# Config와 Lock 구현 가이드

이 문서는 Issue #2에서 구현한 Harness, Task, Experiment 검증과 content-addressed Lock 규칙을 설명합니다. Runtime, Task Runner와 Experiment 구현은 원본 YAML을 임의로 다시 해석하지 않고 `rigmetry.config`의 공개 API를 사용합니다.

## CLI

```bash
rigmetry validate examples/harnesses/basic.yaml
rigmetry validate examples/tasks/example.yaml
rigmetry validate examples/experiments/debugging-skill.yaml

rigmetry lock examples/experiments/debugging-skill.yaml
rigmetry lock examples/experiments/debugging-skill.yaml --output experiment.lock.json
```

`validate`도 참조 Skill, Workspace, Task와 Variant를 확인합니다. `lock`은 key가 정렬된 JSON을 stdout 또는 지정한 파일에 출력합니다. 오류는 실패한 파일과 Pydantic field 위치를 포함하고 종료 코드 `1`을 반환합니다.

Python에서는 다음 공개 API를 사용합니다.

```python
from rigmetry.config import ConfigError, build_lock, load_config

config = load_config("harness.yaml")
lock = build_lock("experiment.yaml")
```

## 작성 Config Schema

세 Config는 선언하지 않은 필드를 거부합니다. 따라서 `api_key`, `token`, `password`처럼 Credential 값을 담는 별도 필드를 추가할 수 없습니다.

### Harness

- `model.provider`: `openai-compatible` 또는 `ollama`
- `model.model`: Provider에 요청할 Model ID
- `model.base_url`: 선택 HTTP(S) Endpoint. 사용자 정보와 Credential query를 거부합니다.
- `model.api_key_env`: 선택 환경변수 이름. 실제 값이 아닙니다.
- `system_prompt`: inline Prompt
- `mcps`: 이름 문자열 또는 `{name, capabilities}` 선언
- `tools`: 이름 문자열 또는 `{name, description, input_schema}` 선언
- `skills`: Harness 파일 기준 상대 파일 경로
- `runtime`: 양수인 `max_steps`, `timeout`, `max_total_tokens`

문자열 Tool/MCP는 이름만 고정합니다. Tool Schema나 MCP Capability가 알려진 시점에는 객체 형태로 선언해야 그 내용까지 digest에 포함됩니다. 실제 Registry에서 Schema를 주입하는 연결은 Tool/MCP 구현 Issue에서 담당합니다.

### Task

- `id`: 사람용 이름
- `workspace`: Task 파일 기준 상대 Workspace 디렉터리
- `prompt`: Agent 작업 지시문
- `evaluator`: MVP `command`, 명령과 양수 timeout

MVP Lock은 Workspace 파일의 상대 경로와 내용 digest를 정렬한 Fixture Manifest로 계산합니다. `.git` 내부는 제외하고 symlink는 거부합니다. 이는 Workspace revision을 content snapshot으로 식별하는 것이며 disposable Workspace 생성이나 보안 Sandbox를 의미하지 않습니다.

### Experiment

- `task`: Experiment 파일 기준 상대 Task 경로
- `variants`: 두 개 이상 Harness 이름과 상대 경로
- `controls.require_same`: 반드시 같은 composed field
- `controls.allow_diff`: 의도적으로 다른 Harness field
- `trials`: 양수 반복 수, `randomized`, 선택 배치 seed
- `metrics`: Report에서 계산할 Metric 이름

현재 control 경로는 `task`와 `harness.model`, `mcps`, `tools`, `skills`, `system_prompt`, `runtime`입니다. Harness의 사람용 `name` 차이는 실행 의미 비교에서 제외합니다. 실제 차이가 `allow_diff` 밖에 있거나 `require_same` 값이 다르면 Lock 생성을 거부합니다.

## Canonicalization

Digest 입력은 다음 규칙을 사용합니다.

1. YAML을 Pydantic Model로 검증하고 Default를 적용합니다.
2. Map key를 정렬하고 공백 없는 UTF-8 JSON으로 직렬화합니다.
3. SHA-256을 계산하고 `sha256:` 접두사를 붙입니다.
4. 참조 파일은 절대 경로가 아니라 내용 digest를 실행 의미에 포함합니다.
5. YAML key 순서와 사람용 `name`/`id`는 실행 digest를 바꾸지 않습니다.

YAML에서 중복 key는 마지막 값으로 덮어쓰지 않고 오류로 처리합니다.

## Digest 구성

### Harness digest

- Provider, 요청 Model ID, base URL, Credential 환경변수 이름
- System Prompt 내용 digest
- MCP 선언과 Capability digest
- Tool 선언과 Input Schema digest
- 순서가 보존된 Skill 내용 digest
- Runtime 제한

Lock의 `requested_model`은 요청 설정입니다. 응답 Model ID, Ollama native digest 같은 관측 provenance는 실행 중 Run Manifest에 별도로 기록해야 합니다.

### Task digest

- Prompt 내용 digest
- Workspace Fixture Manifest digest
- Evaluator type, command, timeout digest

### Experiment digest

- Task digest
- Variant 이름별 Harness digest
- `require_same`, `allow_diff`
- 반복 횟수, 순서와 배치 seed
- Metric 목록

Lock에 표시되는 source reference는 사람이 추적하기 위한 상대 경로이며 Machine의 절대 경로는 저장하지 않습니다.

## 허용 root

기본 허용 root는 Config에서 위로 탐색한 가장 가까운 `pyproject.toml` 또는 `.git` 경계입니다. 모든 Skill, Task, Harness와 Workspace 참조는 이 root 안에 있어야 합니다. Library 사용자는 `build_lock(path, root=...)`로 root를 명시할 수 있습니다.

## 보장하지 않는 범위

- 외부 Provider의 실제 Model revision 고정
- 운영체제, Python과 dependency 전체 fingerprint
- Tool/MCP Registry에 등록된 실제 구현 자동 탐색
- Git submodule, symlink와 대용량 Workspace 최적화
- Agent 실행, 반복 orchestration과 Evidence 생성

Environment fingerprint와 실행 중 provenance는 Runtime/Storage Issue에서 Lock과 분리해 추가합니다.
