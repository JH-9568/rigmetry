"""이식 가능한 Evidence Bundle 생성과 내부 일관성 검증."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from rigmetry.config import digest_json
from rigmetry.metrics import build_report, render_markdown
from rigmetry.replay import replay_stored_run
from rigmetry.storage import RunStore


class EvidenceError(ValueError):
    """Evidence artifact, Lock, Run 또는 Report 불일치."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _file_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-.")
    return normalized or "variant"


def export_evidence(store: RunStore, experiment_id: str, output: str | Path) -> dict[str, Any]:
    destination = Path(output)
    if destination.exists():
        raise EvidenceError(f"Evidence 출력 경로가 이미 있습니다: {destination}")
    destination.mkdir(parents=True)
    experiment = store.load_experiment(experiment_id)
    report = build_report(store, experiment)

    bundle_store = RunStore(destination / "runs.sqlite")
    bundle_store.save_experiment(
        experiment.experiment_id,
        experiment.experiment_digest,
        experiment.lock,
        experiment.plan,
    )
    for item in experiment.plan:
        stored = store.load_run(str(item["run_id"]))
        copied = bundle_store.save_execution(
            stored.request,
            stored.execution,
            evaluator=stored.evaluator,
            runtime_version=stored.runtime_version,
        )
        if copied.transcript_digest != stored.transcript_digest:
            raise EvidenceError(
                f"Run 복사 중 Transcript digest가 바뀌었습니다: {stored.request.run_id}"
            )

    artifacts: dict[str, str] = {}
    logical_locks: dict[str, str] = {
        "experiment": "experiment.lock.json",
        "task": "task.lock.json",
    }
    (destination / logical_locks["experiment"]).write_bytes(_json_bytes(experiment.lock))
    (destination / logical_locks["task"]).write_bytes(_json_bytes(experiment.lock["task"]))
    used_names = set(logical_locks.values())
    for index, (variant, lock) in enumerate(sorted(experiment.lock["harnesses"].items()), start=1):
        filename = f"harness-{index}-{_safe_name(variant)}.lock.json"
        if filename in used_names:
            raise EvidenceError(f"Harness Lock 파일명이 충돌합니다: {variant}")
        used_names.add(filename)
        logical_locks[f"harness:{variant}"] = filename
        (destination / filename).write_bytes(_json_bytes(lock))
    (destination / "report.json").write_bytes(_json_bytes(report))
    (destination / "report.md").write_text(render_markdown(report), encoding="utf-8")

    for filename in (*logical_locks.values(), "runs.sqlite", "report.json", "report.md"):
        artifacts[filename] = _file_digest(destination / filename)
    evidence_digest = digest_json(
        {"experiment_digest": experiment.experiment_digest, "artifacts": artifacts}
    )
    manifest = {
        "schema_version": 1,
        "experiment_id": experiment.experiment_id,
        "experiment_digest": experiment.experiment_digest,
        "evidence_digest": evidence_digest,
        "artifacts": artifacts,
        "locks": logical_locks,
        "planned_runs": len(experiment.plan),
    }
    (destination / "manifest.json").write_bytes(_json_bytes(manifest))
    return manifest


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError(f"JSON Artifact를 읽을 수 없습니다: {path.name}") from error
    if not isinstance(value, dict):
        raise EvidenceError(f"JSON Artifact는 object여야 합니다: {path.name}")
    return value


def _verify_lock_digests(lock: dict[str, Any]) -> None:
    task = lock["task"]
    task_semantic = {
        key: task[key]
        for key in (
            "schema_version",
            "kind",
            "prompt_digest",
            "workspace_digest",
            "evaluator_digest",
        )
    }
    if digest_json(task_semantic) != task["task_digest"]:
        raise EvidenceError("Task Lock digest가 일치하지 않습니다")
    for variant, harness in lock["harnesses"].items():
        harness_semantic = {
            key: harness[key]
            for key in (
                "schema_version",
                "kind",
                "model",
                "system_prompt_digest",
                "mcps",
                "tools",
                "skill_digests",
                "runtime",
            )
        }
        if digest_json(harness_semantic) != harness["harness_digest"]:
            raise EvidenceError(f"Harness Lock digest가 일치하지 않습니다: {variant}")
    semantic = {
        key: lock[key]
        for key in (
            "schema_version",
            "kind",
            "task_digest",
            "variants",
            "controls",
            "trials",
            "metrics",
        )
    }
    if digest_json(semantic) != lock["experiment_digest"]:
        raise EvidenceError("Experiment Lock digest가 일치하지 않습니다")


