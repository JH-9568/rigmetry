import asyncio
import json

import pytest

from rigmetry.models import (
    MessageRole,
    ModelAdapterError,
    ModelMessage,
    ModelRequest,
    ModelResult,
    ProviderCapabilities,
    RunTerminationReason,
    TokenTotalSource,
    TokenUsage,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from rigmetry.runtime import (
    AgentRuntime,
    RuntimeCapabilityError,
    RuntimeLimits,
    RuntimeRequest,
)
from rigmetry.tracing import EventType

DIGEST = f"sha256:{'0' * 64}"


def _usage(input_tokens: int, output_tokens: int) -> TokenUsage:
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        total_tokens_source=TokenTotalSource.PROVIDER,
    )


def _request(**changes: object) -> RuntimeRequest:
    values = {
        "run_id": "run-1",
        "model": "test-model",
        "system_prompt": "system",
        "prompt": "prompt-secret-that-must-not-enter-events",
        "tools": (ToolDefinition(name="terminal"),),
        "limits": RuntimeLimits(max_steps=3, timeout=1, max_total_tokens=100),
        "harness_digest": DIGEST,
        "task_digest": DIGEST,
        "environment_digest": DIGEST,
    }
    values.update(changes)
    return RuntimeRequest.model_validate(values)


class FakeAdapter:
    name = "fake"
    version = "test"

    def __init__(
        self,
        *results: ModelResult,
        capabilities: ProviderCapabilities | None = None,
    ) -> None:
        self.capabilities = capabilities or ProviderCapabilities(
            tool_calling=True,
            token_usage=True,
            seed=True,
        )
        self.results = list(results)
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        return self.results.pop(0)


def test_fake_adapter_runs_model_tool_model_loop_and_emits_hash_chained_events() -> None:
    call = ToolCall(id="call-1", name="terminal", arguments={"command": "pytest"})
    adapter = FakeAdapter(
        ModelResult(
            message=ModelMessage(role=MessageRole.ASSISTANT),
            tool_calls=(call,),
            usage=_usage(3, 2),
            finish_reason="tool_calls",
            response_model="resolved-model",
            native_model_digest="sha256:native",
        ),
        ModelResult(
            message=ModelMessage(role=MessageRole.ASSISTANT, content="완료"),
            usage=_usage(2, 1),
            finish_reason="stop",
            response_model="resolved-model",
        ),
    )
    handled: list[ToolCall] = []

    async def tool_handler(tool_call: ToolCall) -> ToolResult:
        handled.append(tool_call)
        return ToolResult(call_id=tool_call.id, output="12 passed")

    execution = asyncio.run(AgentRuntime(adapter, tool_handler).run(_request()))

    assert execution.result.termination_reason is RunTerminationReason.COMPLETED
    assert execution.result.steps == 2
    assert execution.result.model_calls == 2
    assert execution.result.tool_calls == 1
    assert execution.result.usage.total_tokens == 8
    assert execution.result.usage.total_tokens_source is TokenTotalSource.AGGREGATED
    assert execution.final_message == ModelMessage(role=MessageRole.ASSISTANT, content="완료")
    assert handled == [call]
    assert adapter.requests[1].messages[-2].tool_calls == (call,)
    assert adapter.requests[1].messages[-1].tool_call_id == "call-1"
    assert adapter.requests[1].messages[-1].tool_name == "terminal"
    assert execution.model_provenance[0].response_model == "resolved-model"
    assert execution.model_provenance[0].adapter_version == "test"

    event_types = [event.type for event in execution.events]
    assert event_types == [
        EventType.RUN_STARTED,
        EventType.STEP_STARTED,
        EventType.MODEL_REQUESTED,
        EventType.MODEL_COMPLETED,
        EventType.TOOL_REQUESTED,
        EventType.TOOL_COMPLETED,
        EventType.STEP_COMPLETED,
        EventType.STEP_STARTED,
        EventType.MODEL_REQUESTED,
        EventType.MODEL_COMPLETED,
        EventType.STEP_COMPLETED,
        EventType.RUN_FINISHED,
    ]
    assert all(event.has_valid_hash() for event in execution.events)
    assert all(
        event.previous_event_hash == execution.events[index - 1].event_hash
        for index, event in enumerate(execution.events[1:], start=1)
    )
    assert "prompt-secret" not in json.dumps(
        [event.model_dump(mode="json") for event in execution.events]
    )


