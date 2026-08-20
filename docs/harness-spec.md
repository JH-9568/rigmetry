# Harness Specification (Draft)

이 문서는 MVP Harness 정의의 목표 형태를 설명합니다. 아직 확정된 호환성 계약이 아니며, 실제 Parser와 Validator를 구현하는 Issue에서 세부 규칙을 결정합니다.

## 예시

```yaml
name: coding-basic

model:
  provider: deepseek
  model: deepseek-chat

mcps:
  - filesystem

tools:
  - terminal

skills:
  - ./skills/debugging/SKILL.md

runtime:
  max_steps: 20
  timeout: 120
```

## 필드

### `name`

출력과 Report에서 Harness를 구분하는 사람이 읽기 쉬운 이름입니다. 이름의 전역 고유성 여부는 아직 확정하지 않습니다. 개별 Run에는 별도의 식별자가 필요합니다.

### `model`

Model Adapter와 Model을 선택합니다.

- `provider`: `deepseek`, 향후 `openai-compatible` 등 Adapter 식별자
- `model`: Provider에 전달할 Model 식별자

Provider별 옵션은 이후 추가할 수 있지만 Runtime에 Provider SDK 타입이 노출되어서는 안 됩니다. Credential은 이 필드에 허용하지 않습니다. Adapter는 Run 시작 시 Process 환경변수에서 필요한 API Key를 읽습니다.

### `mcps`

Harness에서 사용할 MCP Server 참조 목록입니다. 예시는 등록된 짧은 이름을 사용합니다. Process, Transport, Allow-list를 포함하는 구조화된 항목은 필요가 확인된 뒤 설계합니다. 현재 Draft에서는 Transport Schema와 lifecycle 정책을 고정하지 않습니다.

### `tools`

Agent에 노출할 Tool 목록입니다. 짧은 이름은 Tool Manager를 통해 해석될 예정입니다. Tool 권한, 인자 Schema, Sandbox 정책은 실제 구현 Issue에서 결정합니다.

### `skills`

Skill 지침 파일의 경로나 향후 등록형 참조 목록입니다. 상대 경로는 Harness 파일 위치를 기준으로 해석하는 방향이지만 Config Loader 구현 시 확정해야 합니다. Skill을 불러오는 행위만으로 Tool 권한이 부여되어서는 안 됩니다.

### `runtime`

Model Provider와 독립적인 실행 제한입니다.

- `max_steps`: 한 Run에서 허용할 최대 Agent 단계 수
- `timeout`: 한 Run의 최대 wall-clock 실행 시간(초)

Adapter 또는 Tool이 자체 제한을 제공하지 않아도 Runtime이 이 제한을 강제해야 합니다. 취소 처리와 Tool별 timeout은 별도 설계 대상입니다.

### 향후 `system_prompt`

최상위 Agent 지침을 inline text 또는 파일 참조로 제공할 필요가 있습니다. Prompt 결합 및 경로 해석 규칙이 정해질 때까지 필드 형태는 확정하지 않습니다.

## 보안과 이식성 원칙

- API Key, Access Token, Password, Private Credential을 Harness YAML에 작성하지 않습니다.
- Runtime Secret은 환경변수에서만 읽고 Trace, 오류, Report, SQLite에서 제거합니다.
- Harness는 필요한 capability를 선언할 뿐이며 Workspace와 Tool 경계는 Runtime이 강제합니다.
- 경로, Provider 옵션, MCP Transport 설정은 사용 전에 검증해야 합니다.

## 구현 상태

Parser와 Validator는 아직 구현되지 않았습니다. 기본값, 알 수 없는 필드 처리, 상대 경로 기준, Schema versioning은 Config 구현 Issue에서 결정합니다.
