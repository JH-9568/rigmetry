"""저장된 경계 결과만 사용하는 Runtime Offline Replay."""

from __future__ import annotations

from pydantic import Field

from rigmetry.models import (
    ModelAdapterError,
    ModelRequest,
    ModelResult,
    ProviderCapabilities,
    RunResult,
    ToolCall,
    ToolResult,
)
from rigmetry.models.contracts import ContractModel
from rigmetry.runtime import RUNTIME_VERSION, AgentRuntime, RuntimeExecution
from rigmetry.storage import RunStore, StoredRun
from rigmetry.tracing import BoundaryKind, ModelBoundary, RuntimeBoundary, ToolBoundary


class ReplayError(ValueError):
    """저장된 Transcript로 같은 Runtime 전이를 만들 수 없음."""


class ExternalCallCounts(ContractModel):
    model: int = Field(default=0, ge=0)
    tool: int = Field(default=0, ge=0)
    evaluator: int = Field(default=0, ge=0)


class ReplayReport(ContractModel):
    run_id: str
    runtime_version: str
    transcript_digest: str
    result: RunResult
    external_calls: ExternalCallCounts = Field(default_factory=ExternalCallCounts)
    metrics_match: bool = True


class _TranscriptPlayer:
    def __init__(self, boundaries: tuple[RuntimeBoundary, ...]) -> None:
        self.boundaries = boundaries
        self.position = 0

    def _next(self, kind: BoundaryKind) -> RuntimeBoundary:
        if self.position >= len(self.boundaries):
            raise ReplayError(f"저장된 {kind.value} 경계 결과가 부족합니다")
        boundary = self.boundaries[self.position]
        if boundary.kind is not kind:
            raise ReplayError(
                f"Boundary 순서가 일치하지 않습니다: {boundary.kind.value}, 기대값 {kind.value}"
            )
        self.position += 1
        return boundary

    async def complete(self, request: ModelRequest) -> ModelResult:
        boundary = self._next(BoundaryKind.MODEL)
        if not isinstance(boundary, ModelBoundary) or boundary.request != request:
            raise ReplayError("저장된 Model 요청이 Replay 요청과 일치하지 않습니다")
        if boundary.error_code == "timeout_exceeded":
            raise TimeoutError
        if boundary.error_code is not None:
            raise ModelAdapterError(boundary.error_code, "저장된 Model 오류")
        if boundary.result is None:
            raise ReplayError("저장된 Model 결과가 없습니다")
        return boundary.result

    async def call_tool(self, call: ToolCall) -> ToolResult:
        boundary = self._next(BoundaryKind.TOOL)
        if not isinstance(boundary, ToolBoundary) or boundary.request != call:
            raise ReplayError("저장된 Tool 요청이 Replay 요청과 일치하지 않습니다")
        if boundary.error_code == "timeout_exceeded":
            raise TimeoutError
        if boundary.error_code is not None:
            raise RuntimeError("저장된 Tool 오류")
        if boundary.result is None:
            raise ReplayError("저장된 Tool 결과가 없습니다")
        return boundary.result

    def ensure_consumed(self) -> None:
        if self.position != len(self.boundaries):
            raise ReplayError("Replay가 저장된 Boundary Transcript 전체를 소비하지 않았습니다")


class _TranscriptAdapter:
    capabilities = ProviderCapabilities(
        tool_calling=True,
        token_usage=True,
        cached_token_usage=True,
        reasoning_token_usage=True,
        seed=True,
        native_model_digest=True,
    )

    def __init__(self, player: _TranscriptPlayer, stored: StoredRun) -> None:
        self.player = player
        if stored.execution.model_provenance:
            first = stored.execution.model_provenance[0]
            self.name = first.adapter_name
            self.version = first.adapter_version
        else:
            started = stored.execution.events[0].payload
            self.name = str(started.get("adapter_name", "transcript"))
            self.version = str(started.get("adapter_version", "unknown"))

    async def complete(self, request: ModelRequest) -> ModelResult:
        return await self.player.complete(request)


def _event_semantics(execution: RuntimeExecution) -> tuple[tuple[object, object], ...]:
    return tuple((event.type, event.payload) for event in execution.events)


def _deterministic_result(result: RunResult) -> tuple[object, ...]:
    return (
        result.run_id,
        result.harness_digest,
        result.task_digest,
        result.environment_digest,
        result.experiment_digest,
        result.termination_reason,
        result.evaluator,
        result.usage,
        result.steps,
        result.model_calls,
        result.tool_calls,
    )


async def replay_stored_run(stored: StoredRun) -> ReplayReport:
    """외부 호출 없이 기존 AgentRuntime을 저장된 결과로 다시 실행한다."""

    if stored.runtime_version != RUNTIME_VERSION:
        raise ReplayError(
            "Runtime version이 일치하지 않습니다: "
            f"저장값 {stored.runtime_version}, 현재값 {RUNTIME_VERSION}"
        )

    player = _TranscriptPlayer(stored.execution.boundaries)
    adapter = _TranscriptAdapter(player, stored)
    has_tool_boundary = any(
        boundary.kind is BoundaryKind.TOOL for boundary in stored.execution.boundaries
    )
    runtime = AgentRuntime(adapter, player.call_tool if has_tool_boundary else None)
    replayed = await runtime.run(stored.request)
    player.ensure_consumed()
    replayed_result = replayed.result.model_copy(
        update={
            "evaluator": stored.evaluator,
            "duration_ms": stored.execution.result.duration_ms,
        }
    )
    replayed = replayed.model_copy(update={"result": replayed_result})

    if _deterministic_result(replayed.result) != _deterministic_result(stored.execution.result):
        raise ReplayError("Replay 종료 사유 또는 파생 Metric이 원본 Run과 일치하지 않습니다")
    if replayed.final_message != stored.execution.final_message:
        raise ReplayError("Replay 최종 Model Message가 원본 Run과 일치하지 않습니다")
    if replayed.model_provenance != stored.execution.model_provenance:
        raise ReplayError("Replay Model provenance가 원본 Run과 일치하지 않습니다")
    if _event_semantics(replayed) != _event_semantics(stored.execution):
        raise ReplayError("Replay Runtime 상태 전이가 원본 Event와 일치하지 않습니다")

    return ReplayReport(
        run_id=stored.request.run_id,
        runtime_version=stored.runtime_version,
        transcript_digest=stored.transcript_digest,
        result=replayed.result,
    )


async def replay_run(store: RunStore, run_id: str) -> ReplayReport:
    return await replay_stored_run(store.load_run(run_id))
