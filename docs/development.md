# Development Guide

Rigmetry는 2명이 GitHub Issue를 기준으로 병렬 개발하는 것을 전제로 합니다. Issue는 계획 단위, Branch는 구현 단위, PR은 Review와 Merge 단위입니다.

## 2인 역할 분배

다음 구분은 파일 충돌을 줄이기 위한 초기 책임 분배이며 영구적인 소유권이 아닙니다. 모든 PR은 담당자가 아닌 팀원이 Review하는 것을 원칙으로 합니다.

### Contributor A: Config와 실행 Core

- Harness/Task/Experiment Schema, Canonicalization과 Lock (`config`)
- Provider 중립 Model 계약과 Adapter (`models`)
- Agent Loop와 실행 제한 (`runtime`)
- Event Trace와 Offline Replay (`tracing`)
- 완료된 Core 기능을 노출하는 CLI (`cli`)

### Contributor B: Capability와 Task 수명 주기

- MCP 연결 lifecycle (`mcp`)
- Tool 등록과 호출 (`tools`)
- disposable Workspace 준비 (`workspace`)
- Task Runner와 Evaluator (`tasks`, `evaluation`)
- SQLite 저장과 Metric 집계 (`storage`, `metrics`)
- 반복 Experiment와 Compare Report (`experiment`)

### 공동 작업

`run_id`, Digest, Event envelope, Token usage, Run Result와 Experiment 통제 조건은 두 영역이 공유하는 계약입니다. [Experiment Model](experiment-model.md)과 [Experiment Specification](experiment-spec.md)을 기준으로 최소 형태를 합의하고 Merge한 뒤 병렬 구현합니다. 소유권은 조정 책임을 뜻하며 다른 팀원의 수정을 금지하지 않습니다.

두 병렬 Issue가 데이터를 주고받아야 한다면 먼저 경계에 필요한 최소 데이터만 합의합니다. 해당 계약을 별도 선행 Issue로 Merge한 뒤 양쪽 구현을 시작합니다. 병렬 작업을 시작하기 위해 사용하지 않을 Interface를 미리 만들지 않습니다.

## Issue 원칙

모든 작업은 구현 전에 Issue로 등록합니다. Issue에는 결과, 범위, 완료 조건, 선행 관계, 제외 범위, 예상 수정 모듈을 작성합니다.

- 하나의 Issue는 독립적으로 Review 가능한 결과 하나만 만듭니다.
- 하루 안에 끝낼 수 있는 크기를 권장하고, 이틀을 넘길 것으로 보이면 나눕니다.
- 완료 조건은 명령, 테스트, 생성 파일처럼 확인 가능한 문장으로 씁니다.
- `Blocked by #<issue>`와 `Blocks #<issue>`로 작업 순서를 표시합니다.
- 막힌 Issue는 임시 계약을 팀이 합의하지 않은 상태에서 구현하지 않습니다.
- 작업 중 발견한 추가 요구는 현재 Issue 범위를 늘리지 않고 후속 Issue로 만듭니다.
- Credential, 명령 실행, 경로, 출력 redaction과 관련된 Issue는 보안 처리 방식을 적습니다.
- Issue는 PR Merge 시 `Closes #<issue>`로 닫고 미리 수동 종료하지 않습니다.

### Definition of Ready

담당자가 제품 동작을 임의로 결정하지 않고 구현할 수 있도록 결과, 완료 조건, 의존 Issue, 제외 범위가 작성되어 있어야 합니다.

### Definition of Done

- Issue 범위의 구현과 집중된 테스트가 있습니다.
- 관련 문서와 예시가 실제 동작과 일치합니다.
- `pytest`와 `ruff check .`가 통과합니다.
- Review 의견을 반영하거나 반영하지 않은 이유를 답변했습니다.
- 연결된 PR이 Merge되었습니다.

## 브랜치 전략

짧게 유지되는 Issue Branch를 `main`에 합치는 GitHub Flow를 사용합니다.

### `main`

- 항상 설치와 테스트가 가능한 상태를 유지합니다.
- 직접 개발, 직접 Commit, force push를 금지합니다.
- 모든 변경은 PR과 다른 Contributor의 승인 1개를 거칩니다.
- GitHub Actions의 Python 3.11 설치, `pytest`, `ruff check .`가 통과해야 합니다.
- Repository 설정에서 `Python 3.11` Check를 Branch protection의 필수 Check로 지정합니다.

