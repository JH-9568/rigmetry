from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from rigmetry.models import (
    ModelAdapter,
    ModelMessage,
    ModelRequest,
    ModelResult,
    ProviderCapabilities,
    TokenTotalSource,
    TokenUsage,
)
from rigmetry.tracing import EventType, TraceEvent


def test_unknown_token_usage_stays_null_and_calculated_total_has_a_source() -> None:
    unknown = TokenUsage()
    calculated = TokenUsage(
        input_tokens=8,
        output_tokens=2,
        total_tokens=10,
        total_tokens_source=TokenTotalSource.CALCULATED,
    )

    assert unknown.model_dump() == {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens_source": None,
    }
    assert calculated.total_tokens == 10

    with pytest.raises(ValidationError):
        TokenUsage(total_tokens=10)


def test_model_contract_exposes_capabilities_without_accepting_credentials() -> None:
    class FakeAdapter:
        capabilities = ProviderCapabilities(tool_calling=True, token_usage=True)

        async def complete(self, request: ModelRequest) -> ModelResult:
            return ModelResult(message=ModelMessage(role="assistant", content=request.model))

    assert isinstance(FakeAdapter(), ModelAdapter)

    with pytest.raises(ValidationError):
        ModelRequest(model="example", messages=(), api_key="secret")


def test_event_hash_is_canonical_and_detects_changed_payload() -> None:
    timestamp = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)
    first = TraceEvent.create(
        run_id="run-1",
        sequence=0,
        type=EventType.RUN_STARTED,
        timestamp=timestamp,
        payload={"z": 1, "nested": {"b": True, "a": None}},
    )
    same_content = TraceEvent.create(
        run_id="run-1",
        sequence=0,
        type=EventType.RUN_STARTED,
        timestamp=timestamp,
        payload={"nested": {"a": None, "b": True}, "z": 1},
    )
    second = TraceEvent.create(
        run_id="run-1",
        sequence=1,
        type=EventType.STEP_STARTED,
        timestamp=timestamp,
        previous_event_hash=first.event_hash,
    )

    assert first.event_hash == same_content.event_hash
    assert first.has_valid_hash()
    assert second.previous_event_hash == first.event_hash
    assert second.has_valid_hash()

    changed = first.model_copy(update={"payload": {"z": 2}})
    assert not changed.has_valid_hash()


def test_event_timestamp_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError):
        TraceEvent.create(
            run_id="run-1",
            sequence=0,
            type=EventType.RUN_STARTED,
            timestamp=datetime(2026, 8, 21, 9, 0),
        )
