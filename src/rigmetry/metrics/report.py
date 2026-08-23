"""저장된 전체 Run에서 비교 Metric과 Pareto 상태를 계산한다."""

from __future__ import annotations

from collections import Counter
from statistics import mean, median
from typing import Any

from rigmetry.storage import RunStore, StoredExperiment, StoredRun


class ReportError(ValueError):
    """실험 계획과 저장된 Run이 일치하지 않음."""


def _summary(values: list[int | None]) -> dict[str, int | float | None]:
    observed = [value for value in values if value is not None]
    return {
        "mean": mean(observed) if observed else None,
        "median": median(observed) if observed else None,
        "observed": len(observed),
    }


def _success(run: StoredRun) -> bool:
    return (
        run.execution.result.termination_reason == "completed"
        and run.evaluator is not None
        and run.evaluator.passed
    )


def _variant_metrics(runs: list[StoredRun]) -> dict[str, Any]:
    successes = sum(_success(run) for run in runs)
    totals = [run.execution.result.usage.total_tokens for run in runs]
    all_tokens_observed = all(value is not None for value in totals)
    if successes == 0:
        tokens_per_success = None
        null_reason = "no_successful_runs"
    elif not all_tokens_observed:
        tokens_per_success = None
        null_reason = "total_tokens_unavailable"
    else:
        tokens_per_success = sum(value for value in totals if value is not None) / successes
        null_reason = None

    usages = [run.execution.result.usage for run in runs]
    results = [run.execution.result for run in runs]
    return {
        "attempts": len(runs),
        "successes": successes,
        "success_at_budget": successes / len(runs),
        "tokens_per_success": tokens_per_success,
        "tokens_per_success_null_reason": null_reason,
        "tokens": {
            field: _summary([getattr(usage, field) for usage in usages])
            for field in (
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "cached_input_tokens",
                "reasoning_tokens",
            )
        },
        "steps": _summary([result.steps for result in results]),
        "model_calls": _summary([result.model_calls for result in results]),
        "tool_calls": _summary([result.tool_calls for result in results]),
        "duration_ms": _summary([result.duration_ms for result in results]),
        "termination_reasons": dict(
            sorted(Counter(result.termination_reason.value for result in results).items())
        ),
    }


def _harness_diff(lock: dict[str, Any]) -> list[dict[str, Any]]:
    fields = {
        "harness.model": "model",
        "harness.mcps": "mcps",
        "harness.tools": "tools",
        "harness.skills": "skill_digests",
        "harness.system_prompt": "system_prompt_digest",
        "harness.runtime": "runtime",
    }
    harnesses = lock["harnesses"]
    variants = sorted(harnesses)
    return [
        {
            "path": path,
            "allowed": path in lock["controls"]["allow_diff"],
            "values": {name: harnesses[name][field] for name in variants},
        }
        for path, field in fields.items()
        if len({str(harnesses[name][field]) for name in variants}) > 1
    ]


def _apply_pareto(variants: list[dict[str, Any]]) -> None:
    for candidate in variants:
        candidate_metrics = candidate["metrics"]
        candidate_tokens = candidate_metrics["tokens_per_success"]
        if candidate_tokens is None:
            candidate["pareto"] = {"status": "indeterminate", "dominated_by": []}
            continue
        dominated_by = []
        for other in variants:
            if other is candidate:
                continue
            other_metrics = other["metrics"]
            other_tokens = other_metrics["tokens_per_success"]
            if other_tokens is None:
                continue
            no_worse = (
                other_metrics["success_at_budget"] >= candidate_metrics["success_at_budget"]
                and other_tokens <= candidate_tokens
            )
            strictly_better = (
                other_metrics["success_at_budget"] > candidate_metrics["success_at_budget"]
                or other_tokens < candidate_tokens
            )
            if no_worse and strictly_better:
                dominated_by.append(other["variant"])
        candidate["pareto"] = {
            "status": "dominated" if dominated_by else "frontier",
            "dominated_by": sorted(dominated_by),
        }


