import asyncio
import json
from pathlib import Path

import pytest

from rigmetry.experiment import (
    EvidenceError,
    build_plan,
    export_evidence,
    run_experiment,
    verify_evidence,
)
from rigmetry.models import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelResult,
    ProviderCapabilities,
    TokenTotalSource,
    TokenUsage,
)
from rigmetry.replay import replay_run
from rigmetry.storage import RunStore
from rigmetry.tasks import run_task


class FakeAdapter:
    name = "ollama"
    version = "test"
    capabilities = ProviderCapabilities(token_usage=True)

    async def complete(self, request: ModelRequest) -> ModelResult:
        return ModelResult(
            message=ModelMessage(role=MessageRole.ASSISTANT, content="done"),
            usage=TokenUsage(
                input_tokens=7,
                output_tokens=3,
                total_tokens=10,
                total_tokens_source=TokenTotalSource.PROVIDER,
            ),
            response_model=request.model,
        )


def _write_project(root: Path, *, evaluator_passes: bool = True) -> tuple[Path, Path, Path]:
    workspace = root / "workspace"
    workspace.mkdir()
    (workspace / "ok.txt").write_text("ok", encoding="utf-8")
    (root / "skill.md").write_text("check the evidence", encoding="utf-8")
    passing_command = (
        'python -c "import pathlib; '
        "raise SystemExit(0 if pathlib.Path('ok.txt').exists() else 1)\""
    )
    evaluator = passing_command if evaluator_passes else 'python -c "raise SystemExit(1)"'
    task = root / "task.yaml"
    task.write_text(
        "\n".join(
            [
                "id: task-one",
                "workspace: ./workspace",
                "prompt: finish the task",
                "evaluator:",
                "  type: command",
                f"  command: {evaluator}",
                "  timeout: 5",
            ]
        ),
        encoding="utf-8",
    )
    base_harness = "\n".join(
        [
            "name: {name}",
            "model:",
            "  provider: ollama",
            "  model: fake-model",
            "system_prompt: do the work",
            "mcps: []",
            "tools: []",
            "skills: {skills}",
            "runtime:",
            "  max_steps: 2",
            "  timeout: 5",
            "  max_total_tokens: 100",
        ]
    )
    baseline = root / "baseline.yaml"
    candidate = root / "candidate.yaml"
    baseline.write_text(base_harness.format(name="baseline", skills="[]"), encoding="utf-8")
    candidate.write_text(
        base_harness.format(name="candidate", skills="[./skill.md]"), encoding="utf-8"
    )
    experiment = root / "experiment.yaml"
    experiment.write_text(
        "\n".join(
            [
                "id: evidence-test",
                "task: ./task.yaml",
                "variants:",
                "  baseline: ./baseline.yaml",
                "  candidate: ./candidate.yaml",
                "controls:",
                "  require_same: [task, harness.model, harness.runtime]",
                "  allow_diff: [harness.skills]",
                "trials:",
                "  count: 2",
                "  order: randomized",
                "  seed: 9568",
                "metrics: [success_rate, total_tokens, steps, duration]",
            ]
        ),
        encoding="utf-8",
    )
    return baseline, task, experiment


def test_task_runner_records_evaluation_failure_and_replays(tmp_path: Path) -> None:
    harness, task, _ = _write_project(tmp_path, evaluator_passes=False)
    store = RunStore(tmp_path / "runs.sqlite")

    stored = asyncio.run(
        run_task(
            harness_path=harness,
            task_path=task,
            store=store,
            run_id="evaluation-failed",
            adapter=FakeAdapter(),
        )
    )
    replay = asyncio.run(replay_run(store, "evaluation-failed"))

    assert stored.execution.result.termination_reason == "evaluation_failed"
    assert stored.evaluator is not None and not stored.evaluator.passed
    assert replay.result.termination_reason == "evaluation_failed"
    assert replay.external_calls.model == 0


def test_compare_export_and_verify_use_every_planned_run(tmp_path: Path) -> None:
    _, _, experiment = _write_project(tmp_path)
    database = tmp_path / "runs.sqlite"
    store = RunStore(database)
    first_plan = build_plan(experiment)[1]
    second_plan = build_plan(experiment)[1]

    report = asyncio.run(
        run_experiment(
            experiment,
            store,
            adapter_factory=lambda _variant, _harness: FakeAdapter(),
        )
    )

    assert first_plan == second_plan
    assert report["planned_runs"] == 4
    assert report["stored_runs"] == 4
    assert report["cross_provider_token_ranking"] is False
    variants = report["groups"][0]["variants"]
    assert {item["metrics"]["success_at_budget"] for item in variants} == {1.0}
    assert {item["metrics"]["tokens_per_success"] for item in variants} == {10.0}
    assert {item["pareto"]["status"] for item in variants} == {"frontier"}

    evidence = tmp_path / "evidence"
    manifest = export_evidence(store, "evidence-test", evidence)
    verified = asyncio.run(verify_evidence(evidence))

    assert manifest["planned_runs"] == 4
    assert verified["valid"] is True
    assert verified["verified_runs"] == 4
    assert verified["external_calls"] == {"model": 0, "tool": 0, "evaluator": 0}

    report_path = evidence / "report.json"
    value = json.loads(report_path.read_text(encoding="utf-8"))
    value["stored_runs"] = 3
    report_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(EvidenceError, match="Artifact digest"):
        asyncio.run(verify_evidence(evidence))
