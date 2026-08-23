import asyncio
from pathlib import Path

from rigmetry.config import build_lock
from rigmetry.evaluation import CommandEvaluator
from rigmetry.workspace import WorkspaceManager

ROOT = Path(__file__).parents[1]
BENCHMARKS = ROOT / "benchmarks"
TASKS = ("tag-normalization", "discount-calculation", "retry-schedule")


def test_frozen_benchmarks_only_allow_debugging_skill_diff() -> None:
    digests = set()
    for name in TASKS:
        lock = build_lock(BENCHMARKS / "experiments" / f"{name}-llama32.yaml")

        assert lock["controls"]["allow_diff"] == ["harness.skills"]
        assert lock["trials"]["count"] == 5
        assert lock["trials"]["order"] == "randomized"
        assert lock["trials"]["seed"] is not None
        assert len(lock["variants"]) == 2
        assert len(set(lock["variants"].values())) == 2
        digests.add(lock["experiment_digest"])

    assert len(digests) == 3


def test_frozen_workspace_defects_are_reproduced_before_agent_runs(tmp_path: Path) -> None:
    for name in TASKS:
        source = BENCHMARKS / "fixtures" / name
        with WorkspaceManager(BENCHMARKS, temporary_root=tmp_path).create(source) as workspace:
            result = asyncio.run(
                CommandEvaluator(
                    "python -m unittest discover -s tests -q",
                    timeout=10,
                ).evaluate(workspace.path)
            )

        assert result.passed is False
        assert result.exit_code == 1
