# Model Adapter와 Runtime 구현 가이드

이 문서는 Issue #4에서 구현한 OpenAI-compatible·Ollama Native Adapter와 Budgeted Agent Runtime의 연결 계약을 설명합니다. Task Runner, Tool Manager와 Replay는 Provider별 객체를 직접 다루지 않고 아래 공개 API를 사용합니다.

## 공개 API

```python
from rigmetry.models import OllamaAdapter, OpenAICompatibleAdapter
from rigmetry.runtime import AgentRuntime, RuntimeLimits, RuntimeRequest
```

`AgentRuntime`은 `ModelAdapter` Protocol에만 의존하며 구체 Adapter를 import하지 않습니다. 실제 Tool 연결은 다음 async callback 하나를 주입합니다.

```python
async def tool_handler(call: ToolCall) -> ToolResult:
    ...

runtime = AgentRuntime(adapter, tool_handler)
execution = await runtime.run(request)
```

Issue #3의 Tool Manager는 `ToolCall`을 받아 같은 `call_id`의 `ToolResult`를 반환하면 됩니다. Runtime은 Tool 이름과 arguments의 권한·Schema를 대신 검증하지 않습니다.

## Model Adapter Protocol

```python
class ModelAdapter(Protocol):
    name: str
    version: str
    capabilities: ProviderCapabilities

    async def complete(self, request: ModelRequest) -> ModelResult: ...
```

`name`과 `version`, 요청·응답 Model ID 및 Provider native digest는 `ModelProvenance`에 호출별로 기록됩니다. Provider SDK 객체와 원본 HTTP 응답은 Runtime으로 전달하지 않습니다.

### OpenAI-compatible

```python
adapter = OpenAICompatibleAdapter(
    base_url="https://api.openai.com/v1",
    api_key_env="OPENAI_API_KEY",
)
```

- `POST {base_url}/chat/completions`
- Function Tool Schema와 `tool_call_id` 메시지 흐름 사용
- `prompt_tokens`, `completion_tokens`, `total_tokens` 정규화
- `prompt_tokens_details.cached_tokens`와 `completion_tokens_details.reasoning_tokens`가 있으면 보존
- 광범위한 OpenAI-compatible Endpoint를 위해 출력 제한은 `max_tokens`로 전송

