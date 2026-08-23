"""Offline Replay에 필요한 경계 호출 Transcript 계약."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from rigmetry.models import EvaluatorResult, ModelRequest, ModelResult, ToolCall, ToolResult
from rigmetry.models.contracts import ContractModel


class BoundaryKind(StrEnum):
    MODEL = "model"
    TOOL = "tool"
    EVALUATOR = "evaluator"


class ModelBoundary(ContractModel):
    sequence: int = Field(ge=0)
    kind: Literal[BoundaryKind.MODEL] = BoundaryKind.MODEL
    request: ModelRequest
    result: ModelResult | None = None
    error_code: str | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> ModelBoundary:
        if (self.result is None) == (self.error_code is None):
            raise ValueError("Model 경계에는 result 또는 error_code 중 하나만 필요합니다")
        return self


class ToolBoundary(ContractModel):
    sequence: int = Field(ge=0)
    kind: Literal[BoundaryKind.TOOL] = BoundaryKind.TOOL
    request: ToolCall
    result: ToolResult | None = None
    error_code: str | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> ToolBoundary:
        if (self.result is None) == (self.error_code is None):
            raise ValueError("Tool 경계에는 result 또는 error_code 중 하나만 필요합니다")
        return self


RuntimeBoundary = ModelBoundary | ToolBoundary


class EvaluatorBoundary(ContractModel):
    sequence: int = Field(ge=0)
    kind: Literal[BoundaryKind.EVALUATOR] = BoundaryKind.EVALUATOR
    result: EvaluatorResult


StoredBoundary = ModelBoundary | ToolBoundary | EvaluatorBoundary
