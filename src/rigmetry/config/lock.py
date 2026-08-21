"""YAML Config 검증과 content-addressed Lock 생성."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from yaml.constructor import ConstructorError

from rigmetry.config.models import (
    ExperimentConfig,
    HarnessConfig,
    ProjectConfig,
    TaskConfig,
)
from rigmetry.models import canonical_json_bytes

SCHEMA_VERSION = 1


class ConfigError(ValueError):
    """사용자가 수정할 수 있는 Config 또는 참조 Artifact 오류."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"중복 Key를 사용할 수 없습니다: {key}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def digest_json(value: Any) -> str:
    try:
        return _digest_bytes(canonical_json_bytes(value))
    except (TypeError, ValueError) as error:
        raise ConfigError(f"canonical JSON으로 변환할 수 없습니다: {error}") from error


def _format_validation_error(path: Path, error: ValidationError) -> ConfigError:
    details = []
    for item in error.errors(include_url=False):
        location = ".".join(str(part) for part in item["loc"])
        details.append(f"{location or '<root>'}: {item['msg']}")
    return ConfigError(f"{path}: Config 검증 실패\n- " + "\n- ".join(details))


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"Config 파일을 읽을 수 없습니다: {path}: {error}") from error
    try:
        value = yaml.load(content, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise ConfigError(f"{path}: YAML 문법 오류: {error}") from error
    if not isinstance(value, dict):
        raise ConfigError(f"{path}: YAML 최상위 값은 Map이어야 합니다")
    return value


def load_config(path: str | Path) -> ProjectConfig:
    source = Path(path)
    value = _read_yaml(source)
    try:
        if "variants" in value or "controls" in value:
            return ExperimentConfig.model_validate(value)
        if "workspace" in value or "evaluator" in value:
            return TaskConfig.model_validate(value)
        if "model" in value or "runtime" in value:
            return HarnessConfig.model_validate(value)
    except ValidationError as error:
        raise _format_validation_error(source, error) from error
    raise ConfigError(f"{source}: Harness, Task 또는 Experiment Config를 판별할 수 없습니다")


def _default_root(source: Path) -> Path:
    resolved = source.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if (parent / "pyproject.toml").is_file() or (parent / ".git").exists():
            return parent
    return resolved.parent


def _resolve_reference(source: Path, reference: str, root: Path) -> Path:
    target = (source.resolve().parent / reference).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as error:
        raise ConfigError(f"허용 root 밖의 참조입니다: {reference}") from error
    return target


def _file_digest(path: Path) -> str:
    try:
        return _digest_bytes(path.read_bytes())
    except OSError as error:
        raise ConfigError(f"Artifact를 읽을 수 없습니다: {path}: {error}") from error


def _workspace_digest(path: Path) -> tuple[str, int]:
    if not path.is_dir():
        raise ConfigError(f"Workspace 디렉터리가 없습니다: {path}")
    manifest: list[dict[str, str]] = []
    for candidate in sorted(path.rglob("*")):
        relative = candidate.relative_to(path)
        if ".git" in relative.parts:
            continue
        if candidate.is_symlink():
            raise ConfigError(f"Workspace symlink는 지원하지 않습니다: {relative.as_posix()}")
        if candidate.is_file():
            manifest.append({"path": relative.as_posix(), "digest": _file_digest(candidate)})
    return digest_json(manifest), len(manifest)


def _lock_harness(path: Path, config: HarnessConfig, root: Path) -> dict[str, Any]:
    skill_locks = []
    skill_digests = []
    for reference in config.skills:
        target = _resolve_reference(path, reference, root)
        if not target.is_file():
            raise ConfigError(f"Skill 파일이 없습니다: {reference}")
        content_digest = _file_digest(target)
        skill_locks.append({"reference": reference, "content_digest": content_digest})
        skill_digests.append(content_digest)

    model = config.model.model_dump(mode="json", exclude={"model"})
    model["requested_model"] = config.model.model
    tools = [
        {"name": tool.name, "definition_digest": digest_json(tool.model_dump(mode="json"))}
        for tool in config.tools
    ]
    mcps = [
        {"name": mcp.name, "capability_digest": digest_json(mcp.model_dump(mode="json"))}
        for mcp in config.mcps
    ]
    semantic = {
        "schema_version": SCHEMA_VERSION,
        "kind": "harness",
        "model": model,
        "system_prompt_digest": _digest_bytes(config.system_prompt.encode("utf-8")),
        "mcps": mcps,
        "tools": tools,
        "skill_digests": skill_digests,
        "runtime": config.runtime.model_dump(mode="json"),
    }
    return {
        **semantic,
        "name": config.name,
        "skills": skill_locks,
        "harness_digest": digest_json(semantic),
    }


def _lock_task(path: Path, config: TaskConfig, root: Path) -> dict[str, Any]:
    workspace = _resolve_reference(path, config.workspace, root)
    workspace_digest, file_count = _workspace_digest(workspace)
    evaluator_digest = digest_json(config.evaluator.model_dump(mode="json"))
    semantic = {
        "schema_version": SCHEMA_VERSION,
        "kind": "task",
        "prompt_digest": _digest_bytes(config.prompt.encode("utf-8")),
        "workspace_digest": workspace_digest,
        "evaluator_digest": evaluator_digest,
    }
    return {
        **semantic,
        "id": config.id,
        "workspace": {
            "kind": "fixture",
            "reference": config.workspace,
            "content_digest": workspace_digest,
            "file_count": file_count,
        },
        "evaluator": {
            "type": config.evaluator.type,
            "timeout": config.evaluator.timeout,
            "digest": evaluator_digest,
        },
        "task_digest": digest_json(semantic),
    }


def _control_value(lock: dict[str, Any], path: str) -> Any:
    fields = {
        "harness.model": "model",
        "harness.mcps": "mcps",
        "harness.tools": "tools",
        "harness.skills": "skill_digests",
        "harness.system_prompt": "system_prompt_digest",
        "harness.runtime": "runtime",
    }
    return lock[fields[path]]


def _validate_experiment_controls(
    experiment: ExperimentConfig, harnesses: dict[str, dict[str, Any]]
) -> None:
    locks = list(harnesses.values())
    first = locks[0]
    for path in experiment.controls.require_same:
        if path == "task":
            continue
        expected = _control_value(first, path)
        if any(_control_value(lock, path) != expected for lock in locks[1:]):
            raise ConfigError(f"require_same 조건이 일치하지 않습니다: {path}")

    control_paths = {
        "harness.model",
        "harness.mcps",
        "harness.tools",
        "harness.skills",
        "harness.system_prompt",
        "harness.runtime",
    }
    differences = {
        path
        for path in control_paths
        if any(_control_value(lock, path) != _control_value(first, path) for lock in locks[1:])
    }
    allowed = set(experiment.controls.allow_diff)
    unexpected = sorted(differences - allowed)
    if unexpected:
        raise ConfigError("allow_diff 밖의 Harness 차이입니다: " + ", ".join(unexpected))


def _lock_experiment(path: Path, config: ExperimentConfig, root: Path) -> dict[str, Any]:
    task_path = _resolve_reference(path, config.task, root)
    task = load_config(task_path)
    if not isinstance(task, TaskConfig):
        raise ConfigError(f"Experiment task 참조가 Task Config가 아닙니다: {config.task}")
    task_lock = _lock_task(task_path, task, root)

    harness_locks: dict[str, dict[str, Any]] = {}
    for name, reference in config.variants.items():
        harness_path = _resolve_reference(path, reference, root)
        harness = load_config(harness_path)
        if not isinstance(harness, HarnessConfig):
            raise ConfigError(f"Variant 참조가 Harness Config가 아닙니다: {reference}")
        harness_locks[name] = _lock_harness(harness_path, harness, root)

    _validate_experiment_controls(config, harness_locks)
    semantic = {
        "schema_version": SCHEMA_VERSION,
        "kind": "experiment",
        "task_digest": task_lock["task_digest"],
        "variants": {
            name: lock["harness_digest"] for name, lock in sorted(harness_locks.items())
        },
        "controls": config.controls.model_dump(mode="json"),
        "trials": config.trials.model_dump(mode="json"),
        "metrics": list(config.metrics),
    }
    return {
        **semantic,
        "id": config.id,
        "task": task_lock,
        "harnesses": harness_locks,
        "experiment_digest": digest_json(semantic),
    }


def build_lock(path: str | Path, *, root: str | Path | None = None) -> dict[str, Any]:
    source = Path(path)
    allowed_root = Path(root).resolve() if root is not None else _default_root(source)
    try:
        source.resolve().relative_to(allowed_root)
    except ValueError as error:
        raise ConfigError(f"Config가 허용 root 밖에 있습니다: {source}") from error
    config = load_config(source)
    if isinstance(config, HarnessConfig):
        return _lock_harness(source, config, allowed_root)
    if isinstance(config, TaskConfig):
        return _lock_task(source, config, allowed_root)
    return _lock_experiment(source, config, allowed_root)