def test_missing_capability_is_rejected_before_adapter_call() -> None:
    adapter = FakeAdapter(
        capabilities=ProviderCapabilities(tool_calling=False, token_usage=False)
    )

    with pytest.raises(RuntimeCapabilityError) as error:
        asyncio.run(AgentRuntime(adapter).run(_request()))

    assert error.value.missing == ("tool_calling", "token_usage")
    assert adapter.requests == []


def test_runtime_distinguishes_step_token_and_timeout_termination() -> None:
    call = ToolCall(id="call-1", name="terminal")

    async def tool_handler(tool_call: ToolCall) -> ToolResult:
        return ToolResult(call_id=tool_call.id, output="ok")

    step_adapter = FakeAdapter(
        ModelResult(
            message=ModelMessage(role=MessageRole.ASSISTANT),
            tool_calls=(call,),
            usage=_usage(1, 1),
        )
    )
    step_execution = asyncio.run(
        AgentRuntime(step_adapter, tool_handler).run(
            _request(limits=RuntimeLimits(max_steps=1, timeout=1, max_total_tokens=100))
        )
    )

    token_adapter = FakeAdapter(
        ModelResult(
            message=ModelMessage(role=MessageRole.ASSISTANT, content="done"),
            usage=_usage(8, 3),
        )
    )
    token_execution = asyncio.run(
        AgentRuntime(token_adapter).run(
            _request(
                tools=(),
                limits=RuntimeLimits(max_steps=1, timeout=1, max_total_tokens=10),
            )
        )
    )

    class SlowAdapter(FakeAdapter):
        async def complete(self, request: ModelRequest) -> ModelResult:
            self.requests.append(request)
            await asyncio.sleep(0.05)
            return ModelResult(
                message=ModelMessage(role=MessageRole.ASSISTANT), usage=_usage(1, 1)
            )

    timeout_adapter = SlowAdapter()
    timeout_execution = asyncio.run(
        AgentRuntime(timeout_adapter).run(
            _request(
                tools=(),
                limits=RuntimeLimits(max_steps=1, timeout=0.001, max_total_tokens=10),
            )
        )
    )

    assert step_execution.result.termination_reason is RunTerminationReason.MAX_STEPS_EXCEEDED
    assert token_execution.result.termination_reason is RunTerminationReason.TOKEN_BUDGET_EXCEEDED
    assert timeout_execution.result.termination_reason is RunTerminationReason.TIMEOUT_EXCEEDED


def test_unreported_token_usage_stays_null_and_stops_budgeted_run() -> None:
    adapter = FakeAdapter(
        ModelResult(
            message=ModelMessage(role=MessageRole.ASSISTANT, content="done"),
            usage=TokenUsage(),
        )
    )

    execution = asyncio.run(AgentRuntime(adapter).run(_request(tools=())))

    assert execution.result.termination_reason is RunTerminationReason.MODEL_ERROR
    assert execution.result.usage.total_tokens is None
    assert execution.events[-1].payload["error_code"] == "token_usage_unavailable"


def test_model_and_tool_errors_are_classified_without_leaking_messages() -> None:
    class ErrorAdapter(FakeAdapter):
        async def complete(self, request: ModelRequest) -> ModelResult:
            self.requests.append(request)
            raise ModelAdapterError("provider_failed", "provider-secret")

    model_execution = asyncio.run(AgentRuntime(ErrorAdapter()).run(_request(tools=())))

    call = ToolCall(id="call-1", name="terminal")
    tool_adapter = FakeAdapter(
        ModelResult(
            message=ModelMessage(role=MessageRole.ASSISTANT),
            tool_calls=(call,),
            usage=_usage(1, 1),
        )
    )

    async def failing_tool(tool_call: ToolCall) -> ToolResult:
        raise RuntimeError(f"tool-secret:{tool_call.name}")

    tool_execution = asyncio.run(AgentRuntime(tool_adapter, failing_tool).run(_request()))

    assert model_execution.result.termination_reason is RunTerminationReason.MODEL_ERROR
    assert model_execution.events[-1].payload["error_code"] == "provider_failed"
    assert tool_execution.result.termination_reason is RunTerminationReason.TOOL_ERROR
    serialized = json.dumps(
        [
            event.model_dump(mode="json")
            for event in (*model_execution.events, *tool_execution.events)
        ]
    )
    assert "provider-secret" not in serialized
    assert "tool-secret" not in serialized
