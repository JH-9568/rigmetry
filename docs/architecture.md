# Architecture

OpenHarness는 Provider 중립 Runtime을 중심으로 Config, Capability, 실행, 관측 책임을 분리합니다. 이 문서는 구현 완료 상태가 아니라 앞으로 구현할 방향과 의존성 경계를 정의합니다.

## 계획된 실행 흐름

```text
harness.yaml
      ↓
Harness Manager
      ↓
Model Adapter / MCP Manager / Tool Manager / Skill Loader
      ↓
Agent Runtime
      ↓
Isolated Workspace
      ↓
Task Runner
      ↓
Trace / Metrics / Evaluator
      ↓
Run Report
      ↓
Harness Compare
```

## 모듈별 책임

### Harness Manager (`config`)

YAML을 읽고, 허용된 참조를 해석하고, Draft Schema를 검증해 내부 Harness Config를 만듭니다. Model 호출, MCP Server 시작, Task 실행은 담당하지 않습니다.

### Model Adapter (`models`)

Provider 중립 요청과 응답을 각 Provider 형식으로 변환합니다. MVP 기준 구현은 OpenAI-compatible과 DeepSeek입니다. Provider SDK 객체, 인증 정보, API 오류는 내부 경계를 넘기 전에 프로젝트 타입으로 정규화해야 합니다.

### MCP Manager (`mcp`)

MCP Client 연결, capability 탐색, lifecycle과 종료를 담당합니다. Runtime에는 Transport별 Client 객체가 아니라 정규화된 capability를 제공합니다.

### Tool Manager (`tools`)

허용된 Tool 등록, 호출 검증, 실행 위임, 결과 정규화를 담당합니다. Agent에 보이는 Tool을 제한하는 권한 경계이며 Skill Loader가 이 경계를 우회해서는 안 됩니다.

### Skill Loader (`config`에서 시작)

Skill 지침 경로를 해석하고 내용을 불러옵니다. 실제 책임이 커질 때까지 별도 Package를 만들지 않습니다. Skill은 Runtime에 전달하는 데이터이며 실행 권한이 아닙니다.

### Agent Runtime (`runtime`)

Model turn과 capability 호출을 조정하고 최대 단계, timeout, 취소 같은 Provider 중립 제한을 강제합니다. 프로젝트 내부 Model/Tool 계약만 사용하며 구체적인 OpenAI, DeepSeek, MCP Client 구현을 직접 import해서는 안 됩니다.

### Workspace Manager (`workspace`)

Task별 격리된 작업 사본을 생성·정리하고 모든 작업이 허용된 root 안에서 수행되도록 보장합니다. 격리 방식은 별도 MVP Issue에서 결정합니다.

### Task Runner (`tasks`)

Workspace 준비, Runtime 호출, Evaluator 호출, Result 조립으로 이어지는 하나의 Task 수명 주기를 조정합니다. Provider나 Evaluator 세부 구현을 직접 담당하지 않습니다.

### Trace, Metrics, Evaluator (`tracing`, `metrics`, `evaluation`)

- Trace는 시간 순서의 실행 Event를 기록하며 Secret을 제거합니다.
- Metrics는 실행 시간, 단계 수, 사용량처럼 제한된 측정값을 계산합니다.
- Evaluator는 Agent Runtime과 독립적으로 Task 성공 여부를 판단합니다.

관측 계층 실패는 Agent 실행 실패 및 평가 실패와 구분되어야 합니다.

### Storage (`storage`)

SQLite에 로컬 Run metadata와 Report를 저장합니다. Credential이 제거된 이식 가능한 데이터만 저장해야 합니다. Schema와 migration 전략은 별도 Issue에서 결정합니다.

### Experiment와 Compare (`experiment`)

여러 Harness/Task 조합을 실행하거나 묶고 완료된 Report를 비교합니다. Provider SDK가 아니라 안정된 Task Runner Result에 의존합니다. 현재 Repository foundation 범위에는 포함되지 않습니다.

## 의존성 경계

의존성은 작고 프로젝트가 소유하는 내부 계약을 향해야 합니다.

```text
Provider 구현 ─┐
MCP 구현 ──────┼─> 내부 계약 <─ Agent Runtime
Tool 구현 ─────┘                   ↑
                         Task Runner / Evaluator
```

필수 규칙:

1. `runtime`은 구체적인 Provider SDK 또는 MCP Transport를 import하지 않습니다.
2. Provider Credential은 해당 Adapter가 Runtime에만 읽으며 Config Model, YAML, SQLite에 저장하지 않습니다.
3. `tasks`는 Provider 응답 객체가 아니라 프로젝트 내부 Result로 Component를 조정합니다.
4. `evaluation`은 격리된 Workspace와 실행 Result를 관측하며 Model 동작을 변경하지 않습니다.
5. `experiment`는 완료된 Run Report를 사용하며 Task Runner를 우회하지 않습니다.

Interface는 첫 실제 구현에서 경계가 필요해질 때 추가합니다. 현재 빈 Package는 책임 영역만 표시하며 미리 복잡한 class hierarchy를 고정하지 않습니다.
