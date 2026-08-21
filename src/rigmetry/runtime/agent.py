"""Provider 중립 Budgeted Agent Runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import perf_counter

from pydantic import Field

from rigmetry.models import (
    MessageRole,
    ModelAdapter,
    ModelAdapterError,
    ModelMessage,
    ModelRequest,
    ProviderCapabilities,
    RunResult,
    RunTerminationReason,
    Sha256Digest,
    TokenTotalSource,
    TokenUsage,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from rigmetry.models.contracts import ContractModel
from rigmetry.tracing import EventType, TraceEvent

ToolHandler = Callable[[ToolCall], Awaitable[ToolResult]]


class RuntimeCapabilityError(ValueError):
    """외부 호출 전에 발견한 Adapter Capability 불일치."""

    def __init__(self, missing: tuple[str, ...]) -> None:
        self.missing = missing
        super().__init__("Adapter가 필요한 Capability를 지원하지 않습니다: " + ", ".join(missing))


class RuntimeLimits(ContractModel):
    max_steps: int = Field(gt=0)
    timeout: float = Field(gt=0)
    max_total_tokens: int = Field(gt=0)


class RuntimeRequest(ContractModel):
    run_id: str
    model: str
    system_prompt: str
    prompt: str
    tools: tuple[ToolDefinition, ...] = ()
    limits: RuntimeLimits
    harness_digest: Sha256Digest
    task_digest: Sha256Digest
    environment_digest: Sha256Digest
    experiment_digest: Sha256Digest | None = None
    max_output_tokens: int | None = Field(default=None, gt=0)
    temperature: float | None = None
    seed: int | None = None
    required_capabilities: ProviderCapabilities = Field(default_factory=ProviderCapabilities)


class ModelProvenance(ContractModel):
    adapter_name: str
    adapter_version: str
    requested_model: str
    response_model: str | None = None
    native_model_digest: str | None = None


class RuntimeExecution(ContractModel):
    result: RunResult
    final_message: ModelMessage | None = None
    events: tuple[TraceEvent, ...]
    model_provenance: tuple[ModelProvenance, ...] = ()


class _EventLog:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.events: list[TraceEvent] = []

    def emit(self, type: EventType, payload: dict[str, object] | None = None) -> None:
        previous = self.events[-1].event_hash if self.events else None
        event = TraceEvent.create(
            run_id=self.run_id,
            sequence=len(self.events),
            type=type,
            timestamp=datetime.now(UTC),
            payload=payload or {},
            previous_event_hash=previous,
        )
        self.events.append(event)


def _sum_known(usages: list[TokenUsage], field: str) -> int | None:
    values = [getattr(usage, field) for usage in usages]
    if not values or any(value is None for value in values):
        return None
    return sum(values)


def _aggregate_usage(usages: list[TokenUsage]) -> TokenUsage:
    if not usages:
        return TokenUsage()
    if len(usages) == 1:
        return usages[0]
    input_tokens = _sum_known(usages, "input_tokens")
    output_tokens = _sum_known(usages, "output_tokens")
    total_tokens = _sum_known(usages, "total_tokens")
    source = None
    if total_tokens is not None:
        source = TokenTotalSource.AGGREGATED
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=_sum_known(usages, "cached_input_tokens"),
        reasoning_tokens=_sum_known(usages, "reasoning_tokens"),
        total_tokens_source=source,
    )


class AgentRuntime:
    """Model turn과 Tool 결과만 조정하는 최소 Agent Loop."""

    def __init__(self, adapter: ModelAdapter, tool_handler: ToolHandler | None = None) -> None:
        self.adapter = adapter
        self.tool_handler = tool_handler

    def _validate_capabilities(self, request: RuntimeRequest) -> None:
        required = request.required_capabilities.model_dump()
        required["token_usage"] = True
        if request.tools:
            required["tool_calling"] = True
        if request.seed is not None:
            required["seed"] = True
        missing = tuple(
            name
            for name, needed in required.items()
            if needed and not getattr(self.adapter.capabilities, name)
        )
        if missing:
            raise RuntimeCapabilityError(missing)

    async def run(self, request: RuntimeRequest) -> RuntimeExecution:
        self._validate_capabilities(request)
        started = perf_counter()
        log = _EventLog(request.run_id)
        usages: list[TokenUsage] = []
        provenance: list[ModelProvenance] = []
        messages = [
            ModelMessage(role=MessageRole.SYSTEM, content=request.system_prompt),
            ModelMessage(role=MessageRole.USER, content=request.prompt),
        ]
        steps = 0
        model_calls = 0
        tool_calls = 0

        log.emit(
            EventType.RUN_STARTED,
            {
                "adapter_name": self.adapter.name,
                "adapter_version": self.adapter.version,
                "requested_model": request.model,
                "max_steps": request.limits.max_steps,
                "timeout": request.limits.timeout,
                "max_total_tokens": request.limits.max_total_tokens,
            },
        )

        def finish(
            reason: RunTerminationReason,
            *,
            final_message: ModelMessage | None = None,
            error_code: str | None = None,
        ) -> RuntimeExecution:
            usage = _aggregate_usage(usages)
            payload: dict[str, object] = {"termination_reason": reason.value}
            if error_code is not None:
                payload["error_code"] = error_code
            event_type = (
                EventType.RUN_FAILED
                if reason in {RunTerminationReason.MODEL_ERROR, RunTerminationReason.TOOL_ERROR}
                else EventType.RUN_FINISHED
            )
            log.emit(event_type, payload)
            result = RunResult(
                run_id=request.run_id,
                harness_digest=request.harness_digest,
                task_digest=request.task_digest,
                environment_digest=request.environment_digest,
                experiment_digest=request.experiment_digest,
                termination_reason=reason,
                usage=usage,
                steps=steps,
                model_calls=model_calls,
                tool_calls=tool_calls,
                duration_ms=max(0, int((perf_counter() - started) * 1000)),
            )
            return RuntimeExecution(
                result=result,
                final_message=final_message,
                events=tuple(log.events),
                model_provenance=tuple(provenance),
            )

        try:
            async with asyncio.timeout(request.limits.timeout):
                for step in range(1, request.limits.max_steps + 1):
                    steps = step
                    log.emit(EventType.STEP_STARTED, {"step": step})
                    model_request = ModelRequest(
                        model=request.model,
                        messages=tuple(messages),
                        tools=request.tools,
                        max_output_tokens=request.max_output_tokens,
                        temperature=request.temperature,
                        seed=request.seed,
                    )
                    log.emit(
                        EventType.MODEL_REQUESTED,
                        {
                            "step": step,
                            "message_count": len(messages),
                            "tool_count": len(request.tools),
                        },
                    )
                    model_calls += 1
                    model_result = await self.adapter.complete(model_request)
                    usages.append(model_result.usage)
                    cumulative = _aggregate_usage(usages)
                    provenance.append(
                        ModelProvenance(
                            adapter_name=self.adapter.name,
                            adapter_version=self.adapter.version,
                            requested_model=request.model,
                            response_model=model_result.response_model,
                            native_model_digest=model_result.native_model_digest,
                        )
                    )
                    log.emit(
                        EventType.MODEL_COMPLETED,
                        {
                            "step": step,
                            "response_model": model_result.response_model,
                            "native_model_digest": model_result.native_model_digest,
                            "finish_reason": model_result.finish_reason,
                            "tool_call_count": len(model_result.tool_calls),
                            "usage": model_result.usage.model_dump(mode="json"),
                        },
                    )
                    if cumulative.total_tokens is None:
                        log.emit(EventType.STEP_COMPLETED, {"step": step})
                        return finish(
                            RunTerminationReason.MODEL_ERROR,
                            error_code="token_usage_unavailable",
                        )
                    if cumulative.total_tokens > request.limits.max_total_tokens:
                        log.emit(EventType.STEP_COMPLETED, {"step": step})
                        return finish(RunTerminationReason.TOKEN_BUDGET_EXCEEDED)
                    if not model_result.tool_calls:
                        log.emit(EventType.STEP_COMPLETED, {"step": step})
                        return finish(
                            RunTerminationReason.COMPLETED,
                            final_message=model_result.message,
                        )
                    if self.tool_handler is None:
                        return finish(
                            RunTerminationReason.TOOL_ERROR,
                            error_code="tool_handler_unavailable",
                        )

                    messages.append(
                        model_result.message.model_copy(
                            update={"tool_calls": model_result.tool_calls}
                        )
                    )
                    for call in model_result.tool_calls:
                        log.emit(
                            EventType.TOOL_REQUESTED,
                            {"step": step, "call_id": call.id, "tool_name": call.name},
                        )
                        tool_calls += 1
                        try:
                            tool_result = await self.tool_handler(call)
                        except Exception:
                            return finish(
                                RunTerminationReason.TOOL_ERROR,
                                error_code="tool_execution_failed",
                            )
                        if tool_result.call_id != call.id:
                            return finish(
                                RunTerminationReason.TOOL_ERROR,
                                error_code="tool_result_mismatch",
                            )
                        log.emit(
                            EventType.TOOL_COMPLETED,
                            {
                                "step": step,
                                "call_id": call.id,
                                "tool_name": call.name,
                                "is_error": tool_result.is_error,
                            },
                        )
                        messages.append(
                            ModelMessage(
                                role=MessageRole.TOOL,
                                content=tool_result.output,
                                tool_call_id=call.id,
                                tool_name=call.name,
                            )
                        )
                    log.emit(EventType.STEP_COMPLETED, {"step": step})
        except TimeoutError:
            return finish(RunTerminationReason.TIMEOUT_EXCEEDED)
        except ModelAdapterError as error:
            return finish(RunTerminationReason.MODEL_ERROR, error_code=error.code)
        return finish(RunTerminationReason.MAX_STEPS_EXCEEDED)
