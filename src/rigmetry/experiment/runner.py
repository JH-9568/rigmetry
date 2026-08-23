"""동결된 Experiment의 반복 Run을 계획하고 순서대로 실행한다."""

from __future__ import annotations

import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rigmetry.config import ExperimentConfig, HarnessConfig, build_lock, load_config
from rigmetry.metrics import build_report
from rigmetry.models import ModelAdapter
from rigmetry.storage import RunStore
from rigmetry.tasks import create_adapter, run_task

AdapterFactory = Callable[[str, HarnessConfig], ModelAdapter]


class ExperimentError(ValueError):
    """Experiment source와 실행 계획을 연결할 수 없음."""


def _resolve(source: Path, reference: str) -> Path:
    return (source.resolve().parent / reference).resolve()


def build_plan(source: str | Path) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    experiment_path = Path(source)
    config = load_config(experiment_path)
    if not isinstance(config, ExperimentConfig):
        raise ExperimentError(f"Experiment Config가 아닙니다: {experiment_path}")
    lock = build_lock(experiment_path)
    seed = config.trials.seed
    if seed is None:
        seed = int(lock["experiment_digest"].split(":", 1)[1][:16], 16)
    order = [
        (trial, variant)
        for trial in range(1, config.trials.count + 1)
        for variant in sorted(config.variants)
    ]
    random.Random(seed).shuffle(order)
    plan = []
    for sequence, (trial, variant) in enumerate(order, start=1):
        harness = load_config(_resolve(experiment_path, config.variants[variant]))
        if not isinstance(harness, HarnessConfig):
            raise ExperimentError(f"Variant가 Harness Config가 아닙니다: {variant}")
        plan.append(
            {
                "sequence": sequence,
                "run_id": f"{config.id}-{sequence:03d}-{variant}",
                "trial": trial,
                "variant": variant,
                "provider": harness.model.provider,
                "model": harness.model.model,
                "harness_digest": lock["harnesses"][variant]["harness_digest"],
                "order_seed": seed,
            }
        )
    return lock, tuple(plan)


async def run_experiment(
    source: str | Path,
    store: RunStore,
    *,
    adapter_factory: AdapterFactory | None = None,
) -> dict[str, Any]:
    """사전 검증한 seed 순서의 모든 Variant/Trial을 실행한다."""

    experiment_path = Path(source)
    config = load_config(experiment_path)
    if not isinstance(config, ExperimentConfig):
        raise ExperimentError(f"Experiment Config가 아닙니다: {experiment_path}")
    lock, plan = build_plan(experiment_path)
    stored_experiment = store.save_experiment(
        config.id,
        lock["experiment_digest"],
        lock,
        plan,
    )
    adapters: dict[str, ModelAdapter] = {}
    task_path = _resolve(experiment_path, config.task)
    for item in plan:
        variant = str(item["variant"])
        harness_path = _resolve(experiment_path, config.variants[variant])
        harness = load_config(harness_path)
        if not isinstance(harness, HarnessConfig):
            raise ExperimentError(f"Variant가 Harness Config가 아닙니다: {variant}")
        if variant not in adapters:
            adapters[variant] = (
                adapter_factory(variant, harness) if adapter_factory else create_adapter(harness)
            )
        await run_task(
            harness_path=harness_path,
            task_path=task_path,
            store=store,
            run_id=str(item["run_id"]),
            experiment_digest=lock["experiment_digest"],
            adapter=adapters[variant],
        )
    return build_report(store, stored_experiment)
