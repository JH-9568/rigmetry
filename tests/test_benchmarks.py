import asyncio
from pathlib import Path

from rigmetry.config import build_lock
from rigmetry.evaluation import CommandEvaluator

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


def test_frozen_workspace_defects_are_reproduced_before_agent_runs() -> None:
    for name in TASKS:
        workspace = BENCHMARKS / "fixtures" / name
        result = asyncio.run(
            CommandEvaluator(
                "python -m unittest discover -s tests -q",
                timeout=10,
            ).evaluate(workspace)
        )

        assert result.passed is False
        assert result.exit_code == 1
