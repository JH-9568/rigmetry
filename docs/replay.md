# SQLite Trace와 Offline Replay 구현 가이드

이 문서는 Issue #5에서 구현한 Run 저장, Event hash chain, Boundary Transcript와
무호출 Runtime Replay 계약을 설명합니다. Task Runner와 Experiment는 자체 Replay
상태 머신을 만들지 않고 이 API를 사용합니다.

## 공개 API

```python
from rigmetry.replay import replay_run
from rigmetry.storage import RunStore

store = RunStore("rigmetry.sqlite3")
stored = store.save_execution(
    runtime_request,
    runtime_execution,
    evaluator=evaluator_result,
    secrets=(runtime_api_key,),
)

report = await replay_run(store, stored.request.run_id)
```

`save_execution()`은 Runtime 요청·결과의 `run_id`와 Harness·Task·Environment·Experiment
digest가 일치하는지 확인한 뒤 하나의 Transaction으로 저장합니다. 같은 `run_id`를
덮어쓰지 않습니다.

## SQLite Schema

MVP Schema version은 `1`이며 표준 라이브러리 `sqlite3`만 사용합니다.

- `runs`: Runtime version, 요청, Result, 최종 Message, Model provenance, Evaluator 결과와 Transcript digest
- `events`: Run별 연속 sequence와 hash를 가진 redacted Event
- `boundaries`: 순서가 고정된 Model·Tool·Evaluator 요청/결과

JSON은 정렬된 key와 공백 없는 UTF-8 canonical 형식으로 저장합니다. `runs`의
`transcript_digest`는 Runtime 요청·결과, Event, Boundary와 Evaluator 결과를 함께
hash하므로 별도 Row의 비의도적 변경을 탐지합니다.

## Boundary Transcript

`AgentRuntime`의 `RuntimeExecution.boundaries`에는 실제 실행 순서대로 다음 값이
추가됩니다.

```text
ModelBoundary(ModelRequest → ModelResult | safe error_code)
ToolBoundary(ToolCall → ToolResult | safe error_code)
```

Evaluator는 Agent Runtime 밖의 경계이므로 `RunStore.save_execution(...,
evaluator=...)`에서 마지막 `EvaluatorBoundary`로 저장합니다. Provider 원본 HTTP
응답, Client 객체와 예외 본문은 저장하지 않습니다.

## Event chain 검증

`validate_event_chain()`은 다음을 모두 확인합니다.

- Event가 하나 이상 존재함
- 모든 Event의 `run_id` 일치
- `sequence`가 `0`부터 빈틈없이 증가함
- 첫 Event의 `previous_event_hash`가 `null`임
- 이후 Event가 직전 `event_hash`를 참조함
- 각 Event를 canonical JSON으로 다시 계산한 hash가 저장값과 일치함

Hash chain은 누락, 순서 변경과 비의도적 수정을 찾는 내부 무결성 장치입니다.
공격자가 DB 전체와 기준 digest를 함께 다시 작성하지 못하게 하는 전자서명은 아닙니다.

## Credential과 redaction

Credential 필드는 `RuntimeRequest`, `ModelResult`와 `RunResult` 계약에 존재하지 않습니다.
저장 전에는 다음 redaction을 추가 적용하고 Event hash chain을 다시 계산합니다.

- `api_key`, `authorization`, `password`, `secret`, `token` 등 민감 key의 값
- Bearer Token, `sk-...`, GitHub Token 형태
- 호출자가 `secrets=`로 전달한 Runtime Credential 값

Task Runner는 Harness의 `api_key_env`가 가리키는 환경변수 값을 DB에 전달하는 것이
아니라 `secrets=` redaction 목록으로만 전달해야 합니다. 임의 형식 Credential은 자동
탐지에 의존하지 말고 반드시 이 목록에 포함합니다. 저장된 redacted Transcript가 Replay
입력이므로 외부 호출은 발생하지 않습니다.

## Offline Replay

```text
SQLite 검증
    ↓
Transcript-backed Model Adapter / Tool Handler
    ↓
기존 AgentRuntime 실행
    ↓
종료 사유·Token·단계·호출 수·Event 상태 전이 비교
    ↓
Evaluator 저장 결과 연결
```

Replay Adapter는 다음 Boundary가 예상 종류와 요청 값까지 정확히 일치할 때만 저장된
결과를 반환합니다. Model·Tool 결과가 부족하거나 남고, 순서나 요청이 다르면 실패합니다.
Evaluator Command는 다시 실행하지 않고 저장된 `EvaluatorResult`만 사용합니다.

검증하는 결정적 결과는 종료 사유, Token usage, 단계 수, Model/Tool 호출 수, 최종
Message, Model provenance와 Event type/payload입니다. `duration_ms`는 Replay 실행 시간을
새 성능 측정값처럼 사용하지 않고 원본 Run의 wall-clock 관측값을 보존합니다.

`ReplayReport.external_calls`의 Model, Tool, Evaluator 값은 모두 `0`이어야 합니다.

## Runtime version

현재 `RUNTIME_VERSION`은 `1`입니다. 저장된 값과 현재 값이 다르면 자동 Migration이나
호환성 추측 없이 Replay를 거부합니다. Runtime 상태 전이가 바뀌는 PR은 version 변경,
이 문서와 Replay 회귀 테스트를 함께 검토해야 합니다.

## CLI

```bash
rigmetry replay RUN_ID --offline --database rigmetry.sqlite3
```

현재 Replay는 `--offline`만 지원합니다. 성공 시 검증한 Result, Transcript digest와 외부
호출 수를 JSON으로 출력합니다. DB를 생성하는 `rigmetry run` 연결은 후속 Task Runner와
Experiment Issue에서 담당합니다.

## 보장하지 않는 범위

- 외부 Provider가 다시 같은 응답을 생성하는 live rerun
- 원본 Workspace와 저장하지 않은 Tool side effect 복구
- Evaluator Command 재실행
- Runtime version 간 자동 호환성
- 전자서명, 작성자 신원 또는 공격자에 대한 위조 방지