DeepSeek 등 호환 서비스는 `base_url`, Model ID와 환경변수 이름만 바꾸고 별도 Adapter를 만들지 않습니다. Reference: [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat), [OpenAI Function Calling](https://developers.openai.com/api/docs/guides/function-calling).

### Ollama Native

```python
adapter = OllamaAdapter(base_url="http://localhost:11434")
```

- OpenAI 호환 Endpoint가 아닌 `POST /api/chat` 사용
- Tool 결과는 Ollama Native `tool_name` 메시지로 변환
- `prompt_eval_count`를 input, `eval_count`를 output Token으로 정규화
- 두 값이 있으면 `total_tokens`를 계산하고 Source를 `calculated`로 기록
- `GET /api/tags`에서 요청 Model의 digest를 찾아 `sha256:` 형식의 관측 provenance로 기록
- `/api/tags`를 지원하지 않거나 Model을 찾지 못하면 native digest는 `None`이며 Chat 호출은 계속 진행

Reference: [Ollama Chat API](https://docs.ollama.com/api/chat), [Ollama Tool Calling](https://docs.ollama.com/capabilities/tool-calling), [Ollama Model Tags](https://docs.ollama.com/api/tags).

## HTTP와 Credential 경계

기본 Adapter는 Python 표준 라이브러리 HTTP를 `asyncio.to_thread`로 감싸므로 새 Runtime dependency가 없습니다. 테스트에서는 `JsonTransport`를 주입해 실제 네트워크 없이 같은 변환 경계를 검증합니다.

API Key는 `complete()` 호출 시 지정된 환경변수에서만 읽고 Authorization Header에 넣습니다. Key 값은 Config, Lock, `ModelRequest`, `ModelResult`, Event, 오류 메시지에 포함하지 않습니다. HTTP 오류는 상태 코드와 안전한 오류 code만 노출하며 Provider 응답 본문은 보존하지 않습니다.

## Capability 사전 검증

Runtime은 첫 Event와 외부 호출 전에 Capability를 검사합니다.

- Token Budget이 있으므로 `token_usage` 필수
- Tool 목록이 있으면 `tool_calling` 필수
- seed를 요청하면 `seed` 필수
- `required_capabilities`에서 추가로 요구한 항목 필수

누락 시 `RuntimeCapabilityError`를 발생시키며 Adapter 호출 수는 0입니다. Capability가 `true`여도 개별 응답의 값이 항상 존재한다는 뜻은 아닙니다.

## Agent Loop

```text
System + User Message
        ↓
Model Request
        ↓
Tool Call 있음? ── 아니오 ─→ completed
        │
        예
        ↓
주입된 Tool Handler 실행
        ↓
Assistant Tool Call + Tool Result를 Message에 추가
        ↓
다음 Model Step
```

한 Step은 Model 호출 한 번과 그 결과로 요청된 Tool 호출 전체입니다. 여러 Tool call은 MVP에서 순서대로 실행합니다. Tool이 `is_error=True` 결과를 반환하면 그 결과를 Model에 전달해 복구 기회를 주고, callback 자체가 예외를 던지거나 call ID가 다르면 `tool_error`로 종료합니다.

## 제한과 종료 사유

- `max_steps`: 마지막 허용 Step에서도 Tool call 뒤 Final 응답이 없으면 `max_steps_exceeded`
- `timeout`: 전체 Runtime wall-clock 제한이며 초과 시 `timeout_exceeded`
- `max_total_tokens`: 각 응답 뒤 누적 관측 Token을 검사하고 초과 시 `token_budget_exceeded`
- Usage를 보고할 Capability가 있다고 선언했지만 실제 total을 알 수 없으면 `model_error`와 `token_usage_unavailable`

Provider Usage는 응답 뒤 도착하므로 Token 상한을 소폭 넘길 수 있습니다. 완전한 사전 차단을 주장하지 않습니다. 관측하지 못한 input, output, cached, reasoning 값은 계속 `None`이며 `0`으로 바꾸지 않습니다.

단일 호출 total은 Provider 값이면 `provider`, Ollama처럼 input+output으로 계산하면 `calculated`입니다. 여러 호출의 total을 Runtime이 합산한 Run Usage는 `aggregated`로 구분합니다.

## Event와 Secret 최소화

Runtime은 `run.started`, Step, Model, Tool, `run.finished`/`run.failed` Event를 hash chain으로 반환합니다. 현재 Event에는 다음과 같은 구조 정보만 넣습니다.

- Step과 호출 수
- 요청/응답 Model ID와 native digest
- Token Usage
- Tool 이름, call ID와 성공 여부
- 종료 사유와 안전한 오류 code

Prompt, Message content, Tool arguments·output, API Key와 Provider 오류 본문은 Event payload에 넣지 않습니다. Replay용 Boundary Transcript의 저장·redaction Schema는 Issue #5에서 별도로 구현합니다.

## 실제 Provider 테스트

기본 `pytest`는 외부 호출을 하지 않습니다. 명시한 경우에만 integration test를 실행합니다.

```bash
RIGMETRY_RUN_OPENAI_INTEGRATION=1 \
RIGMETRY_OPENAI_API_KEY=... \
RIGMETRY_OPENAI_MODEL=... \
pytest tests/integration/test_providers.py -k openai

RIGMETRY_RUN_OLLAMA_INTEGRATION=1 \
RIGMETRY_OLLAMA_MODEL=qwen3:8b \
pytest tests/integration/test_providers.py -k ollama
```

Key 값은 명령 기록이나 공유 로그에 남기지 말고 실제 개발 환경에서는 shell export 또는 비공개 환경 주입을 사용합니다.

## Terminal Tool 연결

`rigmetry.tools.TerminalTool`은 disposable Workspace 경로에 고정된 async callback이며 `ToolCall`을 `ToolResult`로 변환합니다. 명령은 shell 없이 실행되고 모델이 요청한 timeout은 생성 시 지정한 상한을 넘을 수 없습니다. stdout/stderr는 제한되며 부모 Process의 Credential 환경변수는 전달하지 않습니다.

이 경계는 원본 Workspace 보호와 출력·시간 제한을 제공하지만 Container/VM 보안 Sandbox가 아니며 시스템의 다른 경로 접근을 차단하지 않습니다.

## 아직 구현하지 않은 부분

- `rigmetry run` CLI와 Config→Adapter factory
- retry, streaming과 병렬 Tool 실행
- Config에서 Terminal Tool, Workspace와 Evaluator를 조립하는 Task Runner
- SQLite Event/Boundary Transcript 저장
- Offline Replay와 Compare
