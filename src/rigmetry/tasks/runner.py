"""Config를 disposable Workspace, Runtime, Evaluator와 연결하는 Task Runner."""

from __future__ import annotations

import os
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from rigmetry import __version__
from rigmetry.config import (
    ConfigError,
    HarnessConfig,
    TaskConfig,
    build_lock,
    digest_json,
    load_config,
)
from rigmetry.evaluation import CommandEvaluator
from rigmetry.models import (
    ModelAdapter,
    OllamaAdapter,
    OpenAICompatibleAdapter,
    RunTerminationReason,
    ToolDefinition,
)
from rigmetry.runtime import AgentRuntime, RuntimeExecution, RuntimeLimits, RuntimeRequest
from rigmetry.storage import RunStore, StoredRun
from rigmetry.tools import TERMINAL_DEFINITION, TerminalTool
from rigmetry.workspace import WorkspaceManager


class TaskRunnerError(ValueError):
    """지원하지 않는 실행 Config 또는 안전하지 않은 참조."""


def environment_digest() -> str:
    """Machine 경로와 Secret을 제외한 실행 환경 지문."""

    dependencies: dict[str, str] = {}
    for package in ("pydantic", "PyYAML", "typer"):
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            dependencies[package] = "unknown"
    return digest_json(
        {
            "rigmetry": __version__,
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "implementation": platform.python_implementation(),
            "os": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "dependencies": dependencies,
        }
    )


def _project_root(source: Path) -> Path:
    resolved = source.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if (parent / "pyproject.toml").is_file() or (parent / ".git").exists():
            return parent
    return resolved.parent


def _reference(source: Path, reference: str, root: Path) -> Path:
    target = (source.resolve().parent / reference).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as error:
        raise TaskRunnerError(f"허용 root 밖의 참조입니다: {reference}") from error
    return target


def _system_prompt(source: Path, harness: HarnessConfig, root: Path) -> str:
    sections = [harness.system_prompt]
    for reference in harness.skills:
        path = _reference(source, reference, root)
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as error:
            raise TaskRunnerError(f"Skill 파일을 읽을 수 없습니다: {reference}: {error}") from error
        sections.append(f"[Skill: {reference}]\n{content}")
    return "\n\n".join(sections)


def _tools(harness: HarnessConfig) -> tuple[ToolDefinition, ...]:
    definitions: list[ToolDefinition] = []
    for tool in harness.tools:
        if tool.name != "terminal":
            raise TaskRunnerError(f"지원하지 않는 Tool입니다: {tool.name}")
        if tool.description or tool.input_schema:
            definitions.append(
                ToolDefinition(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                )
            )
        else:
            definitions.append(TERMINAL_DEFINITION)
    return tuple(definitions)


def create_adapter(harness: HarnessConfig) -> ModelAdapter:
    model = harness.model
    if model.provider == "openai-compatible":
        return OpenAICompatibleAdapter(
            base_url=model.base_url or "https://api.openai.com/v1",
            api_key_env=model.api_key_env or "OPENAI_API_KEY",
            timeout=harness.runtime.timeout,
        )
    return OllamaAdapter(
        base_url=model.base_url or "http://localhost:11434",
        api_key_env=model.api_key_env,
        timeout=harness.runtime.timeout,
    )


async def run_task(
    *,
    harness_path: str | Path,
    task_path: str | Path,
    store: RunStore,
    run_id: str,
    experiment_digest: str | None = None,
    adapter: ModelAdapter | None = None,
) -> StoredRun:
    """한 Task를 실행·평가하고 Replay 가능한 SQLite Run으로 저장한다."""

    harness_source = Path(harness_path)
    task_source = Path(task_path)
    harness = load_config(harness_source)
    task = load_config(task_source)
    if not isinstance(harness, HarnessConfig):
        raise ConfigError(f"Harness Config가 아닙니다: {harness_source}")
    if not isinstance(task, TaskConfig):
        raise ConfigError(f"Task Config가 아닙니다: {task_source}")
    if harness.mcps:
        raise TaskRunnerError("MCP 실행은 아직 지원하지 않습니다")

    root = _project_root(task_source)
    harness_lock = build_lock(harness_source, root=root)
    task_lock = build_lock(task_source, root=root)
    tool_definitions = _tools(harness)
    workspace_source = _reference(task_source, task.workspace, root)
    effective_adapter = adapter or create_adapter(harness)
    request = RuntimeRequest(
        run_id=run_id,
        model=harness.model.model,
        system_prompt=_system_prompt(harness_source, harness, root),
        prompt=task.prompt,
        tools=tool_definitions,
        limits=RuntimeLimits(
            max_steps=harness.runtime.max_steps,
            timeout=harness.runtime.timeout,
            max_total_tokens=harness.runtime.max_total_tokens,
        ),
        harness_digest=harness_lock["harness_digest"],
        task_digest=task_lock["task_digest"],
        environment_digest=environment_digest(),
        experiment_digest=experiment_digest,
    )

    with WorkspaceManager(root).create(workspace_source) as workspace:
        terminal = TerminalTool(workspace.path, timeout=harness.runtime.timeout)
        runtime = AgentRuntime(effective_adapter, terminal if tool_definitions else None)
        execution = await runtime.run(request)
        evaluator = await CommandEvaluator(
            task.evaluator.command,
            timeout=task.evaluator.timeout,
        ).evaluate(workspace.path)

    if (
        not evaluator.passed
        and execution.result.termination_reason is RunTerminationReason.COMPLETED
    ):
        result = execution.result.model_copy(
            update={"termination_reason": RunTerminationReason.EVALUATION_FAILED}
        )
        execution = RuntimeExecution(
            result=result,
            final_message=execution.final_message,
            events=execution.events,
            model_provenance=execution.model_provenance,
            boundaries=execution.boundaries,
        )

    secrets = ()
    secret_env = harness.model.api_key_env
    if harness.model.provider == "openai-compatible" and secret_env is None:
        secret_env = "OPENAI_API_KEY"
    if secret_env:
        value = os.environ.get(secret_env)
        secrets = (value,) if value else ()
    return store.save_execution(request, execution, evaluator=evaluator, secrets=secrets)
