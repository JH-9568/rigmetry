import json
from pathlib import Path
from textwrap import dedent

import pytest
from typer.testing import CliRunner

from rigmetry.cli import app
from rigmetry.config import ConfigError, build_lock, load_config
from rigmetry.config.models import ExperimentConfig, HarnessConfig, TaskConfig

ROOT = Path(__file__).parents[1]


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content).strip() + "\n", encoding="utf-8")
    return path


def test_examples_validate_and_create_a_portable_experiment_lock() -> None:
    harness = load_config(ROOT / "examples/harnesses/basic.yaml")
    task = load_config(ROOT / "examples/tasks/example.yaml")
    experiment_path = ROOT / "examples/experiments/debugging-skill.yaml"
    experiment = load_config(experiment_path)
    lock = build_lock(experiment_path)
    rendered = json.dumps(lock, ensure_ascii=False)

    assert isinstance(harness, HarnessConfig)
    assert isinstance(task, TaskConfig)
    assert isinstance(experiment, ExperimentConfig)
    assert lock["kind"] == "experiment"
    assert lock["harnesses"]["baseline"]["model"]["requested_model"] == "qwen3:8b"
    assert "response_model" not in rendered
    assert str(ROOT) not in rendered


def test_key_order_does_not_change_harness_digest_but_tool_schema_does(tmp_path: Path) -> None:
    first = _write(
        tmp_path / "first.yaml",
        """
        name: first
        model: {provider: ollama, model: qwen3:8b}
        system_prompt: test
        mcps:
          - name: filesystem
            capabilities: {write: false, read: true}
        tools:
          - name: terminal
            input_schema:
              type: object
              properties: {cwd: {type: string}, command: {type: string}}
        skills: []
        runtime: {max_steps: 20, timeout: 120, max_total_tokens: 50000}
        """,
    )
    reordered = _write(
        tmp_path / "reordered.yaml",
        """
        runtime: {max_total_tokens: 50000, timeout: 120, max_steps: 20}
        skills: []
        tools:
          - input_schema:
              properties: {command: {type: string}, cwd: {type: string}}
              type: object
            name: terminal
        mcps:
          - capabilities: {read: true, write: false}
            name: filesystem
        system_prompt: test
        model: {model: qwen3:8b, provider: ollama}
        name: reordered
        """,
    )

    first_digest = build_lock(first)["harness_digest"]
    assert build_lock(reordered)["harness_digest"] == first_digest

    changed = first.read_text(encoding="utf-8").replace("type: string", "type: integer", 1)
    first.write_text(changed, encoding="utf-8")
    assert build_lock(first)["harness_digest"] != first_digest


def test_skill_and_evaluator_content_change_related_digests(tmp_path: Path) -> None:
    skill = _write(tmp_path / "skill.md", "첫 번째 지침")
    harness = _write(
        tmp_path / "harness.yaml",
        """
        name: skill-test
        model: {provider: ollama, model: qwen3:8b}
        system_prompt: test
        mcps: []
        tools: [terminal]
        skills: [./skill.md]
        runtime: {max_steps: 20, timeout: 120, max_total_tokens: 50000}
        """,
    )
    before_skill = build_lock(harness)["harness_digest"]
    skill.write_text("변경한 지침\n", encoding="utf-8")
    assert build_lock(harness)["harness_digest"] != before_skill

    _write(tmp_path / "workspace/file.txt", "fixture")
    task = _write(
        tmp_path / "task.yaml",
        """
        id: task
        workspace: ./workspace
        prompt: fix it
        evaluator: {type: command, command: pytest, timeout: 60}
        """,
    )
    before_evaluator = build_lock(task)["task_digest"]
    task.write_text(
        task.read_text(encoding="utf-8").replace("command: pytest", "command: pytest -q"),
        encoding="utf-8",
    )
    assert build_lock(task)["task_digest"] != before_evaluator


