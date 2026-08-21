"""Append-only Trace Event 계약과 hash 계산."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, JsonValue, field_validator

from rigmetry.models.contracts import (
    ContractModel,
    Sha256Digest,
    canonical_json_bytes,
)


class EventType(StrEnum):
    RUN_STARTED = "run.started"
    STEP_STARTED = "step.started"
    MODEL_REQUESTED = "model.requested"
    MODEL_COMPLETED = "model.completed"
    TOOL_REQUESTED = "tool.requested"
    TOOL_COMPLETED = "tool.completed"
    STEP_COMPLETED = "step.completed"
    EVALUATION_COMPLETED = "evaluation.completed"
    RUN_FINISHED = "run.finished"
    RUN_FAILED = "run.failed"


class TraceEvent(ContractModel):
    """Run 안에서 이전 Event hash를 가리키는 불변 Event."""

    run_id: str
    sequence: int = Field(ge=0)
    type: EventType
    timestamp: datetime
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    previous_event_hash: Sha256Digest | None = None
    event_hash: Sha256Digest

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp에는 timezone 정보가 필요합니다")
        return value.astimezone(UTC)

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        sequence: int,
        type: EventType,
        timestamp: datetime,
        payload: dict[str, JsonValue] | None = None,
        previous_event_hash: Sha256Digest | None = None,
    ) -> Self:
        event = cls(
            run_id=run_id,
            sequence=sequence,
            type=type,
            timestamp=timestamp,
            payload=payload or {},
            previous_event_hash=previous_event_hash,
            event_hash="sha256:" + "0" * 64,
        )
        return event.model_copy(update={"event_hash": event.compute_hash()})

    def compute_hash(self) -> str:
        material = self.model_dump(mode="json", exclude={"event_hash"})
        return f"sha256:{hashlib.sha256(canonical_json_bytes(material)).hexdigest()}"

    def has_valid_hash(self) -> bool:
        return hmac.compare_digest(self.event_hash, self.compute_hash())
