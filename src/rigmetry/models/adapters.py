"""OpenAI-compatible과 Ollama Native Model Adapter."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from rigmetry import __version__
from rigmetry.models.contracts import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelResult,
    ProviderCapabilities,
    TokenTotalSource,
    TokenUsage,
    ToolCall,
)


class ModelAdapterError(RuntimeError):
    """Provider 원문이나 Credential을 포함하지 않는 Adapter 오류."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class JsonTransport(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: Mapping[str, Any] | None,
        timeout: float,
    ) -> dict[str, Any]: ...


class UrllibJsonTransport:
    """추가 HTTP dependency 없이 JSON API를 호출하는 기본 Transport."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: Mapping[str, Any] | None,
        timeout: float,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._request,
            method,
            url,
            dict(headers),
            dict(body) if body is not None else None,
            timeout,
        )

    @staticmethod
    def _request(
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any] | None,
        timeout: float,
    ) -> dict[str, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                value = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise ModelAdapterError(
                "http_error", f"Model Provider가 HTTP {error.code}을 반환했습니다"
            ) from error
        except (TimeoutError, URLError) as error:
            raise ModelAdapterError(
                "connection_error", "Model Provider에 연결할 수 없습니다"
            ) from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ModelAdapterError(
                "invalid_response", "Model Provider 응답이 JSON이 아닙니다"
            ) from error
        if not isinstance(value, dict):
            raise ModelAdapterError(
                "invalid_response", "Model Provider 응답은 JSON object여야 합니다"
            )
        return value


def _authorization_headers(api_key_env: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key_env is None:
        return headers
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ModelAdapterError(
            "missing_credential", f"환경변수 {api_key_env}가 설정되지 않았습니다"
        )
    headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ModelAdapterError("invalid_config", "base_url은 HTTP(S) URL이어야 합니다")
    if parsed.username or parsed.password:
        raise ModelAdapterError("invalid_config", "base_url에 Credential을 포함할 수 없습니다")
    return value.rstrip("/")


def _function_tools(request: ModelRequest) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
        for tool in request.tools
    ]


def _parse_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise ModelAdapterError(
                "invalid_tool_arguments", "Model이 유효하지 않은 Tool arguments를 반환했습니다"
            ) from error
    if not isinstance(value, dict):
        raise ModelAdapterError(
            "invalid_tool_arguments", "Tool arguments는 JSON object여야 합니다"
        )
    return value


def _optional_count(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ModelAdapterError("invalid_response", f"{field}는 0 이상의 정수여야 합니다")
    return value


def _token_usage(
    *,
    input_tokens: Any,
    output_tokens: Any,
    total_tokens: Any,
    cached_input_tokens: Any = None,
    reasoning_tokens: Any = None,
) -> TokenUsage:
    input_count = _optional_count(input_tokens, "input_tokens")
    output_count = _optional_count(output_tokens, "output_tokens")
    total_count = _optional_count(total_tokens, "total_tokens")
    source = TokenTotalSource.PROVIDER if total_count is not None else None
    if total_count is None and input_count is not None and output_count is not None:
        total_count = input_count + output_count
        source = TokenTotalSource.CALCULATED
    return TokenUsage(
        input_tokens=input_count,
        output_tokens=output_count,
        total_tokens=total_count,
        cached_input_tokens=_optional_count(cached_input_tokens, "cached_input_tokens"),
        reasoning_tokens=_optional_count(reasoning_tokens, "reasoning_tokens"),
        total_tokens_source=source,
    )


class OpenAICompatibleAdapter:
    """OpenAI Chat Completions 형식의 원격 Provider Adapter."""

    name = "openai-compatible"
    version = __version__
    capabilities = ProviderCapabilities(
        tool_calling=True,
        token_usage=True,
        cached_token_usage=True,
        reasoning_token_usage=True,
        seed=True,
    )

    def __init__(
        self,
        *,
        base_url: str = "https://api.openai.com/v1",
        api_key_env: str = "OPENAI_API_KEY",
        timeout: float = 60,
        transport: JsonTransport | None = None,
    ) -> None:
        self.base_url = _base_url(base_url)
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.transport = transport or UrllibJsonTransport()

    async def complete(self, request: ModelRequest) -> ModelResult:
        body: dict[str, Any] = {
            "model": request.model,
            "messages": [self._message(message) for message in request.messages],
            "stream": False,
        }
        if request.tools:
            body["tools"] = _function_tools(request)
        if request.max_output_tokens is not None:
            body["max_tokens"] = request.max_output_tokens
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.seed is not None:
            body["seed"] = request.seed
        response = await self.transport.request(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=_authorization_headers(self.api_key_env),
            body=body,
            timeout=self.timeout,
        )
        return self._result(response)

    @staticmethod
    def _message(message: ModelMessage) -> dict[str, Any]:
        value: dict[str, Any] = {"role": message.role.value}
        if message.content is not None:
            value["content"] = message.content
        if message.role is MessageRole.TOOL:
            if not message.tool_call_id:
                raise ModelAdapterError(
                    "invalid_request", "Tool message에 tool_call_id가 필요합니다"
                )
            value["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            value["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        return value

    @staticmethod
    def _result(response: dict[str, Any]) -> ModelResult:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ModelAdapterError("invalid_response", "응답에 choices[0]이 없습니다")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ModelAdapterError("invalid_response", "응답에 assistant message가 없습니다")
        calls = OpenAICompatibleAdapter._tool_calls(message.get("tool_calls"))
        usage = response.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        input_details = usage.get("prompt_tokens_details")
        input_details = input_details if isinstance(input_details, dict) else {}
        output_details = usage.get("completion_tokens_details")
        output_details = output_details if isinstance(output_details, dict) else {}
        result_message = ModelMessage(
            role=MessageRole.ASSISTANT,
            content=message.get("content") if isinstance(message.get("content"), str) else None,
            tool_calls=calls,
        )
        return ModelResult(
            message=result_message,
            tool_calls=calls,
            usage=_token_usage(
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                cached_input_tokens=input_details.get("cached_tokens"),
                reasoning_tokens=output_details.get("reasoning_tokens"),
            ),
            finish_reason=choice.get("finish_reason")
            if isinstance(choice.get("finish_reason"), str)
            else None,
            response_model=(
                response.get("model") if isinstance(response.get("model"), str) else None
            ),
        )

    @staticmethod
    def _tool_calls(value: Any) -> tuple[ToolCall, ...]:
        if value is None:
            return ()
        if not isinstance(value, list):
            raise ModelAdapterError("invalid_response", "tool_calls는 list여야 합니다")
        calls = []
        for item in value:
            function = item.get("function") if isinstance(item, dict) else None
            if not isinstance(function, dict) or not isinstance(item.get("id"), str):
                raise ModelAdapterError("invalid_response", "유효하지 않은 Tool call 응답입니다")
            name = function.get("name")
            if not isinstance(name, str):
                raise ModelAdapterError("invalid_response", "Tool call name이 없습니다")
            calls.append(
                ToolCall(
                    id=item["id"],
                    name=name,
                    arguments=_parse_arguments(function.get("arguments")),
                )
            )
        return tuple(calls)


class OllamaAdapter:
    """Ollama Native `/api/chat` Adapter."""

    name = "ollama"
    version = __version__
    capabilities = ProviderCapabilities(
        tool_calling=True,
        token_usage=True,
        seed=True,
        native_model_digest=True,
    )

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        api_key_env: str | None = None,
        timeout: float = 60,
        transport: JsonTransport | None = None,
    ) -> None:
        self.base_url = _base_url(base_url)
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.transport = transport or UrllibJsonTransport()
        self._digests: dict[str, str] = {}

    async def complete(self, request: ModelRequest) -> ModelResult:
        headers = _authorization_headers(self.api_key_env)
        native_digest = await self._model_digest(request.model, headers)
        body: dict[str, Any] = {
            "model": request.model,
            "messages": [self._message(message) for message in request.messages],
            "stream": False,
        }
        if request.tools:
            body["tools"] = _function_tools(request)
        options: dict[str, Any] = {}
        if request.max_output_tokens is not None:
            options["num_predict"] = request.max_output_tokens
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.seed is not None:
            options["seed"] = request.seed
        if options:
            body["options"] = options
        response = await self.transport.request(
            "POST",
            f"{self.base_url}/api/chat",
            headers=headers,
            body=body,
            timeout=self.timeout,
        )
        return self._result(response, native_digest)

    async def _model_digest(self, model: str, headers: Mapping[str, str]) -> str | None:
        if model in self._digests:
            return self._digests[model]
        try:
            response = await self.transport.request(
                "GET",
                f"{self.base_url}/api/tags",
                headers=headers,
                body=None,
                timeout=self.timeout,
            )
        except ModelAdapterError:
            return None
        models = response.get("models")
        if not isinstance(models, list):
            return None
        for item in models:
            if not isinstance(item, dict) or model not in {item.get("name"), item.get("model")}:
                continue
            digest = item.get("digest")
            if isinstance(digest, str):
                normalized = digest if digest.startswith("sha256:") else f"sha256:{digest}"
                self._digests[model] = normalized
                return normalized
        return None

    @staticmethod
    def _message(message: ModelMessage) -> dict[str, Any]:
        value: dict[str, Any] = {"role": message.role.value, "content": message.content or ""}
        if message.role is MessageRole.TOOL:
            if not message.tool_name:
                raise ModelAdapterError("invalid_request", "Tool message에 tool_name이 필요합니다")
            value["tool_name"] = message.tool_name
        if message.tool_calls:
            value["tool_calls"] = [
                {
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.arguments,
                    },
                }
                for call in message.tool_calls
            ]
        return value

    @staticmethod
    def _result(response: dict[str, Any], native_digest: str | None) -> ModelResult:
        message = response.get("message")
        if not isinstance(message, dict):
            raise ModelAdapterError("invalid_response", "응답에 assistant message가 없습니다")
        calls = OllamaAdapter._tool_calls(message.get("tool_calls"))
        result_message = ModelMessage(
            role=MessageRole.ASSISTANT,
            content=message.get("content") if isinstance(message.get("content"), str) else None,
            tool_calls=calls,
        )
        return ModelResult(
            message=result_message,
            tool_calls=calls,
            usage=_token_usage(
                input_tokens=response.get("prompt_eval_count"),
                output_tokens=response.get("eval_count"),
                total_tokens=None,
            ),
            finish_reason=response.get("done_reason")
            if isinstance(response.get("done_reason"), str)
            else None,
            response_model=(
                response.get("model") if isinstance(response.get("model"), str) else None
            ),
            native_model_digest=native_digest,
        )

    @staticmethod
    def _tool_calls(value: Any) -> tuple[ToolCall, ...]:
        if value is None:
            return ()
        if not isinstance(value, list):
            raise ModelAdapterError("invalid_response", "tool_calls는 list여야 합니다")
        calls = []
        for index, item in enumerate(value):
            function = item.get("function") if isinstance(item, dict) else None
            if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                raise ModelAdapterError("invalid_response", "유효하지 않은 Tool call 응답입니다")
            call_id = item.get("id") if isinstance(item.get("id"), str) else f"ollama-call-{index}"
            calls.append(
                ToolCall(
                    id=call_id,
                    name=function["name"],
                    arguments=_parse_arguments(function.get("arguments")),
                )
            )
        return tuple(calls)
