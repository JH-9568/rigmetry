# Architecture

Rigmetry는 AI Agent Framework가 아니라 Harness 실험 엔진입니다. Config를 재현 가능한 실행 지문으로 만들고, 제한된 Runtime에서 Event를 기록하며, 동일 조건의 Run을 비교하는 데 초점을 둡니다. 이 문서는 구현 완료 상태가 아닌 의존성 방향을 정의합니다.

## 계획된 흐름

```text
harness.yaml + task.yaml
          ↓
Config Loader / Validator
          ↓
Canonical Manifest / Digest
          ↓
Model Adapter / MCP Manager / Tool Manager / Skill Loader
          ↓
Budgeted Agent Runtime ─────→ Append-only Event Trace
          ↓                              ↓
Isolated Workspace                 SQLite Storage
          ↓                              ↓
Task Runner → Evaluator → Run Result / Metrics
                                  ↓
                   Offline Replay / Harness Compare
```

## 핵심 데이터 경계

### Config와 Lock (`config`)

`harness.yaml`과 `task.yaml`을 읽고 검증합니다. 참조 Artifact의 내용을 정규화하고 digest를 계산해 실행 조건 Manifest를 만듭니다.

작성자가 관리하는 YAML과 Rigmetry가 생성하는 Lock Manifest는 구분합니다. Lock은 Credential을 포함하지 않으며 같은 입력에 같은 digest가 나와야 합니다.

### Model Adapter (`models`)

Provider 중립 요청을 Provider API 형식으로 바꾸고 응답과 Token usage를 프로젝트 내부 타입으로 정규화합니다. Provider SDK 객체, 인증 정보, API 오류가 Runtime 경계를 넘어가면 안 됩니다.

OpenAI-compatible과 DeepSeek는 MVP 기준 대상이지만 공통 Protocol로 처리할 수 있는 부분을 중복 구현하지 않습니다.

### MCP Manager (`mcp`)

MCP Client 연결, capability 탐색, lifecycle과 종료를 담당합니다. Runtime에는 Transport별 Client 객체가 아니라 정규화된 Tool capability를 제공합니다.

### Tool Manager (`tools`)

허용된 Tool 등록, Schema 제공, 호출 검증, 실행 위임과 결과 정규화를 담당합니다. Skill은 Tool 권한을 추가하거나 이 경계를 우회할 수 없습니다.

### Skill Loader (`config`에서 시작)

Skill 파일을 해석하고 내용을 불러와 content digest를 계산합니다. 별도 Package는 실제 책임이 커질 때만 만듭니다.

### Agent Runtime (`runtime`)

Model turn과 Tool 호출을 조정하고 다음 제한을 누적 강제합니다.

- `max_steps`
- `timeout`
- `max_total_tokens`
- 취소 신호

Runtime은 구체적인 Provider SDK와 MCP Transport를 import하지 않습니다. 모든 중요한 상태 전이는 Trace Event로 내보냅니다.

### Workspace Manager (`workspace`)

Task별 격리된 작업 사본을 만들고 정리합니다. 원본 Workspace를 변경하지 않으며 허용 root 밖의 경로 접근을 차단합니다. 구체적인 격리 방식은 구현 Issue에서 정합니다.

### Task Runner (`tasks`)

Lock 확인, Workspace 준비, Runtime 호출, Evaluator 호출, Result 조립을 담당합니다. Provider 또는 Evaluator의 세부 구현을 직접 포함하지 않습니다.

### Trace와 Metrics (`tracing`, `metrics`)

Trace는 redacted append-only Event를 기록합니다. Metrics는 Event와 Provider usage에서 성공 여부, Token, 호출 수, 단계 수, 실행 시간을 계산합니다.

측정되지 않은 값과 실제 `0`을 구분해야 하므로 optional usage 값은 `null`을 허용합니다.

### Evaluator (`evaluation`)

Agent Runtime과 독립적으로 격리 Workspace를 검사합니다. 평가 실패와 Agent 실행 실패를 구분하고, Evaluator timeout도 별도로 기록합니다.

### Storage (`storage`)

SQLite에 Manifest, Event, Result와 Metric을 저장합니다. Secret은 저장 전에 제거하며 원본 API 응답 전체를 무조건 보존하지 않습니다.

### Experiment와 Compare (`experiment`)

같은 Task, Workspace revision, Budget, Evaluator에서 여러 Harness Variant를 반복 실행하고 차이와 집계 결과를 계산합니다. Provider SDK가 아니라 Task Runner Result와 Metric에만 의존합니다.

## 의존성 방향

```text
Provider 구현 ─┐
MCP 구현 ──────┼─> 내부 계약 <─ Runtime <─ Task Runner
Tool 구현 ─────┘       ↑                       ↓
                 Trace / Metrics       Evaluator / Experiment
```

필수 규칙:

1. `runtime`은 구체적인 Provider SDK 또는 MCP Transport를 import하지 않습니다.
2. Credential은 Adapter가 Process 환경변수에서 Runtime에만 읽습니다.
3. Config, Lock, Event, SQLite, 오류와 Report에는 Secret을 저장하지 않습니다.
4. `tasks`는 Provider 응답 객체가 아니라 프로젝트 내부 Result로 Component를 연결합니다.
5. `evaluation`은 Agent 행동을 변경하지 않고 결과만 관측합니다.
6. `experiment`는 Task Runner를 우회하지 않습니다.
7. Interface는 실제 경계가 필요할 때만 추가합니다.

## 실패와 종료 모델

Run 종료 사유는 최소한 다음을 구분할 예정입니다.

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

예산 초과는 일반 오류가 아니라 비교 가능한 종료 결과입니다.

## 재현성 경계

Rigmetry의 live rerun은 외부 Model 응답의 동일성을 보장하지 않습니다. 대신 다음을 분리합니다.

- **Configuration reproducibility**: Harness, Task, Environment digest 비교
- **Execution replayability**: 저장 Event로 Runtime 흐름을 offline 재생
- **Statistical repeatability**: 동일 조건을 여러 번 실행해 분포로 비교

세 범위를 문서와 Report에서 혼동하지 않아야 합니다.