초기 빈 저장소를 생성하는 첫 Commit만 부트스트랩 예외로 `main`에 게시합니다.

### Issue Branch

최신 `main`에서 다음 형식으로 생성합니다.

```text
feature/<issue-number>-<short-name>
```

예시:

```text
feature/4-base-model-adapter
feature/7-mcp-client
```

`short-name`은 영문 소문자와 hyphen을 사용합니다. 문서나 버그 수정도 별도 Issue에서 같은 형식을 사용해 Branch 규칙을 하나로 유지합니다.

```bash
git switch main
git pull --ff-only
git switch -c feature/4-base-model-adapter
```

Branch는 하나의 주요 Issue만 다룹니다. PR 최종 Review 전에 최신 `main`을 반영하고, 충돌 해결 후 테스트를 다시 실행합니다. Merge 후 원격 Branch를 삭제하고 다음 작업은 갱신된 `main`에서 시작합니다.

같은 public contract를 두 Branch가 동시에 수정해야 한다면 양쪽 Issue에 먼저 알립니다. 계약 소유 PR에서 문서와 테스트를 함께 수정하고 먼저 Merge한 뒤 의존 Branch가 따라가도록 합니다.

## Commit 원칙

Conventional Commit prefix는 영문으로 유지하고 제목 내용은 한국어로 작성합니다.

- `feat:` 사용자에게 보이는 기능
- `fix:` 결함 수정
- `docs:` 문서만 수정
- `test:` 테스트만 수정
- `refactor:` 동작을 바꾸지 않는 구조 개선
- `chore:` Tooling과 유지보수

예시:

```text
feat: 하네스 YAML 검증 추가
fix: Provider 누락 오류 메시지 수정
docs: Adapter 오류 경계 설명
test: 최대 단계 제한 회귀 테스트 추가
refactor: 실행 결과 변환 로직 단순화
chore: 개발 의존성 정리
```

- 제목은 명령형으로 짧고 구체적으로 작성합니다.
- 하나의 Commit에 Format 변경, 관계없는 Refactor, 기능 구현을 섞지 않습니다.
- 각 Commit은 가능하면 독립적으로 설치와 테스트가 가능해야 합니다.
- Issue 번호는 Commit 본문에 적을 수 있지만 공식 연결은 PR의 `Closes` 문장으로 관리합니다.

## PR 원칙

PR 제목과 본문은 한국어로 작성합니다. Draft PR은 공유 계약을 일찍 논의할 때 사용합니다.

PR 본문 필수 항목:

- 변경 이유와 목표
- 주요 변경사항
- 테스트 방법과 결과
- 알려진 제한사항과 후속 Issue
- 보안 및 의존성 경계 확인
- 마지막 줄의 `Closes #<issue-number>`

GitHub 자동 종료 기능 때문에 `Closes` keyword만 영문으로 유지합니다.

### Review와 Merge

- 자신의 PR은 다른 Contributor의 승인 없이 Merge하지 않습니다.
- Reviewer는 동작, 의존 방향, Secret 처리, 테스트, 문서의 구현 상태 표현을 확인합니다.
- 작성자는 모든 Review thread를 해결하거나 변경하지 않은 이유를 답변합니다.
- `Python 3.11` CI Check 통과를 Merge 조건으로 설정합니다.
- 2명 × 7일 MVP에서는 기본적으로 squash merge를 사용합니다.
- Migration이나 단계별 Commit 보존이 실제로 필요할 때만 merge commit을 선택합니다.
- Merge 후 Branch를 삭제하고 후속 작업은 새 Issue와 새 Branch에서 진행합니다.

## 로컬 검증

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
ruff check .
```

지원 기준은 Python 3.11 이상입니다. SQLite는 표준 라이브러리를 사용하므로 별도 DB Service가 필요하지 않습니다.

## CI

`.github/workflows/ci.yml`은 모든 Pull Request와 `main` Push에서 다음을 실행합니다.

```bash
python -m pip install -e ".[dev]"
ruff check .
pytest
```

Workflow는 `contents: read` 권한만 사용하고 Credential이나 Repository Secret을 요구하지 않습니다. 전체 Python Version Matrix, License 검사, Secret scan과 Release 검증은 제출 통합 Issue에서 추가합니다.
