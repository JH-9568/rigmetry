# Rigmetry

[![CI](https://github.com/JH-9568/rigmetry/actions/workflows/ci.yml/badge.svg)](https://github.com/JH-9568/rigmetry/actions/workflows/ci.yml)

> Lock. Run. Replay. Compare.

Rigmetry는 AI Agent Harness 변경을 content-addressed Lock으로 고정하고, 통제된 반복 실행과 무호출 Replay를 통해 그 변경이 성공률과 Token 효율에 미친 효과를 검증하는 오픈소스 실험 엔진입니다.

Model만 같다고 Agent 실행 조건이 같은 것은 아닙니다. System Prompt, MCP Server, Tool, Skill, Runtime 제한, Workspace가 달라지면 결과도 달라집니다. Rigmetry는 이 전체 구성을 **Harness-as-Code**로 정의하고 다음 질문에 답하는 것을 목표로 합니다.

> 같은 Task, Model과 Budget에서 이 Harness 변경은 성공률과 Token 효율을 어떻게 바꾸는가?

현재 저장소는 **초기 개발 단계(pre-alpha)**입니다. Python Package, 공통 실행 계약과 Config 검증·Lock 생성까지 구현되어 있으며 Run, Replay, Compare 기능은 아직 구현되지 않았습니다.

## 핵심 흐름

```text
Define → Lock → Run → Trace → Evaluate → Replay → Compare → Verify
```

1. **Define**: `harness.yaml`, `task.yaml`, `experiment.yaml`로 실행과 통제 조건을 정의합니다.
2. **Lock**: Config와 참조 Artifact를 정규화하고 content digest를 생성합니다.
3. **Run**: 원본을 보호하는 disposable Workspace에서 정해진 단계·시간·Token Budget 안으로 실행합니다.
4. **Trace**: Model과 Tool 상호작용을 redacted append-only Event로 기록합니다.
5. **Evaluate**: Agent와 독립된 Evaluator가 Task 성공 여부를 판정합니다.
6. **Replay**: 기록된 Model·Tool·Evaluator 결과를 경계 Adapter로 공급해 Runtime 상태와 Metric을 외부 호출 없이 재계산합니다.
7. **Compare**: 허용된 Harness 차이만 가진 반복 Run을 묶어 변경 효과를 비교합니다.
8. **Verify**: Evidence Bundle의 Lock, Event hash chain, Run 누락과 Report 계산을 확인합니다.

## Rigmetry가 해결하는 문제

일반적인 Agent 비교는 Model 이름이나 최종 응답만 확인하기 쉽습니다. 하지만 다음 조건이 다르면 공정한 비교가 아닙니다.

- Prompt와 Skill 내용
- 노출된 Tool과 MCP Capability
- Workspace revision
- 최대 단계와 timeout
- Token Budget
- Evaluator
- 의도적으로 허용한 Config diff

Rigmetry는 실행 당시 조건의 지문을 남기고, 같은 Task·Model·Budget에서 Harness Variant를 반복 실행해 결과를 비교합니다.

```text
Baseline:  terminal Tool만 사용
Candidate: terminal Tool + debugging Skill

동일 조건: Model, Task, Workspace, max_steps, timeout, Token Budget

결과 예시
                         Baseline    Candidate
success@50k                 40%          80%
성공당 Token               45,500       15,500
중앙 Agent 단계              16           10
중앙 실행 시간               55초         39초
```

위 숫자는 인터페이스 설명을 위한 예시이며 실제 Benchmark 결과가 아닙니다.

## Harness 구성요소

- **Model**: Provider 중립 Adapter로 선택한 Model
- **MCP**: Agent에 제공할 MCP Server와 Capability. 실제 연결은 MVP 우선순위에 따라 단계적으로 지원합니다.
- **Tool**: Agent가 호출할 수 있는 제한된 기능
- **Skill**: 실행 Context에 포함할 재사용 가능한 지침
- **System Prompt**: Agent의 최상위 지침
- **Runtime**: 최대 단계, timeout, Token Budget
- **Workspace**: 원본을 보호하기 위한 Task별 disposable 작업 사본. Container/VM 보안 Sandbox를 의미하지 않습니다.
- **Evaluator**: Agent 실행과 독립된 성공 판정기

Credential은 Harness에 포함하지 않습니다. API Key는 실행 시 환경변수에서만 주입하며 Config, Lock, SQLite, Trace, Report에 저장하지 않습니다.

### MVP Model Adapter 전략

MVP는 서로 다른 실행 경계를 검증하기 위해 다음 두 Adapter를 목표로 합니다.

- **OpenAI-compatible**: 환경변수로 Credential을 주입하는 원격 API
- **Ollama Native**: 로컬 Ollama의 `/api/chat`을 사용하는 로컬 실행

DeepSeek처럼 OpenAI 호환 API를 제공하는 서비스는 별도 Adapter를 만들지 않고 OpenAI-compatible 설정으로 연결할 수 있게 설계합니다. Ollama는 OpenAI 호환 Endpoint가 아니라 Native API로 연동하여 Adapter 경계와 로컬 실행 지표 정규화를 실제로 검증합니다. 두 Adapter 모두 아직 구현되지 않았습니다.

## Quick Start

현재 Repository foundation을 설치하고 검증할 수 있습니다.

```bash
git clone https://github.com/JH-9568/rigmetry.git
cd rigmetry
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
rigmetry --help
rigmetry validate examples/experiments/debugging-skill.yaml
rigmetry lock examples/experiments/debugging-skill.yaml
pytest
ruff check .
```

현재 `validate`와 `lock`은 동작합니다. Agent 실행 관련 명령은 아직 목표 인터페이스입니다.

## `harness.yaml` 예시

```yaml
name: basic

model:
  provider: ollama
  model: qwen3:8b

system_prompt: >
  변경 전 테스트를 실행하고 실패 원인을 확인한 뒤 최소한으로 수정하라.

mcps: []

tools:
  - terminal

skills: []

runtime:
  max_steps: 20
  timeout: 120
  max_total_tokens: 50000
```

필드 정의는 [Harness Specification](docs/harness-spec.md)을 참고하세요.

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

Task 수명 주기는 [Task Specification](docs/task-spec.md)을 참고하세요.

## `experiment.yaml` 예시

```yaml
id: debugging-skill-effect
task: ../tasks/example.yaml

variants:
  baseline: ../harnesses/basic.yaml
  candidate: ../harnesses/basic-with-debugging.yaml

controls:
  require_same: [task, harness.model, harness.mcps, harness.tools, harness.system_prompt, harness.runtime]
  allow_diff: [harness.skills]

trials:
  count: 5
  order: randomized
  seed: 9568
```

Experiment는 허용된 Harness 차이와 공유 조건, 반복 계획을 일급 Config로 고정합니다. 자세한 정의는 [Experiment Specification](docs/experiment-spec.md)을 참고하세요.

## CLI

```bash
# 구현됨: Config와 참조 Artifact 검증
rigmetry validate experiment.yaml

# 구현됨: Experiment와 참조 Artifact Lock 생성
rigmetry lock experiment.yaml

# 계획됨: 단일 Task 실행
rigmetry run --harness harness.yaml --task task.yaml

# 기록된 Event를 이용한 offline replay
rigmetry replay <run-id> --offline

# 통제 조건에 따른 반복 실행과 비교
rigmetry compare experiment.yaml

# 이식 가능한 결과 생성과 내부 일관성 검증
rigmetry export <experiment-id> --output evidence/
rigmetry verify evidence/
```

`run`, `replay`, `compare`, `export`, `verify`는 **목표 인터페이스이며 아직 구현되지 않았습니다**. 구현 Issue에서 옵션이 변경될 수 있습니다.

## 핵심 지표

- `success@budget`: 주어진 Token Budget 안에서 성공한 Run 비율
- `tokens_per_success`: 같은 Provider·Model 안에서 전체 Token 사용량을 성공 Run 수로 나눈 값
- 입력·출력·Cache·Reasoning Token: Provider가 보고한 범위에서 각각 기록
- Model 호출 수, Tool 호출 수, Agent 단계 수
- 실행 시간과 종료 사유

Provider가 제공하지 않은 Token 값은 `0`이 아니라 `null`로 보존합니다. 서로 다른 tokenizer의 Token 수를 동일한 단위처럼 직접 비교하지 않습니다. 금액 비용은 적용 가능한 Provider에서만 Token usage와 분리해 가격표 출처와 기준 시점을 함께 기록할 예정입니다.

자세한 Fingerprint, Event, Replay, 비교 규칙은 [Experiment Model](docs/experiment-model.md)을 참고하세요.

## 재현성의 범위

Rigmetry는 외부 Model이 live rerun에서 같은 응답을 생성한다고 주장하지 않습니다.

- **보장 목표**: 같은 Harness/Task/Environment인지 digest로 확인
- **보장 목표**: 기록된 Model·Tool·Evaluator 결과를 사용하는 동일 Runtime 상태 전이와 Metric의 offline replay
- **보장 목표**: Evidence Bundle 내부 Lock, Event와 Report 계산의 일관성 검증
- **비보장**: 외부 Provider가 다시 생성하는 응답의 결정론적 동일성
- **비보장**: 원본 Workspace와 저장하지 않은 외부 Side Effect의 완전한 복원

이 구분을 통해 “실행 조건의 동일성”과 “확률적 Model 출력의 동일성”을 혼동하지 않습니다.

## Architecture

Runtime은 OpenAI-compatible, Ollama 또는 MCP 구현체를 직접 import하지 않고 프로젝트 내부 계약에만 의존해야 합니다. 자세한 책임과 의존성 방향은 [Architecture](docs/architecture.md)를 참고하세요.

## Project Status

현재 구현됨:

- Python Package metadata와 `src` layout
- Pull Request와 `main` Push에서 설치·Ruff·pytest를 검증하는 GitHub Actions CI
- `rigmetry validate`, `rigmetry lock` CLI
- Harness·Task·Experiment Pydantic Schema와 canonical Lock digest
- Prompt·Skill·Tool/MCP 선언·Workspace Fixture·Evaluator content hash
- Experiment `require_same`, `allow_diff` 검증
- Provider 중립 Model·Token·Run 공통 계약과 `ModelAdapter` Protocol
- Trace Event envelope, vocabulary와 canonical Event hash 계산
- Harness, Task, Experiment와 Evidence Draft 명세
- Architecture와 2인 협업 문서
- 예시 YAML 및 GitHub Issue/PR Template

아직 구현되지 않음:

- Agent Loop와 Model API 호출
- MCP 연결과 Tool 실행
- Disposable Workspace와 Evaluator
- Event 저장·전체 hash chain 검증, Replay, Metrics, SQLite 저장
- 반복 Experiment, Harness Compare와 Evidence 검증
- 실제 Benchmark 결과

## MVP Roadmap

1. Harness/Task/Experiment Schema와 deterministic canonicalization
2. Provider 중립 Model/Event 계약
3. OpenAI-compatible·Ollama Native Model Adapter와 제한된 Agent Runtime
4. Disposable Workspace, Terminal Tool, Command Evaluator
5. SQLite Event hash chain과 Boundary Transcript 기반 offline replay
6. 통제된 반복 Experiment, Compare Report와 Evidence Bundle 검증
7. 재현 가능한 예제 Benchmark와 결과 공개

Claude, Gemini, vLLM, 세 번째 Model Adapter, Web Dashboard와 대규모 Benchmark는 MVP 이후 범위입니다.

2인 역할, Issue dependency와 8월 27일까지의 일별 계획은 [대회 MVP 계획](docs/mvp-plan.md)에서 관리합니다.

## Contributing

모든 Contributor와 Coding Agent는 작업 전에 [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md), [Development Guide](docs/development.md)를 읽어야 합니다.

Branch는 `feature/<issue-number>-<short-name>` 형식을 사용합니다. Commit 제목은 `feat: Harness Lock 생성 추가`처럼 영문 prefix 뒤 내용을 한국어로 작성하고, PR 제목과 본문도 한국어로 작성합니다.

## License

Rigmetry는 [MIT License](LICENSE)로 배포됩니다.
