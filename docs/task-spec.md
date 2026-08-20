# Task Specification (Draft)

Task는 Harness를 평가할 Workspace, Agent 지시문, 성공 판정 방법을 정의합니다. 현재 문서는 MVP 설계 초안이며 Task Runner와 Evaluator는 아직 구현되지 않았습니다.

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
  → Isolated Workspace
  → Agent Execution
  → Evaluator
  → Result
```

1. Task Runner가 Task를 읽고 검증합니다.
2. Workspace Manager가 `workspace`에서 격리된 작업 사본을 만듭니다.
3. Agent Runtime은 `prompt`를 전달받아 격리된 사본 안에서만 작업합니다.
4. Evaluator가 변경된 Workspace를 검사합니다.
5. Task Runner가 Result를 만들고 Run Trace 및 Metrics와 연결합니다.

Run은 원본 Workspace를 변경해서는 안 됩니다. 구체적인 격리 방법은 Workspace 구현 Issue에서 결정합니다.

## 필드

### `id`

Run metadata에서 Task를 구분할 안정적이고 사람이 읽기 쉬운 식별자입니다. 고유성과 versioning 규칙은 아직 확정하지 않습니다.

### `workspace`

Task의 원본 디렉터리입니다. 상대 경로는 Task 파일 위치를 기준으로 해석하는 방향이지만 Config Loader 구현 시 확정해야 합니다. Runtime은 허용된 root 밖으로 벗어나는 경로를 거부하고 격리된 사본에서 실행해야 합니다.

### `prompt`

Agent에 전달할 작업 지시문입니다. Evaluator Secret이나 Provider Credential을 포함하면 안 됩니다.

### `evaluator`

Task 성공을 판정하는 방법입니다.

- `type`: Evaluator 구현 선택. MVP 예시는 `command`
- `command`: 격리된 Workspace에서 실행할 예정인 명령
- `timeout`: Evaluator 최대 실행 시간(초)

Command Evaluator는 아직 구현되지 않았습니다. 임의 Task 파일을 신뢰하기 전에 Process 격리, 출력 크기 제한, exit code 의미, shell 사용 여부를 명확히 정해야 합니다.

## Result 방향

Result는 Agent 실행 실패와 평가 실패를 구분하고, 직렬화 가능하며 Credential이 제거된 데이터만 포함해야 합니다. 정확한 Result 필드와 Score 정책은 Trace, Metrics, Evaluator 계약을 정의할 때 결정합니다.