def build_report(
    store: RunStore, experiment: StoredExperiment, *, strict_run_set: bool = False
) -> dict[str, Any]:
    """계획된 모든 Run을 읽고 선택 없이 Report를 다시 계산한다."""

    planned_ids = [str(item["run_id"]) for item in experiment.plan]
    if len(planned_ids) != len(set(planned_ids)):
        raise ReportError("Experiment plan의 run_id가 중복되었습니다")
    runs: dict[str, StoredRun] = {}
    for run_id in planned_ids:
        runs[run_id] = store.load_run(run_id)
    extra = sorted(set(store.list_run_ids()) - set(planned_ids))
    if strict_run_set and extra:
        raise ReportError("Experiment DB에 계획 밖 Run이 있습니다: " + ", ".join(extra))

    grouped: dict[tuple[str, str], dict[str, list[StoredRun]]] = {}
    run_rows = []
    environment_digests: set[str] = set()
    budgets: set[int] = set()
    for item in experiment.plan:
        run = runs[str(item["run_id"])]
        result = run.execution.result
        if result.experiment_digest != experiment.experiment_digest:
            raise ReportError(f"Run의 experiment_digest가 다릅니다: {result.run_id}")
        if result.harness_digest != item["harness_digest"]:
            raise ReportError(f"Run의 harness_digest가 다릅니다: {result.run_id}")
        if result.task_digest != experiment.lock["task_digest"]:
            raise ReportError(f"Run의 task_digest가 다릅니다: {result.run_id}")
        if run.request.model != item["model"]:
            raise ReportError(f"Run의 요청 Model이 계획과 다릅니다: {result.run_id}")
        expected_runtime = experiment.lock["harnesses"][str(item["variant"])]["runtime"]
        if run.request.limits.model_dump(mode="json") != expected_runtime:
            raise ReportError(f"Run의 Runtime Budget이 Lock과 다릅니다: {result.run_id}")
        environment_digests.add(result.environment_digest)
        budgets.add(run.request.limits.max_total_tokens)
        key = (str(item["provider"]), str(item["model"]))
        grouped.setdefault(key, {}).setdefault(str(item["variant"]), []).append(run)
        run_rows.append(
            {
                **item,
                "termination_reason": result.termination_reason.value,
                "evaluator_passed": run.evaluator.passed if run.evaluator else None,
                "total_tokens": result.usage.total_tokens,
                "steps": result.steps,
                "model_calls": result.model_calls,
                "tool_calls": result.tool_calls,
                "duration_ms": result.duration_ms,
                "transcript_digest": run.transcript_digest,
            }
        )

    if len(environment_digests) != 1:
        raise ReportError("Experiment Run의 environment_digest가 일치하지 않습니다")
    if len(budgets) != 1:
        raise ReportError("Experiment Variant의 Token Budget이 일치하지 않습니다")

    groups = []
    for (provider, model), variants_by_name in sorted(grouped.items()):
        variants = [
            {"variant": name, "metrics": _variant_metrics(variant_runs)}
            for name, variant_runs in sorted(variants_by_name.items())
        ]
        _apply_pareto(variants)
        groups.append(
            {
                "provider": provider,
                "model": model,
                "token_ranking_scope": "within_provider_model_only",
                "variants": variants,
            }
        )

    return {
        "schema_version": 1,
        "experiment_id": experiment.experiment_id,
        "experiment_digest": experiment.experiment_digest,
        "planned_runs": len(experiment.plan),
        "stored_runs": len(runs),
        "order_seed": experiment.plan[0].get("order_seed") if experiment.plan else None,
        "controls": experiment.lock["controls"],
        "harness_diff": _harness_diff(experiment.lock),
        "cross_provider_token_ranking": False,
        "groups": groups,
        "runs": run_rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Experiment Report: {report['experiment_id']}",
        "",
        f"- Experiment digest: `{report['experiment_digest']}`",
        f"- Runs: {report['stored_runs']} / {report['planned_runs']}",
        "- Token ranking: 같은 Provider·Model 내부에서만 비교",
        "",
    ]
    for group in report["groups"]:
        lines.extend([f"## {group['provider']} / {group['model']}", ""])
        lines.append("| Variant | success@budget | tokens/success | Pareto |")
        lines.append("|---|---:|---:|---|")
        for variant in group["variants"]:
            metrics = variant["metrics"]
            tokens = metrics["tokens_per_success"]
            token_text = str(round(tokens, 2)) if tokens is not None else "null"
            lines.append(
                f"| {variant['variant']} | {metrics['success_at_budget']:.3f} | "
                f"{token_text} | {variant['pareto']['status']} |"
            )
        lines.append("")
    return "\n".join(lines)
