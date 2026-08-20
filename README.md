# OpenHarness

OpenHarness는 AI Agent의 실행 구성을 코드로 정의하고, 같은 조건에서 재현·실행·평가·비교하기 위한 오픈소스 Agent Harness Infrastructure입니다.

핵심 개념은 **Harness-as-Code**입니다.

> Define → Run → Trace → Evaluate → Compare

현재 저장소는 **초기 개발 단계(pre-alpha)**입니다. Python 패키지와 최소 CLI 진입점, 설계 문서만 준비되어 있으며 Agent 실행, Model Provider 호출, MCP 연결, 평가 및 비교 기능은 아직 구현되지 않았습니다.

## 왜 OpenHarness인가?

Agent 결과는 Model 이름만으로 재현되지 않습니다. MCP Server, Tool, Skill, System Prompt, Runtime 제한, Workspace, Evaluator 설정이 모두 결과에 영향을 줍니다.

OpenHarness는 이 실행 환경 전체를 검토하고 버전 관리할 수 있는 코드로 만들고, 동일한 Task에서 여러 Harness를 실행해 결과와 원인을 공정하게 비교하는 것을 목표로 합니다.

## Harness-as-Code

Harness는 다음 실행 요소를 YAML로 정의할 예정입니다.

- **Model**: Provider 중립 Adapter를 통한 Provider 및 Model 선택
- **MCP**: 실행 중 Agent에 제공할 MCP Server
- **Tool**: Agent가 호출할 수 있는 기능
- **Skill**: 실행 문맥에 불러올 재사용 가능한 지침
- **Runtime**: 최대 단계, timeout 등 실행 제한
- **System Prompt**: Agent에 적용할 최상위 지침

Credential은 Harness에 포함하지 않습니다. API Key는 실행 시 환경변수에서만 주입하며 Config, SQLite, Trace, Run Report에 저장하지 않습니다.

## Architecture

계획된 실행 흐름은 다음과 같습니다.

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

Runtime은 OpenAI, DeepSeek 또는 MCP 구현체에 직접 의존하지 않고 프로젝트 내부 계약에만 의존해야 합니다. 자세한 책임과 의존성 경계는 [Architecture 문서](docs/architecture.md)를 참고하세요.

## Quick Start

현재 저장소는 다음과 같이 개발 환경을 설치하고 기반 구성을 검증할 수 있습니다.

```bash
git clone https://github.com/JH-9568/openharness.git
cd openharness
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
openharness --help
pytest
ruff check .
```

현재 `openharness --help`는 CLI 진입점만 검증합니다. 아래 CLI 명령은 목표 인터페이스이며 아직 동작하지 않습니다.

## `harness.yaml` 예시

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

필드별 의미는 [Harness Specification](docs/harness-spec.md)을 참고하세요.

## `task.yaml` 예시

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

계획된 Task 실행 수명 주기는 [Task Specification](docs/task-spec.md)을 참고하세요.

## 목표 CLI 인터페이스

```bash
openharness validate examples/harnesses/basic.yaml
openharness run --harness harness.yaml --task task.yaml
openharness report <run-id>
openharness compare <run-id> <run-id>
```

위 명령은 **계획 상태이며 구현되지 않았습니다**. 실제 구현 Issue에서 명령 이름과 옵션이 변경될 수 있습니다.

## Project Status

현재 준비된 범위:

- Python 패키지 metadata와 `src` layout
- 최소 `openharness` CLI 진입점
- Harness 및 Task Draft 명세
- Architecture 및 협업 문서
- 예시 YAML과 GitHub Issue/PR 템플릿
- Coding Agent 작업 지침

아직 구현되지 않은 범위:

- Agent Loop 및 Task 실행
- OpenAI-compatible 및 DeepSeek API 호출
- MCP 연결과 Tool 실행
- Workspace 격리
- Evaluator, Trace, Metrics, SQLite 저장
- Experiment Runner, Benchmark, Run Report, Harness Compare

## Roadmap

### MVP

- Harness 및 Task YAML 파싱과 검증
- Provider 중립 Model Adapter 계약
- OpenAI-compatible 및 DeepSeek Adapter
- MCP 연결 및 Tool 제공
- 단계 수와 timeout이 제한된 Agent Runtime
- 격리된 Workspace에서 Task 실행
- Credential을 제외한 Trace와 기본 Metrics 수집
- Command Evaluator와 SQLite 실행 결과 저장
- Run Report와 Harness 비교

### 이후

- Claude, Gemini, Ollama, vLLM 및 Custom Provider
- 추가 Evaluator와 재사용 가능한 Benchmark
- 확장된 Experiment orchestration과 Report

Roadmap은 방향을 설명하며 호환성 약속이 아닙니다.

## Contributing

개발은 GitHub Issue 기반으로 진행합니다. 모든 사람과 Coding Agent는 작업 전에 [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md), [Development Guide](docs/development.md)를 읽어야 합니다.

브랜치는 `feature/<issue-number>-<short-name>` 형식을 사용하고, Commit 제목은 `feat: 하네스 YAML 검증 추가`처럼 prefix 뒤 내용을 한국어로 작성합니다. PR 제목과 본문도 한국어로 작성하며 본문에 `Closes #<issue-number>`를 넣습니다.

## License

OpenHarness는 [MIT License](LICENSE)로 배포됩니다.
