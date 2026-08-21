# Architecture

Rigmetry는 AI Agent Framework가 아니라 Harness 변경 효과를 검증하는 실험 엔진입니다. Config를 content-addressed 실행 지문으로 만들고, 통제된 Runtime에서 Event를 기록하며, 동일 조건의 Run과 Evidence를 검증하는 데 초점을 둡니다. 이 문서는 구현 완료 상태가 아닌 의존성 방향을 정의합니다.

## 계획된 흐름

```text
harness.yaml + task.yaml + experiment.yaml
                   ↓
         Config Loader / Validator
                   ↓
        Canonical Locks / Digests
                   ↓
Model Adapter / MCP Manager / Tool Manager / Skill Loader
                   ↓
Budgeted Agent Runtime ─────→ Append-only Event Trace
                   ↓                              ↓
Disposable Workspace                 SQLite Storage
                   ↓                              ↓
Task Runner → Evaluator → Run Result / Metrics
                                           ↓
                    Offline Replay / Harness Compare
                                           ↓
                         Evidence Bundle / Verify
```

## 핵심 데이터 경계

### Config와 Lock (`config`)

`harness.yaml`, `task.yaml`, `experiment.yaml`을 읽고 검증합니다. 참조 Artifact의 내용을 정규화하고 Harness, Task, Experiment Lock과 digest를 만듭니다.

작성자가 관리하는 YAML과 Rigmetry가 생성하는 Lock은 구분합니다. Lock은 Credential을 포함하지 않으며 같은 입력에 같은 digest가 나와야 합니다. Experiment Lock은 `require_same`, `allow_diff`, 반복 계획과 Run 순서를 고정합니다.

현재 Pydantic Schema, YAML 검증, 참조 Artifact content hash, Experiment control 검사와 canonical Lock 생성은 `rigmetry.config`에 구현되어 있습니다. 정확한 digest 입력과 경로 경계는 [Config와 Lock 구현 가이드](config-lock.md)를 따릅니다.

### Model Adapter (`models`)

Provider 중립 요청을 Provider API 형식으로 바꾸고 응답과 Token usage를 프로젝트 내부 타입으로 정규화합니다. Provider SDK 객체, 인증 정보, API 오류가 Runtime 경계를 넘어가면 안 됩니다.

각 Adapter는 Tool calling, Token usage, seed, native model digest 등 지원 Capability를 선언합니다. Runtime 또는 Experiment의 필수 Capability를 충족하지 못하면 외부 호출 전에 거부합니다.

공통 `ModelRequest`, `ModelResult`, `TokenUsage`, `ProviderCapabilities`와 `ModelAdapter` Protocol은 `rigmetry.models`에 구현되어 있습니다. Adapter와 Runtime 구현은 별도 유사 타입을 만들지 않고 [공통 계약 구현 가이드](contracts.md)의 공개 import를 사용합니다.

MVP는 OpenAI-compatible Adapter와 Ollama Native Adapter를 구현 대상으로 둡니다. DeepSeek처럼 OpenAI 호환 API를 제공하는 서비스는 별도 Adapter를 만들지 않고 OpenAI-compatible 설정으로 처리합니다.

#### MVP Provider 경계

- **OpenAI-compatible Adapter**: OpenAI 호환 요청·응답과 Credential 주입을 담당합니다.
- **Ollama Native Adapter**: 로컬 Ollama의 Native `/api/chat` 요청·응답을 담당합니다. OpenAI 호환 Endpoint를 경유하지 않습니다.

Ollama 응답의 `prompt_eval_count`와 `eval_count`는 각각 내부 input/output Token으로 정규화하고, Provider가 제공하는 실행 시간 값은 Provider metric으로 보존하는 방향입니다. 정확한 필드와 Streaming 처리 방식은 구현 Issue에서 고정합니다.

