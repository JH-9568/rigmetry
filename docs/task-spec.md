# Task Specification (Draft)

Task는 Harness Variant를 비교할 Workspace, Agent 지시문, 성공 판정 방법을 정의합니다. 현재 Task Runner와 Evaluator는 아직 구현되지 않았습니다.

## 예시

```yaml
id: login-bug
workspace: ./benchmarks/login-bug
prompt: >
  잘못된 비밀번호로 로그인할 경우 HTTP 401을 반환하도록 수정하라.

evaluator:
  type: command
  command: pytest tests/test_login.py
  timeout: 60
```

## 실행 수명 주기

```text
Task
  → Task digest
  → Isolated Workspace
  → Budgeted Agent Execution
  → Evaluator
  → Run Result
```

1. Task Runner가 Task를 읽고 검증해 `task_digest`를 계산합니다.
2. Workspace Manager가 원본 revision에서 격리된 사본을 만듭니다.
3. Agent Runtime이 정해진 단계·시간·Token Budget 안에서 실행합니다.
4. Evaluator가 변경된 Workspace를 검사합니다.
5. Result와 Trace를 Experiment의 한 Run으로 저장합니다.

Harness 비교에 포함되는 각 Run은 같은 `task_digest`와 Workspace revision을 사용해야 합니다.

## 필드

### `id`

사람이 읽을 Task 이름입니다. `task_digest`를 대신하지 않습니다.

### `workspace`

Task 원본 디렉터리입니다. 상대 경로 기준은 Config Loader 구현 시 확정합니다. Runtime은 허용 root 밖의 경로를 거부하고 격리된 사본에서 실행해야 합니다.

Task digest에 Workspace 전체를 포함할지, Git commit과 Fixture Manifest를 사용할지는 Workspace 구현 Issue에서 결정합니다.

### `prompt`

Agent에 전달할 작업 지시문입니다. Evaluator Secret이나 Provider Credential을 포함하면 안 됩니다.

### `evaluator`

- `type`: Evaluator 구현 선택. MVP는 `command`
- `command`: 격리 Workspace에서 실행할 명령
- `timeout`: Evaluator 최대 실행 시간(초)

Command Evaluator 구현 전에 Process 격리, 출력 크기 제한, exit code 의미와 shell 사용 여부를 명확히 정해야 합니다.

## Result 방향

Result는 최소한 다음을 구분할 예정입니다.

- Agent 실행 성공 여부와 종료 사유
- Evaluator 실행 성공 여부와 Task 판정
- 사용한 Harness/Task/Environment digest
- Token, 호출 수, 단계 수, 실행 시간

정확한 집계 방식은 [Experiment Model](experiment-model.md)을 따릅니다.
