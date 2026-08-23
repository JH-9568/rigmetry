"""Run, Event와 Boundary Transcript의 최소 SQLite 저장소."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import JsonValue, ValidationError

from rigmetry.models import EvaluatorResult, ModelMessage, RunResult, canonical_json_bytes
from rigmetry.models.contracts import ContractModel, Sha256Digest
from rigmetry.runtime import (
    RUNTIME_VERSION,
    ModelProvenance,
    RuntimeExecution,
    RuntimeRequest,
)
from rigmetry.tracing import (
    BoundaryKind,
    EvaluatorBoundary,
    ModelBoundary,
    RuntimeBoundary,
    StoredBoundary,
    ToolBoundary,
    TraceEvent,
    validate_event_chain,
)

SCHEMA_VERSION = 1
REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "refresh_token",
    "secret",
    "token",
}
_SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{8,}\b"),
)


class StorageError(ValueError):
    """저장된 Run이 없거나 내부 계약과 일치하지 않음."""


class StoredRun(ContractModel):
    runtime_version: str
    request: RuntimeRequest
    execution: RuntimeExecution
    evaluator: EvaluatorResult | None = None
    transcript_digest: Sha256Digest


def _digest(value: JsonValue) -> str:
    return f"sha256:{hashlib.sha256(canonical_json_bytes(value)).hexdigest()}"


def _dump(value: Any) -> str:
    if isinstance(value, ContractModel):
        value = value.model_dump(mode="json")
    return canonical_json_bytes(value).decode("utf-8")


def _find_secrets(value: Any, found: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in _SENSITIVE_KEYS and isinstance(item, str) and len(item) >= 4:
                found.add(item)
            _find_secrets(item, found)
    elif isinstance(value, list):
        for item in value:
            _find_secrets(item, found)


def _redact(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if key.lower() in _SENSITIVE_KEYS else _redact(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, str):
        redacted = value
        for secret in secrets:
            redacted = redacted.replace(secret, REDACTED)
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(REDACTED, redacted)
        return redacted
    return value


def _safe_material(value: dict[str, Any], explicit_secrets: Iterable[str]) -> dict[str, Any]:
    secrets = {secret for secret in explicit_secrets if len(secret) >= 4}
    _find_secrets(value, secrets)
    return _redact(value, tuple(sorted(secrets, key=len, reverse=True)))


def _parse_boundary(value: dict[str, Any]) -> StoredBoundary:
    kind = value.get("kind")
    if kind == BoundaryKind.MODEL:
        return ModelBoundary.model_validate(value)
    if kind == BoundaryKind.TOOL:
        return ToolBoundary.model_validate(value)
    if kind == BoundaryKind.EVALUATOR:
        return EvaluatorBoundary.model_validate(value)
    raise StorageError(f"알 수 없는 Boundary kind입니다: {kind}")


def _validate_boundaries(boundaries: tuple[StoredBoundary, ...]) -> None:
    for sequence, boundary in enumerate(boundaries):
        if boundary.sequence != sequence:
            raise StorageError(f"Boundary sequence가 연속적이지 않습니다: {boundary.sequence}")
        if isinstance(boundary, EvaluatorBoundary) and sequence != len(boundaries) - 1:
            raise StorageError("Evaluator Boundary는 Transcript의 마지막이어야 합니다")


def _rechain_events(values: list[dict[str, Any]]) -> tuple[TraceEvent, ...]:
    events: list[TraceEvent] = []
    for value in values:
        previous = events[-1].event_hash if events else None
        events.append(
            TraceEvent.create(
                run_id=value["run_id"],
                sequence=value["sequence"],
                type=value["type"],
                timestamp=value["timestamp"],
                payload=value.get("payload", {}),
                previous_event_hash=previous,
            )
        )
    return tuple(events)


def _transcript_material(
    *,
    runtime_version: str,
    request: RuntimeRequest,
    execution: RuntimeExecution,
    evaluator: EvaluatorResult | None,
    boundaries: tuple[StoredBoundary, ...],
) -> dict[str, JsonValue]:
    return {
        "runtime_version": runtime_version,
        "request": request.model_dump(mode="json"),
        "result": execution.result.model_dump(mode="json"),
        "final_message": (
            execution.final_message.model_dump(mode="json") if execution.final_message else None
        ),
        "model_provenance": [item.model_dump(mode="json") for item in execution.model_provenance],
        "events": [event.model_dump(mode="json") for event in execution.events],
        "boundaries": [boundary.model_dump(mode="json") for boundary in boundaries],
        "evaluator": evaluator.model_dump(mode="json") if evaluator else None,
    }


class RunStore:
    """한 파일에 Run과 Replay 입력을 원자적으로 저장한다."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    runtime_version TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    final_message_json TEXT,
                    provenance_json TEXT NOT NULL,
                    evaluator_json TEXT,
                    transcript_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS boundaries (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    boundary_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence)
                );
                """
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def save_execution(
        self,
        request: RuntimeRequest,
        execution: RuntimeExecution,
        *,
        evaluator: EvaluatorResult | None = None,
        secrets: Iterable[str] = (),
        runtime_version: str = RUNTIME_VERSION,
    ) -> StoredRun:
        if request.run_id != execution.result.run_id:
            raise StorageError("Runtime 요청과 결과의 run_id가 일치하지 않습니다")
        for field in ("harness_digest", "task_digest", "environment_digest", "experiment_digest"):
            if getattr(request, field) != getattr(execution.result, field):
                raise StorageError(f"Runtime 요청과 결과의 {field}가 일치하지 않습니다")
        validate_event_chain(execution.events, run_id=request.run_id)

        if evaluator is not None and execution.result.evaluator not in {None, evaluator}:
            raise StorageError("Runtime 결과와 전달된 Evaluator 결과가 일치하지 않습니다")
        effective_evaluator = evaluator or execution.result.evaluator
        stored_result = execution.result.model_copy(update={"evaluator": effective_evaluator})
        runtime_boundaries = list(execution.boundaries)
        all_boundaries: list[StoredBoundary] = list(runtime_boundaries)
        if effective_evaluator is not None:
            all_boundaries.append(
                EvaluatorBoundary(sequence=len(all_boundaries), result=effective_evaluator)
            )

        raw = {
            "request": request.model_dump(mode="json"),
            "result": stored_result.model_dump(mode="json"),
            "final_message": (
                execution.final_message.model_dump(mode="json") if execution.final_message else None
            ),
            "model_provenance": [
                item.model_dump(mode="json") for item in execution.model_provenance
            ],
            "events": [event.model_dump(mode="json") for event in execution.events],
            "boundaries": [boundary.model_dump(mode="json") for boundary in all_boundaries],
            "evaluator": effective_evaluator.model_dump(mode="json")
            if effective_evaluator
            else None,
        }
        safe = _safe_material(raw, secrets)

        safe_request = RuntimeRequest.model_validate(safe["request"])
        safe_result = RunResult.model_validate(safe["result"])
        safe_final = (
            ModelMessage.model_validate(safe["final_message"])
            if safe["final_message"] is not None
            else None
        )
        safe_provenance = tuple(
            ModelProvenance.model_validate(item) for item in safe["model_provenance"]
        )
        safe_boundaries = tuple(_parse_boundary(item) for item in safe["boundaries"])
        _validate_boundaries(safe_boundaries)
        safe_evaluator = (
            EvaluatorResult.model_validate(safe["evaluator"])
            if safe["evaluator"] is not None
            else None
        )
        safe_events = _rechain_events(safe["events"])
        validate_event_chain(safe_events, run_id=request.run_id)
        safe_runtime_boundaries = tuple(
            boundary
            for boundary in safe_boundaries
            if isinstance(boundary, ModelBoundary | ToolBoundary)
        )
        safe_execution = RuntimeExecution(
            result=safe_result,
            final_message=safe_final,
            events=safe_events,
            model_provenance=safe_provenance,
            boundaries=safe_runtime_boundaries,
        )
        material = _transcript_material(
            runtime_version=runtime_version,
            request=safe_request,
            execution=safe_execution,
            evaluator=safe_evaluator,
            boundaries=safe_boundaries,
        )
        transcript_digest = _digest(material)

        self.initialize()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO runs (
                        run_id, runtime_version, request_json, result_json,
                        final_message_json, provenance_json, evaluator_json,
                        transcript_digest, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.run_id,
                        runtime_version,
                        _dump(safe_request),
                        _dump(safe_result),
                        _dump(safe_final) if safe_final else None,
                        _dump([item.model_dump(mode="json") for item in safe_provenance]),
                        _dump(safe_evaluator) if safe_evaluator else None,
                        transcript_digest,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                connection.executemany(
                    "INSERT INTO events (run_id, sequence, event_json) VALUES (?, ?, ?)",
                    [(request.run_id, event.sequence, _dump(event)) for event in safe_events],
                )
                connection.executemany(
                    """
                    INSERT INTO boundaries (run_id, sequence, kind, boundary_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (request.run_id, boundary.sequence, boundary.kind.value, _dump(boundary))
                        for boundary in safe_boundaries
                    ],
                )
        except sqlite3.IntegrityError as error:
            raise StorageError(f"Run을 저장할 수 없습니다: {request.run_id}") from error

        return StoredRun(
            runtime_version=runtime_version,
            request=safe_request,
            execution=safe_execution,
            evaluator=safe_evaluator,
            transcript_digest=transcript_digest,
        )

    def load_run(self, run_id: str) -> StoredRun:
        self.initialize()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                if row is None:
                    raise StorageError(f"저장된 Run을 찾을 수 없습니다: {run_id}")
                event_rows = connection.execute(
                    "SELECT event_json FROM events WHERE run_id = ? ORDER BY sequence", (run_id,)
                ).fetchall()
                boundary_rows = connection.execute(
                    "SELECT boundary_json FROM boundaries WHERE run_id = ? ORDER BY sequence",
                    (run_id,),
                ).fetchall()

            request = RuntimeRequest.model_validate_json(row["request_json"])
            result = RunResult.model_validate_json(row["result_json"])
            final_message = (
                ModelMessage.model_validate_json(row["final_message_json"])
                if row["final_message_json"]
                else None
            )
            provenance = tuple(
                ModelProvenance.model_validate(item) for item in json.loads(row["provenance_json"])
            )
            evaluator = (
                EvaluatorResult.model_validate_json(row["evaluator_json"])
                if row["evaluator_json"]
                else None
            )
            events = tuple(
                TraceEvent.model_validate_json(item["event_json"]) for item in event_rows
            )
            boundaries = tuple(
                _parse_boundary(json.loads(item["boundary_json"])) for item in boundary_rows
            )
        except (json.JSONDecodeError, ValidationError, KeyError, TypeError) as error:
            raise StorageError(f"저장된 Run 형식이 손상되었습니다: {run_id}") from error

        validate_event_chain(events, run_id=run_id)
        _validate_boundaries(boundaries)
        runtime_boundaries: tuple[RuntimeBoundary, ...] = tuple(
            boundary
            for boundary in boundaries
            if isinstance(boundary, ModelBoundary | ToolBoundary)
        )
        execution = RuntimeExecution(
            result=result,
            final_message=final_message,
            events=events,
            model_provenance=provenance,
            boundaries=runtime_boundaries,
        )
        actual_digest = _digest(
            _transcript_material(
                runtime_version=row["runtime_version"],
                request=request,
                execution=execution,
                evaluator=evaluator,
                boundaries=boundaries,
            )
        )
        if actual_digest != row["transcript_digest"]:
            raise StorageError("Boundary Transcript digest가 일치하지 않습니다")
        if result.evaluator != evaluator:
            raise StorageError("Run Result와 Evaluator 경계 결과가 일치하지 않습니다")

        return StoredRun(
            runtime_version=row["runtime_version"],
            request=request,
            execution=execution,
            evaluator=evaluator,
            transcript_digest=row["transcript_digest"],
        )
