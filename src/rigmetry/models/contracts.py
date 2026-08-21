"""Provider와 Runtime 사이에서 공유하는 최소 계약."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Sha256Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class ContractModel(BaseModel):
    """알 수 없는 필드를 거부하는 불변 공통 계약."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def canonical_json_bytes(value: BaseModel | JsonValue) -> bytes:
    """Hash 입력에 사용할 결정적인 UTF-8 JSON을 반환한다."""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


class TokenTotalSource(StrEnum):
    """전체 Token 값의 출처."""

    PROVIDER = "provider"
    CALCULATED = "calculated"
    AGGREGATED = "aggregated"


class TokenUsage(ContractModel):
    """Provider가 관측한 Token 사용량. 미관측 값은 ``None``이다."""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    total_tokens_source: TokenTotalSource | None = None

    @model_validator(mode="after")
    def validate_total_source(self) -> TokenUsage:
        if (self.total_tokens is None) != (self.total_tokens_source is None):
            raise ValueError("total_tokens와 total_tokens_source는 함께 지정해야 합니다")
        if self.total_tokens_source is TokenTotalSource.CALCULATED:
            if self.input_tokens is None or self.output_tokens is None:
                raise ValueError(
                    "계산한 total_tokens에는 input_tokens와 output_tokens가 필요합니다"
                )
            if self.total_tokens != self.input_tokens + self.output_tokens:
                raise ValueError(
                    "계산한 total_tokens는 input_tokens와 output_tokens의 합이어야 합니다"
                )
        return self


class ProviderCapabilities(ContractModel):
    """외부 호출 전에 확인할 수 있는 Adapter 지원 범위."""

    tool_calling: bool = False
    token_usage: bool = False
    cached_token_usage: bool = False
    reasoning_token_usage: bool = False
    seed: bool = False
    native_model_digest: bool = False


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolDefinition(ContractModel):
    name: str
    description: str = ""
    input_schema: dict[str, JsonValue] = Field(default_factory=dict)


class ToolCall(ContractModel):
    id: str
    name: str
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class ModelMessage(ContractModel):
    role: MessageRole
    content: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


class ModelRequest(ContractModel):
    """Runtime이 Adapter에 전달하는 Provider 중립 요청."""

    model: str
    messages: tuple[ModelMessage, ...]
    tools: tuple[ToolDefinition, ...] = ()
    max_output_tokens: int | None = Field(default=None, gt=0)
    temperature: float | None = None
    seed: int | None = None


class ModelResult(ContractModel):
    """Adapter가 정규화해 반환하고 Replay가 다시 공급하는 결과."""

    message: ModelMessage
    tool_calls: tuple[ToolCall, ...] = ()
    usage: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: str | None = None
    response_model: str | None = None
    native_model_digest: str | None = None


class ToolResult(ContractModel):
    """Tool 실행 경계에서 저장할 결과."""

    call_id: str
    output: str
    is_error: bool = False


class EvaluatorResult(ContractModel):
    """Evaluator를 재실행하지 않고 Replay할 수 있는 판정 결과."""

    passed: bool
    exit_code: int | None = None
    output: str | None = None
    timed_out: bool = False


class RunTerminationReason(StrEnum):
    COMPLETED = "completed"
    MAX_STEPS_EXCEEDED = "max_steps_exceeded"
    TIMEOUT_EXCEEDED = "timeout_exceeded"
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"
    MODEL_ERROR = "model_error"
    TOOL_ERROR = "tool_error"
    EVALUATION_FAILED = "evaluation_failed"
    CANCELLED = "cancelled"


class RunResult(ContractModel):
    """Task Runner와 Experiment가 공유하는 개별 Run 결과."""

    run_id: str
    harness_digest: Sha256Digest
    task_digest: Sha256Digest
    environment_digest: Sha256Digest
    experiment_digest: Sha256Digest | None = None
    termination_reason: RunTerminationReason
    evaluator: EvaluatorResult | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    steps: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)


@runtime_checkable
class ModelAdapter(Protocol):
    """Runtime이 구체 Provider 대신 의존하는 최소 Adapter 경계."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    async def complete(self, request: ModelRequest) -> ModelResult: ...
