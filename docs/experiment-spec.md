# Experiment Specification (Draft)

Experiment는 하나의 Task에서 Baseline과 Candidate Harness를 통제된 조건으로 반복 실행하고 비교하는 단위입니다. 작성자가 관리하는 `experiment.yaml`과 Rigmetry가 생성할 `experiment.lock.json`은 구분합니다. 세부 Validation 규칙은 구현 Issue에서 확정합니다.

## 예시

```yaml
id: debugging-skill-effect
task: ../tasks/example.yaml

variants:
  baseline: ../harnesses/basic.yaml
  candidate: ../harnesses/basic-with-debugging.yaml

controls:
  require_same:
    - task
    - harness.model
    - harness.mcps
    - harness.tools
    - harness.system_prompt
    - harness.runtime
  allow_diff:
    - harness.skills

trials:
  count: 5
  order: randomized
  seed: 9568

metrics:
  - success_rate
  - total_tokens
  - steps
  - duration
```

## 필드

### `id`

사람이 읽는 Experiment 이름입니다. 생성될 `experiment_digest`를 대신하지 않습니다.

### `task`

모든 Variant가 공유하는 `task.yaml` 경로입니다. Task와 Evaluator, Workspace revision은 Experiment Lock에 포함해야 합니다.

### `variants`

비교할 Harness 이름과 `harness.yaml` 경로의 Map입니다. MVP는 `baseline`과 `candidate` 두 Variant를 우선 지원합니다.

### `controls`

- `require_same`: 비교 Run 전체에서 같아야 하는 composed Lock 경로
- `allow_diff`: 의도적으로 다르게 허용한 composed Lock 경로

경로는 `harness.*`, `task`처럼 Lock namespace를 명시합니다. `task`가 같다는 것은 Task Config, Workspace revision과 Evaluator digest가 같다는 뜻입니다. Lock 단계는 실제 Config diff가 `allow_diff` 밖에 있거나 `require_same` 값이 다르면 실행을 거부해야 합니다. 한 Experiment에서는 한 종류의 Harness 변경 효과만 해석하는 것을 원칙으로 합니다.

Model 또는 Provider 자체를 비교하려면 별도 Experiment로 분리합니다. 서로 다른 tokenizer의 Token 수를 같은 단위처럼 직접 비교하지 않습니다.

### `trials`

- `count`: 각 Variant의 반복 Run 수
- `order`: MVP 목표 값은 `randomized`
- `seed`: Run 배치 순서를 재현하기 위한 선택 값

`seed`는 배치 순서를 재현할 뿐 외부 Model 응답의 결정론을 보장하지 않습니다. Baseline을 모두 실행한 뒤 Candidate를 실행하지 않고 두 Variant 순서를 섞어 시간대와 시스템 상태의 편향을 줄입니다.

### `metrics`

Report에 포함할 Metric 이름입니다. 실제 계산 정의는 [Experiment Model](experiment-model.md)을 따릅니다.

## 실험 동결 원칙

1. 실행 전에 Experiment, Harness, Task와 참조 Artifact를 Lock합니다.
2. 첫 Run 이후 Config, Workspace Fixture 또는 Evaluator가 바뀌면 새 Experiment로 취급합니다.
3. 성공한 Run만 선택하지 않고 시도한 전체 Run과 종료 사유를 보존합니다.
4. Report는 허용된 Config diff와 공유 조건을 함께 표시합니다.
5. 작은 표본에서 인과관계나 통계적 유의성을 과장하지 않습니다.

## 보안 원칙

Credential 값은 Experiment와 Lock에 허용하지 않습니다. Secret은 Harness에 선언한 환경변수 이름을 통해 Runtime에만 주입하며 Evidence Bundle에 저장하지 않습니다.

## 구현 상태

Experiment Parser, Lock, 반복 실행, 무작위 배치와 Compare는 아직 구현되지 않았습니다.
