# Harness Specification (Draft)

이 문서는 Rigmetry MVP Harness 정의의 목표 형태를 설명합니다. 작성자가 관리하는 `harness.yaml`과 Rigmetry가 생성할 Lock Manifest는 별개입니다. 세부 Validation 규칙은 Config 구현 Issue에서 확정합니다.

## 예시

```yaml
name: coding-basic

model:
  provider: ollama
  model: qwen3:8b

system_prompt: >
  변경 전 테스트를 실행하고 실패 원인을 확인한 뒤 최소한으로 수정하라.

mcps: []

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

- `provider`: Model Adapter 식별자. MVP 목표 값은 `openai-compatible`, `ollama`입니다.
- `model`: Provider에 전달할 Model 식별자
- `base_url`: 기본 Endpoint를 덮어쓸 때 사용하는 선택 필드
- `api_key_env`: Credential 값이 아니라 읽을 환경변수 이름을 지정하는 선택 필드

Provider별 옵션은 내부 Runtime 계약과 분리해야 합니다. API Key와 Credential 값은 이 Config에 허용하지 않습니다. `api_key_env`에는 환경변수 이름만 기록하며, Ollama 로컬 실행에는 기본적으로 Credential이 필요하지 않습니다.

OpenAI-compatible 원격 API의 목표 예시는 다음과 같습니다.

```yaml
model:
  provider: openai-compatible
  model: gpt-4.1-mini
  base_url: https://api.openai.com/v1
  api_key_env: OPENAI_API_KEY
```

Ollama는 Adapter 경계를 검증하기 위해 OpenAI 호환 Endpoint가 아닌 Native API를 사용하는 방향입니다.

```yaml
model:
  provider: ollama
  model: qwen3:8b
  base_url: http://localhost:11434
```

DeepSeek처럼 OpenAI 호환 API를 제공하는 서비스는 전용 Adapter가 아니라 `openai-compatible`의 `base_url`, `model`, `api_key_env` 설정으로 연결합니다. 지원 Endpoint, 기본 URL과 필수 옵션은 Model Adapter 구현 Issue에서 확정합니다.

Adapter는 Tool calling, Token usage, seed와 native model digest 같은 Capability를 선언해야 합니다. Harness와 Experiment가 요구하는 Capability를 충족하지 못하면 Runtime 외부 호출 전에 Validation 오류를 반환합니다.

### `system_prompt`

Agent에 적용할 최상위 지침입니다. MVP는 inline text를 우선 지원하고 파일 참조는 경로·digest 규칙이 정해진 뒤 추가할 수 있습니다.

### `mcps`

Harness에서 사용할 MCP Server 참조 목록입니다. 기본 예시는 실제 연결이 구현되기 전까지 빈 목록을 사용합니다. Process, Transport와 Allow-list를 포함한 구조는 MCP 구현 Issue에서 확정하며, 지원되지 않는 참조를 조용히 무시하면 안 됩니다.

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
    "provider": "ollama",
    "model": "qwen3:8b"
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

Lock에는 요청 Model 설정을 기록합니다. 실제 Run Manifest에는 응답 Model ID, Adapter version과 Ollama Model digest처럼 실행 중 관측한 Model provenance를 별도로 기록합니다. 외부 Provider의 가변 alias를 Lock만으로 완전히 고정할 수 있다고 주장하지 않습니다.

## 보안 원칙

- API Key, Token, Password와 Private Credential을 YAML과 Lock에 작성하지 않습니다.
- Runtime Secret은 환경변수에서만 읽습니다.
- Trace, 오류, Report, SQLite에 저장하기 전에 Secret을 제거합니다.
- Harness는 Capability를 요청할 뿐이며 실제 권한 경계는 Runtime과 Tool Manager가 강제합니다.

## 구현 상태

Parser, Validator, Canonicalizer와 Lock 생성은 아직 구현되지 않았습니다.