def test_experiment_rejects_difference_outside_allow_diff(tmp_path: Path) -> None:
    _write(tmp_path / "workspace/file.txt", "fixture")
    _write(
        tmp_path / "task.yaml",
        """
        id: task
        workspace: ./workspace
        prompt: fix it
        evaluator: {type: command, command: pytest, timeout: 60}
        """,
    )
    base_harness = """
        name: {name}
        model: {{provider: ollama, model: qwen3:8b}}
        system_prompt: test
        mcps: []
        tools: [terminal]
        skills: {skills}
        runtime: {{max_steps: {steps}, timeout: 120, max_total_tokens: 50000}}
    """
    _write(
        tmp_path / "baseline.yaml",
        base_harness.format(name="baseline", skills="[]", steps=20),
    )
    _write(
        tmp_path / "candidate.yaml",
        base_harness.format(name="candidate", skills="[]", steps=21),
    )
    experiment = _write(
        tmp_path / "experiment.yaml",
        """
        id: controlled
        task: ./task.yaml
        variants: {baseline: ./baseline.yaml, candidate: ./candidate.yaml}
        controls:
          require_same: [task, harness.model]
          allow_diff: [harness.skills]
        trials: {count: 2, order: randomized, seed: 1}
        metrics: [success_rate]
        """,
    )

    with pytest.raises(ConfigError, match="allow_diff 밖"):
        build_lock(experiment)

    experiment.write_text(
        experiment.read_text(encoding="utf-8").replace(
            "require_same: [task, harness.model]",
            "require_same: [task, harness.model, harness.runtime]",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="require_same"):
        build_lock(experiment)


def test_experiment_controls_compare_skill_contents(tmp_path: Path) -> None:
    _write(tmp_path / "workspace/file.txt", "fixture")
    _write(
        tmp_path / "task.yaml",
        """
        id: task
        workspace: ./workspace
        prompt: fix it
        evaluator: {type: command, command: pytest, timeout: 60}
        """,
    )
    harness = """
        name: variant
        model: {provider: ollama, model: qwen3:8b}
        system_prompt: test
        mcps: []
        tools: [terminal]
        skills: [./skill.md]
        runtime: {max_steps: 20, timeout: 120, max_total_tokens: 50000}
    """
    _write(tmp_path / "baseline/harness.yaml", harness)
    _write(tmp_path / "baseline/skill.md", "baseline skill")
    _write(tmp_path / "candidate/harness.yaml", harness)
    _write(tmp_path / "candidate/skill.md", "candidate skill")
    experiment = _write(
        tmp_path / "experiment.yaml",
        """
        id: controlled
        task: ./task.yaml
        variants:
          baseline: ./baseline/harness.yaml
          candidate: ./candidate/harness.yaml
        controls:
          require_same: [task, harness.model, harness.runtime]
          allow_diff: []
        trials: {count: 2, order: randomized, seed: 1}
        metrics: [success_rate]
        """,
    )

    with pytest.raises(ConfigError, match="harness.skills"):
        build_lock(experiment)


def test_credential_values_are_rejected_and_environment_secret_is_not_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _write(
        tmp_path / "secret.yaml",
        """
        name: unsafe
        model:
          provider: openai-compatible
          model: model
          api_key: actual-secret
        system_prompt: test
        mcps: []
        tools: []
        skills: []
        runtime: {max_steps: 1, timeout: 1, max_total_tokens: 1}
        """,
    )

    with pytest.raises(ConfigError, match="api_key"):
        load_config(harness)

    safe = _write(
        tmp_path / "safe.yaml",
        """
        name: safe
        model:
          provider: openai-compatible
          model: model
          api_key_env: TEST_PROVIDER_KEY
        system_prompt: test
        mcps: []
        tools: []
        skills: []
        runtime: {max_steps: 1, timeout: 1, max_total_tokens: 1}
        """,
    )
    monkeypatch.setenv("TEST_PROVIDER_KEY", "runtime-only-secret")
    rendered = json.dumps(build_lock(safe))
    assert "TEST_PROVIDER_KEY" in rendered
    assert "runtime-only-secret" not in rendered


def test_validate_and_lock_cli() -> None:
    runner = CliRunner()
    experiment = ROOT / "examples/experiments/debugging-skill.yaml"

    validated = runner.invoke(app, ["validate", str(experiment)])
    locked = runner.invoke(app, ["lock", str(experiment)])

    assert validated.exit_code == 0
    assert "유효한 ExperimentConfig" in validated.output
    assert locked.exit_code == 0
    assert json.loads(locked.output)["kind"] == "experiment"
