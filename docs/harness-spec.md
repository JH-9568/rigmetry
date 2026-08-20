# Harness Specification (Draft)

이 문서는 Rigmetry MVP Harness 정의의 목표 형태를 설명합니다. 작성자가 관리하는 `harness.yaml`과 Rigmetry가 생성할 Lock Manifest는 별개입니다. 세부 Validation 규칙은 Config 구현 Issue에서 확정합니다.

## 예시

```yaml
name: coding-basic

model:
  provider: deepseek
  model: deepseek-chat

system_prompt: >
  변경 전 테스트를 실행하고 실패 원인을 확인한 뒤 최소한으로 수정하라.

mcps:
  - filesystem

tools:
  - terminal

skills:
  - ./skills/debugging/SKILL.md

runtime:
  max_steps: 20
  timeout: 120
  max_total_tokens: 50000
```

## 필드

### `name`

Report에서 Harness Variant를 구분할 이름입니다. 개별 Run 식별자와 digest를 대신하지 않습니다.

### `model`

- `provider`: Model Adapter 식별자
- `model`: Provider에 전달할 Model 식별자

Provider별 옵션은 내부 Runtime 계약과 분리해야 합니다. API Key와 Credential은 이 Config에 허용하지 않습니다.

### `system_prompt`

Agent에 적용할 최상위 지침입니다. MVP는 inline text를 우선 지원하고 파일 참조는 경로·digest 규칙이 정해진 뒤 추가할 수 있습니다.

### `mcps`

Harness에서 사용할 MCP Server 참조 목록입니다. 예시는 등록된 짧은 이름을 사용합니다. Process, Transport와 Allow-list를 포함한 구조는 MCP 구현 Issue에서 확정합니다.

### `tools`

Agent에 노출할 Tool 목록입니다. Tool Manager가 이름을 해석하고 Schema와 권한을 관리합니다.

### `skills`

Skill 지침 파일 경로 목록입니다. 상대 경로는 Harness 파일 위치 기준으로 해석하는 방향이며 Config Loader 구현 시 확정합니다. Lock에는 경로뿐 아니라 파일 content digest가 필요합니다.

### `runtime`

- `max_steps`: 한 Run에서 허용할 최대 Agent 단계 수
- `timeout`: 한 Run의 최대 wall-clock 실행 시간(초)
- `max_total_tokens`: 한 Run에서 Provider가 보고한 누적 전체 Token 상한

`max_total_tokens`는 공정한 Experiment 비교를 위한 Budget입니다. Provider가 usage를 제공하지 않는 경우의 실행 허용 여부는 Adapter capability와 Validation 정책으로 명시해야 합니다.

## 생성 예정 Lock Manifest

다음 형태는 방향을 설명하기 위한 예시입니다.

```json
{
  "schema_version": 1,
  "harness_digest": "sha256:...",
  "model": {
    "provider": "deepseek",
    "model": "deepseek-chat"
  },
  "artifacts": {
    "system_prompt": "sha256:...",
    "skills": {
      "./skills/debugging/SKILL.md": "sha256:..."
    }
  },
  "runtime": {
    "max_steps": 20,
    "timeout": 120,
    "max_total_tokens": 50000
  }
}
```

정규화 방식, Tool/MCP Schema digest, Runtime version과 Environment fingerprint는 [Experiment Model](experiment-model.md)에서 설명합니다.

## 보안 원칙

- API Key, Token, Password와 Private Credential을 YAML과 Lock에 작성하지 않습니다.
- Runtime Secret은 환경변수에서만 읽습니다.
- Trace, 오류, Report, SQLite에 저장하기 전에 Secret을 제거합니다.
- Harness는 Capability를 요청할 뿐이며 실제 권한 경계는 Runtime과 Tool Manager가 강제합니다.

## 구현 상태

Parser, Validator, Canonicalizer와 Lock 생성은 아직 구현되지 않았습니다.
