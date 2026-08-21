# Task Specification (Draft)

Task는 Harness Variant를 비교할 Workspace, Agent 지시문, 성공 판정 방법을 정의합니다. disposable Workspace, Terminal Tool과 Command Evaluator 경계는 구현되어 있으며 Task Runner 연결은 아직 구현되지 않았습니다.

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
  → Disposable Workspace
  → Budgeted Agent Execution
  → Evaluator
  → Run Result
```

1. Task Runner가 Task를 읽고 검증해 `task_digest`를 계산합니다.
2. Workspace Manager가 원본 revision에서 disposable 사본을 만듭니다.
3. Agent Runtime이 정해진 단계·시간·Token Budget 안에서 실행합니다.
4. Evaluator가 변경된 Workspace를 검사합니다.
5. Result와 Trace를 Experiment의 한 Run으로 저장합니다.

Harness 비교에 포함되는 각 Run은 같은 `task_digest`와 Workspace revision을 사용해야 합니다.

## 필드

### `id`

사람이 읽을 Task 이름입니다. `task_digest`를 대신하지 않습니다.

### `workspace`

Task 원본 디렉터리입니다. 상대 경로 기준은 Config Loader 구현 시 확정합니다. Runtime은 Rigmetry가 해석하는 허용 root 밖의 경로를 거부하고 disposable 사본에서 실행해야 합니다.

임시 디렉터리 또는 Git worktree는 원본 보호 수단이며 Shell Process의 시스템 접근을 막는 보안 Sandbox가 아닙니다. Container/VM 격리는 별도 범위입니다.

Task digest에 Workspace 전체를 포함할지, Git commit과 Fixture Manifest를 사용할지는 Workspace 구현 Issue에서 결정합니다.

현재 Config Lock은 Workspace 내부 파일의 상대 경로와 content digest로 Fixture Manifest digest를 계산합니다. `.git`은 제외하고 symlink는 거부합니다. disposable 사본 생성과 Git revision 전략은 Workspace 구현 Issue에서 확장합니다.

### `prompt`

Agent에 전달할 작업 지시문입니다. Evaluator Secret이나 Provider Credential을 포함하면 안 됩니다.

### `evaluator`

- `type`: Evaluator 구현 선택. MVP는 `command`
- `command`: disposable Workspace에서 실행할 명령
- `timeout`: Evaluator 최대 실행 시간(초)

Command Evaluator와 Terminal Tool은 command 문자열을 `shlex`로 나누고 shell 없이 실행합니다. 따라서 pipe, redirect, `&&` 같은 shell 문법은 해석하지 않습니다. 둘은 다음 실행 경계를 공유합니다.

- 실행 작업 디렉터리는 disposable Workspace로 고정
- Runtime과 별도의 Tool/Evaluator timeout
- stdout과 stderr 각각 기본 64 KiB 제한 및 잘림 표시
- stdin 비활성화
- 부모 Process의 전체 환경을 복사하지 않고 `PATH`, locale, 임시 `HOME`/`TMPDIR`만 전달
- timeout 시 Process group 종료

부모 환경을 전달하지 않으므로 Provider Credential을 명령에서 조회할 수 없습니다. 임시 Workspace와 Process 제한은 원본 보호 및 재현성 경계이며 Container/VM 보안 Sandbox가 아닙니다. 실행 명령이 운영체제의 다른 경로에 접근하는 것을 차단하지 않습니다.

## Result 방향

Result는 최소한 다음을 구분할 예정입니다.

- Agent 실행 성공 여부와 종료 사유
- Evaluator 실행 성공 여부와 Task 판정
- 사용한 Harness/Task/Environment digest
- Token, 호출 수, 단계 수, 실행 시간

정확한 집계 방식은 [Experiment Model](experiment-model.md)을 따릅니다.

## 구현 상태

Task Config 검증, Prompt·Workspace Fixture·Evaluator digest와 Task Lock, disposable Workspace lifecycle, Terminal Tool과 Command Evaluator는 구현되어 있습니다. Config에서 Runtime/Adapter를 구성하는 `rigmetry run` Task Runner와 Result/Event 연결은 아직 구현되지 않았습니다.
