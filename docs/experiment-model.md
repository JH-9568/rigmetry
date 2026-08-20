# Experiment Model (Draft)

이 문서는 Rigmetry의 핵심 차별점인 Fingerprint, Event Trace, Replay, Token Budget, Harness Compare의 최소 계약을 정의합니다. 구현 과정에서 변경할 수 있지만 서로 다른 모듈이 같은 의미를 사용해야 합니다.

## 식별자와 Digest

다음 값은 서로 다른 목적을 가지며 하나로 합치지 않습니다.

- `run_id`: 개별 실행 식별자. 동일 조건의 반복 Run도 서로 다른 값을 가집니다.
- `harness_digest`: 정규화된 Harness와 참조 Artifact의 content digest
- `task_digest`: Task Config와 평가 대상 revision의 digest
- `environment_digest`: Rigmetry/Python/dependency 및 격리 환경의 digest

비교 Report는 사람이 읽는 `name`과 검증 가능한 digest를 함께 표시해야 합니다.

## Canonicalization 방향

같은 의미의 입력은 같은 digest를 생성해야 합니다.

1. YAML을 검증된 내부 Model로 변환합니다.
2. Default를 명시적으로 적용합니다.
3. Map key를 정렬한 canonical JSON으로 직렬화합니다.
4. Skill, Prompt, Tool Schema와 MCP Capability 같은 참조 Artifact는 내용을 hash합니다.
5. Credential과 실행 시 Secret은 대상에서 제외합니다.
6. SHA-256을 기본 digest algorithm으로 사용합니다.

경로의 절대값처럼 Machine마다 달라지는 값은 그대로 hash하지 않습니다. Path traversal을 방지하면서 이식 가능한 상대 식별자를 사용해야 합니다.

## Event Trace

Event는 append-only이며 최소 envelope는 다음 방향을 따릅니다.

```json
{
  "run_id": "run-123",
  "sequence": 7,
  "type": "tool.completed",
  "timestamp": "2026-08-20T12:00:00Z",
  "payload": {}
}
```

- `sequence`는 Run 안에서 단조 증가합니다.
- `timestamp`는 관측 정보이며 Replay 순서는 `sequence`가 결정합니다.
- `payload`는 Event type별 project-owned Schema를 사용합니다.
- Secret은 Event 생성 또는 저장 경계에서 제거합니다.

최소 Event vocabulary 후보:

```text
run.started
step.started
model.requested
model.completed
tool.requested
tool.completed
step.completed
evaluation.completed
run.finished
run.failed
```

Streaming token delta 전체를 MVP에 저장할지는 저장 비용과 Replay 필요성을 확인한 뒤 결정합니다.

## Token Usage

Provider Adapter는 가능한 값을 다음 공통 형태로 정규화합니다.

```json
{
  "input_tokens": 8400,
  "output_tokens": 2100,
  "total_tokens": 10500,
  "cached_input_tokens": 3200,
  "reasoning_tokens": null
}
```

- Provider가 값을 제공하지 않으면 `0`이 아니라 `null`입니다.
- `total_tokens`를 제공하지 않지만 입력·출력 값이 있으면 합산 여부와 원본/계산 값을 구분해야 합니다.
- Token usage와 통화 비용은 별도 데이터입니다.
- 비용을 계산하면 가격 출처, 통화, 적용 시점을 함께 기록합니다.

## Budget 강제

Runtime은 각 Model 응답 후 누적 usage를 갱신합니다. 누적 Token이 `max_total_tokens`를 초과하거나 다음 호출이 상한을 넘을 것이 명백한 경우 Run을 `token_budget_exceeded`로 종료합니다.

Provider가 usage를 늦게 보고하므로 상한을 소폭 초과할 수 있습니다. MVP Report는 설정 Budget과 실제 관측 Token을 모두 표시해야 하며 완벽한 사전 차단을 주장하지 않습니다.

## Offline Replay

Offline Replay는 저장된 Model 응답과 Tool 결과를 sequence 순서로 공급해 Runtime의 상태 전이와 Evaluator 입력을 다시 구성합니다.

보장 목표:

- 외부 Model API와 Tool side effect를 다시 호출하지 않음
- 동일 Event 입력에서 동일한 Runtime 결과 생성
- Manifest digest 불일치 탐지

비보장:

- live rerun의 Model 응답 동일성
- 저장하지 않은 외부 side effect 복원
- 변경된 Runtime version에서의 무조건적인 호환성

Replay Report는 외부 호출 수가 0인지와 사용한 Runtime version을 표시해야 합니다.

## 공정한 Harness Compare

한 Experiment 안의 Variant는 다음 조건을 공유해야 합니다.

- `task_digest`
- Workspace revision
- Evaluator와 timeout
- 최대 단계와 wall-clock timeout
- Token Budget
- 반복 횟수

의도적으로 다른 Harness 필드는 Config diff에 표시합니다. Model까지 바꾸는 Experiment는 가능하지만 “Skill만의 효과”처럼 인과 범위를 과장해서는 안 됩니다.

## 집계 지표

### `success@budget`

```text
Budget 안에서 Evaluator를 통과한 Run 수 / 시도한 전체 Run 수
```

Budget 초과, timeout, Model 오류도 시도한 Run에 포함합니다. Infrastructure 자체 오류를 분모에서 제외할지는 오류 분류 정책을 확정할 때 결정하고 Report에 명시해야 합니다.

### `tokens_per_success`

```text
전체 Run의 관측 total tokens 합 / 성공 Run 수
```

성공 Run이 0이면 숫자를 만들지 않고 `null`과 사유를 표시합니다.

### 기타 지표

- 입력·출력·전체 Token의 평균과 중앙값
- 성공 Run의 Token과 단계 수 분포
- Model/Tool 호출 수
- wall-clock 실행 시간
- 종료 사유별 개수

MVP에서 여러 지표를 임의 가중치로 합친 종합 점수는 만들지 않습니다. 성공률, 비용, 시간을 각각 보여주고 Pareto 비교를 우선합니다.

반복 수가 충분할 때 Confidence Interval을 추가할 수 있지만 작은 표본에서 통계적 유의성을 과장하지 않습니다.
