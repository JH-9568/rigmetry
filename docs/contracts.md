# 공통 계약 구현 가이드

이 문서는 Issue #1에서 구현한 Rigmetry의 공통 Python 계약을 설명합니다. Config, Runtime, Workspace, Evaluator와 Replay를 병렬 개발할 때 아래 타입을 직접 사용하고 같은 의미의 타입을 각 Package에 다시 만들지 않습니다.

## 공개 import

```python
from rigmetry.models import (
    EvaluatorResult,
    ModelAdapter,
    ModelRequest,
    ModelResult,
    ProviderCapabilities,
    RunResult,
    RunTerminationReason,
    TokenUsage,
    ToolResult,
)
from rigmetry.tracing import EventType, TraceEvent
```

구현 위치는 `src/rigmetry/models/contracts.py`와 `src/rigmetry/tracing/events.py`입니다. Package 사용자는 내부 파일 경로보다 위 공개 import를 우선합니다.

## 계약 공통 규칙

- 모든 Pydantic 계약은 불변이며 선언하지 않은 필드를 거부합니다.
- Hash 대상 JSON은 UTF-8, 정렬된 Map key, 공백 없는 구분자와 `ensure_ascii=False`로 직렬화합니다.
- SHA-256 digest 문자열은 `sha256:` 접두사와 64자리 소문자 16진수 형식입니다.
- Credential 필드는 공통 요청·결과에 존재하지 않습니다. Adapter 구현이 환경변수에서 읽은 Secret을 요청 Model이나 Event payload에 추가하면 안 됩니다.
- 측정하지 못한 값은 `0`으로 바꾸지 않고 `None`으로 유지합니다.

## Model Adapter 경계

`ModelAdapter`는 Runtime이 Provider 구현 대신 의존하는 최소 Protocol입니다.

```python
class ModelAdapter(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    async def complete(self, request: ModelRequest) -> ModelResult: ...
```

OpenAI-compatible과 Ollama Adapter는 Provider SDK 객체나 원본 응답을 Runtime에 넘기지 않고 `ModelResult`로 정규화해야 합니다. API Key, 인증 Header와 Provider Client 생성 방식은 이 Protocol에 포함하지 않습니다.

Tool loop를 위해 `ModelMessage`는 Provider 중립 `tool_calls`, `tool_call_id`, `tool_name`을 선택적으로 가집니다. OpenAI-compatible Adapter는 call ID를, Ollama Native Adapter는 Tool 이름을 사용해 각 Provider 메시지로 변환합니다.

`ProviderCapabilities`는 실행 가능성의 사전 확인용입니다. `token_usage=True`여도 개별 응답의 모든 Token 항목이 존재한다는 뜻은 아닙니다.

## Replay 경계 결과

Offline Replay가 외부 호출 없이 같은 Runtime 상태 전이를 수행하려면 live 실행 중 다음 경계 결과를 저장해야 합니다.

| 경계 | 요청/결과 계약 | Replay 동작 |
|---|---|---|
| Model | `ModelRequest` / `ModelResult` | 저장한 `ModelResult`를 순서대로 반환 |
| Tool | `ToolCall` / `ToolResult` | Tool을 실행하지 않고 저장한 결과를 반환 |
| Evaluator | `EvaluatorResult` | Command를 실행하지 않고 저장한 판정을 반환 |

현재 계약은 결과 데이터 형태만 정의합니다. Transcript 저장 형식, sequence 일치 검사와 replay Adapter는 Issue #5 범위입니다.

## Token Usage

```json
{
  "input_tokens": 8400,
  "output_tokens": 2100,
  "total_tokens": 10500,
  "cached_input_tokens": null,
  "reasoning_tokens": null,
  "total_tokens_source": "provider"
}
```

`total_tokens`와 `total_tokens_source`는 함께 존재하거나 함께 `null`이어야 합니다. Source가 `calculated`이면 입력·출력 Token이 모두 있어야 하고 전체 값은 두 값의 합이어야 합니다. 나머지 세부 Token은 Provider가 보고한 관측값이며 별도의 추정치를 만들지 않습니다.

여러 Model 호출의 total을 Runtime이 합산한 Run Usage는 Source를 `aggregated`로 기록합니다.

## Event와 hash

`TraceEvent.create(...)`가 timezone-aware timestamp를 UTC로 정규화하고 `event_hash`를 계산합니다. Hash 입력은 `event_hash` 자신을 제외한 다음 필드 전체입니다.

```text
run_id
sequence
type
timestamp
payload
previous_event_hash
```

첫 Event의 `previous_event_hash`는 `None`이고 다음 Event는 직전 `event_hash`를 사용합니다. `has_valid_hash()`는 한 Event의 내용과 hash가 일치하는지만 확인합니다. sequence 연속성, 첫 Event 규칙과 전체 chain 검증은 저장·Replay를 구현하는 Issue #5에서 담당합니다.

`payload`에는 JSON 값만 허용합니다. Event type별 payload Schema와 Secret redaction은 실제 Event 생산자가 추가될 때 해당 Issue에서 확정합니다.

## Run Result와 식별자

`RunResult`는 `run_id`, `harness_digest`, `task_digest`, `environment_digest`를 필수로 갖습니다. Experiment 밖의 단일 실행을 허용하기 위해 `experiment_digest`는 선택 값입니다.

`evidence_digest`는 개별 Run이 아니라 Evidence Bundle 전체의 Manifest에서 계산하는 식별자이므로 `RunResult`에 넣지 않습니다. Evidence 계약과 생성은 Issue #6 범위입니다.

종료 사유는 다음 값을 사용합니다.

```text
completed
max_steps_exceeded
timeout_exceeded
token_budget_exceeded
model_error
tool_error
evaluation_failed
cancelled
```

Budget 초과와 Evaluator 실패는 예외 문자열로만 남기지 않고 비교 가능한 종료 결과로 보존합니다.

## 아직 고정하지 않은 부분

- Config에서 Adapter·Runtime을 생성하는 CLI/Task Runner 연결
- Provider retry와 streaming
- Event type별 payload Schema와 redaction 구현
- SQLite Schema와 전체 Event chain 검증
- Transcript-backed Replay Adapter
- Evidence Manifest와 `evidence_digest` 계산

공통 필드를 변경해야 하면 먼저 Issue #1 의존 Branch에 알리고 계약 테스트와 이 문서를 같은 PR에서 수정합니다.
