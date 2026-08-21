import asyncio
import os

import pytest

from rigmetry.models import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    OllamaAdapter,
    OpenAICompatibleAdapter,
)


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RIGMETRY_RUN_OPENAI_INTEGRATION") != "1",
    reason="RIGMETRY_RUN_OPENAI_INTEGRATION=1일 때만 원격 API를 호출합니다",
)
def test_openai_compatible_live() -> None:
    adapter = OpenAICompatibleAdapter(
        base_url=os.environ.get("RIGMETRY_OPENAI_BASE_URL", "https://api.openai.com/v1"),
        api_key_env="RIGMETRY_OPENAI_API_KEY",
    )
    result = asyncio.run(
        adapter.complete(
            ModelRequest(
                model=os.environ["RIGMETRY_OPENAI_MODEL"],
                messages=(ModelMessage(role=MessageRole.USER, content="Reply with OK."),),
                max_output_tokens=16,
            )
        )
    )

    assert result.response_model
    assert result.message.content


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RIGMETRY_RUN_OLLAMA_INTEGRATION") != "1",
    reason="RIGMETRY_RUN_OLLAMA_INTEGRATION=1일 때만 로컬 Ollama를 호출합니다",
)
def test_ollama_native_live() -> None:
    adapter = OllamaAdapter(
        base_url=os.environ.get("RIGMETRY_OLLAMA_BASE_URL", "http://localhost:11434")
    )
    result = asyncio.run(
        adapter.complete(
            ModelRequest(
                model=os.environ["RIGMETRY_OLLAMA_MODEL"],
                messages=(ModelMessage(role=MessageRole.USER, content="Reply with OK."),),
                max_output_tokens=16,
            )
        )
    )

    assert result.response_model
    assert result.message.content
