# Experiment Model (Draft)

이 문서는 Rigmetry의 핵심 차별점인 content-addressed Lock, 통제된 Experiment, Event Trace, Boundary Replay와 Evidence Bundle의 최소 계약을 정의합니다. 구현 과정에서 변경할 수 있지만 서로 다른 모듈이 같은 의미를 사용해야 합니다. 작성자가 정의하는 비교 단위는 [Experiment Specification](experiment-spec.md)을 따릅니다.

## 식별자와 Digest

다음 값은 서로 다른 목적을 가지며 하나로 합치지 않습니다.

- `run_id`: 개별 실행 식별자. 동일 조건의 반복 Run도 서로 다른 값을 가집니다.
- `harness_digest`: 정규화된 Harness와 참조 Artifact의 content digest
- `task_digest`: Task Config와 평가 대상 revision의 digest
- `environment_digest`: Rigmetry/Python/dependency 및 실행 환경의 digest
- `experiment_digest`: Variant, 통제 조건, 반복 계획과 Metric 정의의 digest
- `evidence_digest`: Evidence Bundle 내부 Manifest가 참조하는 Artifact의 통합 digest

비교 Report는 사람이 읽는 `name`과 검증 가능한 digest를 함께 표시해야 합니다. `evidence_digest`는 Bundle 내부 일관성 검사 값이며 전자서명이나 작성자 신원 보증을 의미하지 않습니다.

## Canonicalization 방향

같은 의미의 입력은 같은 digest를 생성해야 합니다.

1. YAML을 검증된 내부 Model로 변환합니다.
2. Default를 명시적으로 적용합니다.
3. Map key를 정렬한 canonical JSON으로 직렬화합니다.
4. Skill, Prompt, Tool Schema와 MCP Capability 같은 참조 Artifact는 내용을 hash합니다.
5. Credential과 실행 시 Secret은 대상에서 제외합니다.
6. SHA-256을 기본 digest algorithm으로 사용합니다.

경로의 절대값처럼 Machine마다 달라지는 값은 그대로 hash하지 않습니다. Path traversal을 방지하면서 이식 가능한 상대 식별자를 사용해야 합니다.

Lock 범위는 최소한 다음을 구분합니다.

- **Harness Lock**: Model 설정, Prompt, Skill, Tool/MCP Schema, Runtime 제한
- **Task Lock**: Task, Workspace revision 또는 Fixture Manifest, Evaluator
- **Experiment Lock**: Variant, 허용 Diff, 공유 조건, 반복 횟수와 실행 순서
- **Environment Fingerprint**: Rigmetry/Python/dependency/OS 정보와 관측 가능한 Model provenance

외부 Provider의 가변 Model alias나 완전한 실행 환경을 content hash만으로 재현할 수 있다고 주장하지 않습니다. 요청 Model ID, 응답 Model ID, Adapter version과 Provider가 제공한 식별 정보를 관측값으로 함께 기록합니다. Ollama는 제공 가능한 경우 Model tag뿐 아니라 Model digest를 기록합니다.

## Event Trace

Event는 append-only이며 최소 envelope는 다음 방향을 따릅니다.

```json
{
  "run_id": "run-123",
  "sequence": 7,
  "type": "tool.completed",
  "timestamp": "2026-08-20T12:00:00Z",
  "payload": {},
  "previous_event_hash": "sha256:...",
  "event_hash": "sha256:..."
}
```

- `sequence`는 Run 안에서 단조 증가합니다.
- `timestamp`는 관측 정보이며 Replay 순서는 `sequence`가 결정합니다.
- `payload`는 Event type별 project-owned Schema를 사용합니다.
- Secret은 Event 생성 또는 저장 경계에서 제거합니다.
- `event_hash`는 자기 자신을 제외한 canonical Event 필드와 `previous_event_hash`를 hash해 누락, 순서 변경과 비의도적 수정을 검사합니다.

