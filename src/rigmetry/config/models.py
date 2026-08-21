"""Harness, Task와 Experiment 작성 Config Schema."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)


def _reject_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("빈 문자열은 허용하지 않습니다")
    return value


NonEmptyString = Annotated[str, Field(min_length=1), AfterValidator(_reject_blank)]


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _validate_relative_reference(value: str) -> str:
    if Path(value).is_absolute():
        raise ValueError("절대 경로는 허용하지 않습니다")
    if not value.strip():
        raise ValueError("빈 경로는 허용하지 않습니다")
    return Path(value).as_posix()


class ModelConfig(ConfigModel):
    provider: Literal["openai-compatible", "ollama"]
    model: NonEmptyString
    base_url: str | None = None
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Z_][A-Z0-9_]*$")

    @field_validator("base_url")
    @classmethod
    def reject_credentials_in_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url은 http 또는 https URL이어야 합니다")
        if parsed.username or parsed.password:
            raise ValueError("base_url에 Credential을 포함할 수 없습니다")
        secret_words = {"api_key", "apikey", "key", "password", "secret", "token"}
        if any(key.lower() in secret_words for key, _ in parse_qsl(parsed.query)):
            raise ValueError("base_url query에 Credential을 포함할 수 없습니다")
        return value


class ToolConfig(ConfigModel):
    name: NonEmptyString
    description: str = ""
    input_schema: dict[str, JsonValue] = Field(default_factory=dict)


class McpConfig(ConfigModel):
    name: NonEmptyString
    capabilities: dict[str, JsonValue] = Field(default_factory=dict)


class RuntimeConfig(ConfigModel):
    max_steps: int = Field(gt=0)
    timeout: int = Field(gt=0)
    max_total_tokens: int = Field(gt=0)


class HarnessConfig(ConfigModel):
    name: NonEmptyString
    model: ModelConfig
    system_prompt: NonEmptyString
    mcps: tuple[McpConfig, ...] = ()
    tools: tuple[ToolConfig, ...] = ()
    skills: tuple[str, ...] = ()
    runtime: RuntimeConfig

    @field_validator("mcps", "tools", mode="before")
    @classmethod
    def expand_named_references(cls, value: object) -> object:
        if not isinstance(value, list | tuple):
            return value
        return [{"name": item} if isinstance(item, str) else item for item in value]

    @field_validator("skills")
    @classmethod
    def validate_skill_references(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_validate_relative_reference(item) for item in value)


class EvaluatorConfig(ConfigModel):
    type: Literal["command"]
    command: NonEmptyString
    timeout: int = Field(gt=0)


class TaskConfig(ConfigModel):
    id: NonEmptyString
    workspace: str
    prompt: NonEmptyString
    evaluator: EvaluatorConfig

    @field_validator("workspace")
    @classmethod
    def validate_workspace_reference(cls, value: str) -> str:
        return _validate_relative_reference(value)


ControlPath = Literal[
    "task",
    "harness.model",
    "harness.mcps",
    "harness.tools",
    "harness.skills",
    "harness.system_prompt",
    "harness.runtime",
]


class ExperimentControls(ConfigModel):
    require_same: tuple[ControlPath, ...] = ()
    allow_diff: tuple[ControlPath, ...] = ()

    @field_validator("require_same", "allow_diff")
    @classmethod
    def normalize_control_paths(cls, value: tuple[ControlPath, ...]) -> tuple[ControlPath, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Experiment control 경로를 중복 지정할 수 없습니다")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def reject_conflicting_controls(self) -> ExperimentControls:
        overlap = set(self.require_same) & set(self.allow_diff)
        if overlap:
            names = ", ".join(sorted(overlap))
            raise ValueError(f"require_same과 allow_diff가 겹칩니다: {names}")
        return self


class ExperimentTrials(ConfigModel):
    count: int = Field(gt=0)
    order: Literal["randomized"]
    seed: int | None = None


class ExperimentConfig(ConfigModel):
    id: NonEmptyString
    task: str
    variants: dict[str, str] = Field(min_length=2)
    controls: ExperimentControls
    trials: ExperimentTrials
    metrics: tuple[NonEmptyString, ...] = ()

    @field_validator("task")
    @classmethod
    def validate_task_reference(cls, value: str) -> str:
        return _validate_relative_reference(value)

    @field_validator("variants")
    @classmethod
    def validate_variant_references(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not name.strip() for name in value):
            raise ValueError("Variant 이름은 비어 있을 수 없습니다")
        return {name: _validate_relative_reference(reference) for name, reference in value.items()}


ProjectConfig = HarnessConfig | TaskConfig | ExperimentConfig