def _verify_controls(lock: dict[str, Any]) -> None:
    fields = {
        "harness.model": "model",
        "harness.mcps": "mcps",
        "harness.tools": "tools",
        "harness.skills": "skill_digests",
        "harness.system_prompt": "system_prompt_digest",
        "harness.runtime": "runtime",
    }
    harnesses = list(lock["harnesses"].values())
    first = harnesses[0]
    differences = {
        path
        for path, field in fields.items()
        if any(item[field] != first[field] for item in harnesses[1:])
    }
    required = set(lock["controls"]["require_same"])
    violated = sorted((required - {"task"}) & differences)
    unexpected = sorted(differences - set(lock["controls"]["allow_diff"]))
    if violated:
        raise EvidenceError("require_same 위반입니다: " + ", ".join(violated))
    if unexpected:
        raise EvidenceError("allow_diff 밖의 차이입니다: " + ", ".join(unexpected))


def _scan_secrets(root: Path) -> None:
    patterns = (
        re.compile(rb"(?i)bearer\s+[a-z0-9._~+/=-]{8,}"),
        re.compile(rb"\bsk-[A-Za-z0-9_-]{8,}\b"),
        re.compile(rb"\bgh[pousr]_[A-Za-z0-9_]{8,}\b"),
        re.compile(rb'(?i)"(?:password|secret|authorization)"\s*:\s*"(?!\[REDACTED\])[^\"]+"'),
    )
    for path in root.iterdir():
        if path.is_file() and any(pattern.search(path.read_bytes()) for pattern in patterns):
            raise EvidenceError(f"알려진 Secret pattern이 발견되었습니다: {path.name}")


async def verify_evidence(source: str | Path) -> dict[str, Any]:
    root = Path(source)
    manifest = _load_json(root / "manifest.json")
    required = {
        "schema_version",
        "experiment_id",
        "experiment_digest",
        "evidence_digest",
        "artifacts",
        "locks",
        "planned_runs",
    }
    if set(manifest) != required or not isinstance(manifest.get("artifacts"), dict):
        raise EvidenceError("Manifest Schema가 유효하지 않습니다")
    if not isinstance(manifest.get("locks"), dict):
        raise EvidenceError("Manifest Lock Map이 유효하지 않습니다")
    expected_files = set(manifest["artifacts"]) | {"manifest.json"}
    actual_files = {path.name for path in root.iterdir() if path.is_file()}
    if actual_files != expected_files:
        raise EvidenceError("Manifest와 Bundle 파일 목록이 일치하지 않습니다")
    for filename, expected in manifest["artifacts"].items():
        if _file_digest(root / filename) != expected:
            raise EvidenceError(f"Artifact digest가 일치하지 않습니다: {filename}")
    expected_evidence_digest = digest_json(
        {
            "experiment_digest": manifest["experiment_digest"],
            "artifacts": manifest["artifacts"],
        }
    )
    if manifest["evidence_digest"] != expected_evidence_digest:
        raise EvidenceError("Evidence digest가 일치하지 않습니다")

    lock = _load_json(root / manifest["locks"]["experiment"])
    if lock["experiment_digest"] != manifest["experiment_digest"]:
        raise EvidenceError("Manifest와 Experiment Lock digest가 다릅니다")
    if _load_json(root / manifest["locks"]["task"]) != lock["task"]:
        raise EvidenceError("Task Lock Artifact가 Experiment Lock과 다릅니다")
    for variant, harness in lock["harnesses"].items():
        if _load_json(root / manifest["locks"][f"harness:{variant}"]) != harness:
            raise EvidenceError(f"Harness Lock Artifact가 다릅니다: {variant}")
    _verify_lock_digests(lock)
    _verify_controls(lock)

    store = RunStore(root / "runs.sqlite")
    experiment = store.load_experiment(manifest["experiment_id"])
    if experiment.lock != lock or experiment.experiment_digest != manifest["experiment_digest"]:
        raise EvidenceError("SQLite Experiment와 Lock Artifact가 다릅니다")
    if len(experiment.plan) != manifest["planned_runs"]:
        raise EvidenceError("계획한 Run 수가 일치하지 않습니다")
    report = build_report(store, experiment, strict_run_set=True)
    if _load_json(root / "report.json") != report:
        raise EvidenceError("Report Metric 재계산 결과가 일치하지 않습니다")
    if (root / "report.md").read_text(encoding="utf-8") != render_markdown(report):
        raise EvidenceError("Markdown Report 재계산 결과가 일치하지 않습니다")
    for item in experiment.plan:
        replay = await replay_stored_run(store.load_run(str(item["run_id"])))
        if any(replay.external_calls.model_dump().values()):
            raise EvidenceError(f"Offline Replay 외부 호출 수가 0이 아닙니다: {replay.run_id}")
    _scan_secrets(root)
    return {
        "valid": True,
        "experiment_id": experiment.experiment_id,
        "evidence_digest": manifest["evidence_digest"],
        "verified_runs": len(experiment.plan),
        "external_calls": {"model": 0, "tool": 0, "evaluator": 0},
    }


def verify_evidence_sync(source: str | Path) -> dict[str, Any]:
    return asyncio.run(verify_evidence(source))