Hash chain은 Bundle의 내부 무결성을 확인하지만 공격자가 전체 Bundle과 기준 digest를 함께 다시 만들지 못하게 하는 전자서명은 아닙니다. 문서와 UI에서 `tamper-proof`라고 표현하지 않습니다.

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
  "reasoning_tokens": null,
  "total_tokens_source": "provider"
}
```

- Provider가 값을 제공하지 않으면 `0`이 아니라 `null`입니다.
- `total_tokens`를 제공하지 않지만 입력·출력 값이 있으면 합산 여부와 원본/계산 값을 구분해야 합니다.
- Token usage와 통화 비용은 별도 데이터입니다.
- 금액 비용은 적용 가능한 원격 Provider에서만 계산하며 가격 출처, 통화와 기준 시점을 함께 기록합니다.
- 서로 다른 Provider 또는 tokenizer의 Token 수를 동일한 단위로 간주해 직접 순위를 만들지 않습니다.

현재 구현된 Pydantic 타입과 Adapter·Replay 연결 방법은 [공통 계약 구현 가이드](contracts.md)를 따릅니다. `total_tokens_source`는 Provider가 보고한 값이면 `provider`, 입력·출력 값을 더한 값이면 `calculated`, 여러 Model 호출의 total을 Runtime이 합산한 값이면 `aggregated`입니다.

## Provider Capability

Adapter는 Runtime과 Experiment가 실행 전 요구사항을 검증할 수 있도록 최소 Capability를 선언합니다.

```json
{
  "tool_calling": true,
  "token_usage": true,
  "cached_token_usage": false,
  "reasoning_token_usage": false,
  "seed": true,
  "native_model_digest": true
}
```

예를 들어 Experiment가 Token Budget 강제를 요구하는데 Adapter가 usage를 보고하지 않으면 시작 전에 설명 가능한 오류로 거부해야 합니다. Capability는 지원 가능성을 나타내며 개별 응답에 값이 항상 존재한다는 보장은 아닙니다.

## Budget 강제

Runtime은 각 Model 응답 후 누적 usage를 갱신합니다. 누적 Token이 `max_total_tokens`를 초과하거나 다음 호출이 상한을 넘을 것이 명백한 경우 Run을 `token_budget_exceeded`로 종료합니다.

Provider가 usage를 늦게 보고하므로 상한을 소폭 초과할 수 있습니다. MVP Report는 설정 Budget과 실제 관측 Token을 모두 표시해야 하며 완벽한 사전 차단을 주장하지 않습니다.

## Offline Replay

Offline Replay는 저장된 Model 응답, Tool 결과와 Evaluator 결과를 Transcript-backed Adapter가 sequence 순서로 공급해 Runtime 상태 전이, 종료 사유와 파생 Metric을 다시 계산합니다. 외부 경계 호출 없이 저장된 결과를 소비하는 것이 핵심이며 원본 Workspace 전체를 복원하는 기능이 아닙니다.

보장 목표:

- 외부 Model API와 Tool side effect를 다시 호출하지 않음
- 저장된 Evaluator 결과를 사용하며 Evaluator Command를 다시 실행하지 않음
- 동일 Transcript와 Runtime version에서 동일한 종료 사유와 파생 Metric 생성
- Manifest digest, Event hash chain과 Runtime version 불일치 탐지

비보장:

- live rerun의 Model 응답 동일성
- 원본 Workspace의 완전한 복구
- 저장하지 않은 외부 side effect 복원
- 변경된 Runtime version에서의 무조건적인 호환성

Replay Report는 Model, Tool과 Evaluator 외부 호출 수가 각각 0인지와 사용한 Runtime version을 표시해야 합니다. Replay는 단순 Event 출력이 아니라 같은 Runtime reducer/state machine을 실행해야 합니다.

## 공정한 Harness Compare

Harness 변경 효과를 해석하는 한 Experiment 안의 Variant는 다음 조건을 공유해야 합니다.

- `task_digest`
- Workspace revision
- Evaluator와 timeout
- 최대 단계와 wall-clock timeout
- Token Budget
- 반복 횟수

Experiment Lock은 `require_same`과 `allow_diff`를 검증합니다. 의도적으로 다른 Harness 필드는 Config diff와 Report에 표시하며 허용하지 않은 차이가 있으면 실행을 거부합니다.

Baseline과 Candidate Run 순서는 무작위화하거나 교차 배치해 시간대와 시스템 상태의 편향을 줄입니다. 배치 seed는 실행 순서를 재현할 뿐 Model 출력을 고정하지 않습니다. 첫 Run 이후 Task, Evaluator, Workspace Fixture 또는 Variant를 변경하면 새 Experiment로 취급합니다.

Model 또는 Provider 자체를 바꾸는 비교는 Harness 변경 실험과 분리합니다. Provider별 결과는 별도 층으로 집계하며 “Skill만의 효과”처럼 인과 범위를 과장해서는 안 됩니다.

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

MVP에서 여러 지표를 임의 가중치로 합친 종합 점수는 만들지 않습니다. 성공률, Token 효율과 시간을 각각 보여주고 Pareto 비교를 우선합니다. 금액 비용은 가격 근거가 있는 Provider에만 선택적으로 표시합니다.

반복 수가 충분할 때 Confidence Interval을 추가할 수 있지만 작은 표본에서 통계적 유의성을 과장하지 않습니다.

## Evidence Bundle

Experiment의 이식 가능한 결과 단위는 다음 방향을 따릅니다.

```text
evidence/
├── manifest.json
├── experiment.lock.json
├── harness-baseline.lock.json
├── harness-candidate.lock.json
├── task.lock.json
├── runs.sqlite
├── report.json
└── report.md
```

`rigmetry verify evidence/` 목표 동작은 다음과 같습니다.

- Manifest와 포함 Artifact digest 일치 확인
- Event sequence와 hash chain 확인
- 계획한 Run 수와 실제 Run/종료 사유의 누락 여부 확인
- Report Metric을 저장된 Run에서 다시 계산해 일치 확인
- `require_same`, `allow_diff` 위반 확인
- Replay 외부 호출 수 0 확인
- 알려진 Secret pattern 검사

검증 성공은 Bundle의 내부 일관성과 정해진 실험 계약 준수를 의미합니다. 외부 Model의 품질, 결과의 통계적 유의성 또는 작성자 신원을 보증하지 않습니다.