이 구분은 Adapter 수를 늘리기 위한 것이 아니라 원격 Credential 기반 API와 로컬 Runtime이라는 실제로 다른 경계를 최소 두 개로 검증하기 위한 것입니다. 참고: [Ollama Chat API](https://docs.ollama.com/api/chat), [Ollama Usage](https://docs.ollama.com/api/usage).

### MCP Manager (`mcp`)

향후 MCP Client 연결, capability 탐색, lifecycle과 종료를 담당합니다. Runtime에는 Transport별 Client 객체가 아니라 정규화된 Tool capability를 제공해야 합니다. MVP 예제는 실제 연결 전까지 빈 `mcps`를 사용하며 지원되지 않는 참조를 조용히 무시하지 않습니다.

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

Task별 disposable 작업 사본을 만들고 정리합니다. 원본 Workspace를 변경하지 않고 Rigmetry가 해석하는 경로는 허용 root 안으로 제한합니다. 임시 디렉터리나 Git worktree는 Shell Process의 시스템 접근을 막는 Container/VM 보안 Sandbox가 아니며 그렇게 표현하지 않습니다.

### Task Runner (`tasks`)

Lock 확인, Workspace 준비, Runtime 호출, Evaluator 호출, Result 조립을 담당합니다. Provider 또는 Evaluator의 세부 구현을 직접 포함하지 않습니다.

### Trace와 Metrics (`tracing`, `metrics`)

Trace는 redacted append-only Event를 기록하고 Event hash chain으로 누락과 순서 변경을 검사합니다. Metrics는 Event와 Provider usage에서 성공 여부, Token, 호출 수, 단계 수, 실행 시간을 계산합니다.

현재 `rigmetry.tracing`에는 Event envelope, vocabulary와 단일 Event hash 계산까지만 구현되어 있습니다. 전체 chain 검증, 저장과 Replay는 아직 구현되지 않았습니다.

측정되지 않은 값과 실제 `0`을 구분해야 하므로 optional usage 값은 `null`을 허용합니다.

### Evaluator (`evaluation`)

Agent Runtime과 독립적으로 disposable Workspace를 검사합니다. 평가 실패와 Agent 실행 실패를 구분하고, Evaluator timeout도 별도로 기록합니다.

### Storage (`storage`)

SQLite에 Manifest, Event, Result와 Metric을 저장합니다. Secret은 저장 전에 제거하며 원본 API 응답 전체를 무조건 보존하지 않습니다.

### Experiment와 Compare (`experiment`)

같은 Task, Workspace revision, Provider·Model, Budget, Evaluator에서 여러 Harness Variant를 반복 실행하고 차이와 집계 결과를 계산합니다. Variant 순서는 무작위화하거나 교차 배치하며 허용되지 않은 Config diff는 실행 전에 거부합니다. Provider SDK가 아니라 Task Runner Result와 Metric에만 의존합니다.

### Replay와 Evidence (`tracing`, `experiment`)

Transcript-backed Model, Tool, Evaluator Adapter가 저장된 경계 결과를 공급해 같은 Runtime 상태 전이, 종료 사유와 파생 Metric을 외부 호출 없이 재계산합니다. 원본 Workspace 또는 저장하지 않은 Side Effect의 복원을 책임지지 않습니다.

Evidence Bundle은 Lock, SQLite Run/Event, JSON/Markdown Report와 Manifest를 묶습니다. Verify는 Artifact digest, Event hash chain, Run 누락, 통제 조건과 Report 재계산을 검사합니다. 내부 일관성 검증이며 전자서명이나 결과의 통계적 유의성 보증이 아닙니다.

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
7. Replay는 live Provider, Tool 또는 Evaluator 구현을 호출하지 않습니다.
8. Interface는 실제 경계가 필요할 때만 추가합니다.

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
- **Execution replayability**: 저장된 경계 결과로 Runtime 상태와 파생 Metric을 offline 재계산
- **Statistical repeatability**: 동일 조건을 여러 번 실행해 분포로 비교
- **Evidence integrity**: Lock, Event chain, Run과 Report의 내부 일관성 검사

세 범위를 문서와 Report에서 혼동하지 않아야 합니다.
