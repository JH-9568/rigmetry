import asyncio
from collections.abc import Mapping
from typing import Any

import pytest

from rigmetry.models import (
    MessageRole,
    ModelAdapter,
    ModelAdapterError,
    ModelMessage,
    ModelRequest,
    OllamaAdapter,
    OpenAICompatibleAdapter,
    TokenTotalSource,
    ToolCall,
    ToolDefinition,
)


class QueueTransport:
    def __init__(self, *responses: dict[str, Any]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: Mapping[str, Any] | None,
        timeout: float,
    ) -> dict[str, Any]:
        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "body": dict(body) if body is not None else None,
                "timeout": timeout,
            }
        )
        return self.responses.pop(0)


def test_openai_compatible_adapter_normalizes_tools_and_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_API_KEY", "runtime-secret")
    transport = QueueTransport(
        {
            "model": "provider-model-2026-08-01",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "terminal",
                                    "arguments": '{"command":"pytest"}',
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "prompt_tokens_details": {"cached_tokens": 3},
                "completion_tokens_details": {"reasoning_tokens": 2},
            },
        }
    )
    adapter = OpenAICompatibleAdapter(
        base_url="https://provider.example/v1",
        api_key_env="TEST_API_KEY",
        transport=transport,
    )
    request = ModelRequest(
        model="requested-model",
        messages=(ModelMessage(role=MessageRole.USER, content="test"),),
        tools=(
            ToolDefinition(
                name="terminal",
                input_schema={"type": "object", "properties": {}},
            ),
        ),
        max_output_tokens=100,
        seed=9568,
    )

    result = asyncio.run(adapter.complete(request))

    assert isinstance(adapter, ModelAdapter)
    assert result.response_model == "provider-model-2026-08-01"
    assert result.tool_calls == (
        ToolCall(id="call-1", name="terminal", arguments={"command": "pytest"}),
    )
    assert result.usage.total_tokens == 15
    assert result.usage.cached_input_tokens == 3
    assert result.usage.reasoning_tokens == 2
    sent = transport.requests[0]
    assert sent["url"] == "https://provider.example/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer runtime-secret"
    assert sent["body"]["max_tokens"] == 100
    assert sent["body"]["seed"] == 9568


def test_ollama_native_adapter_records_digest_and_calculates_total() -> None:
    transport = QueueTransport(
        {
            "models": [
                {
                    "name": "qwen3:8b",
                    "model": "qwen3:8b",
                    "digest": "a" * 64,
                }
            ]
        },
        {
            "model": "qwen3:8b",
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "terminal",
                            "arguments": {"command": "pytest"},
                        }
                    }
                ],
            },
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 12,
            "eval_count": 4,
        },
    )
    adapter = OllamaAdapter(transport=transport)
    request = ModelRequest(
        model="qwen3:8b",
        messages=(ModelMessage(role=MessageRole.USER, content="test"),),
        tools=(ToolDefinition(name="terminal"),),
        max_output_tokens=50,
        temperature=0.2,
        seed=7,
    )

    result = asyncio.run(adapter.complete(request))

    assert isinstance(adapter, ModelAdapter)
    assert [item["method"] for item in transport.requests] == ["GET", "POST"]
    assert transport.requests[1]["url"] == "http://localhost:11434/api/chat"
    assert transport.requests[1]["body"]["options"] == {
        "num_predict": 50,
        "temperature": 0.2,
        "seed": 7,
    }
    assert result.native_model_digest == f"sha256:{'a' * 64}"
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 4
    assert result.usage.total_tokens == 16
    assert result.usage.total_tokens_source is TokenTotalSource.CALCULATED
    assert result.usage.cached_input_tokens is None
    assert result.tool_calls[0].id == "ollama-call-0"


def test_missing_credential_fails_without_an_external_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_KEY", raising=False)
    transport = QueueTransport({})
    adapter = OpenAICompatibleAdapter(api_key_env="MISSING_KEY", transport=transport)
    request = ModelRequest(
        model="model",
        messages=(ModelMessage(role=MessageRole.USER, content="test"),),
    )

    with pytest.raises(ModelAdapterError, match="MISSING_KEY") as error:
        asyncio.run(adapter.complete(request))

    assert error.value.code == "missing_credential"
    assert transport.requests == []

    with pytest.raises(ModelAdapterError, match="Credential"):
        OpenAICompatibleAdapter(base_url="https://user:secret@provider.example/v1")
