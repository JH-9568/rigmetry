# Rigmetry Agent 작업 지침

이 파일은 Rigmetry를 수정하는 모든 Coding Agent의 시작점입니다. 작업 요청만 보고 바로 구현하지 말고 문서와 담당 Issue를 먼저 읽습니다.

## 필수 읽기 순서

1. [README.md](README.md): 제품 정의, 현재 구현 상태, MVP 범위
2. [docs/mvp-plan.md](docs/mvp-plan.md): 담당자, Issue dependency, 7일 일정과 Scope Freeze
3. [docs/experiment-spec.md](docs/experiment-spec.md): Variant, 통제 조건과 반복 계획
4. [docs/experiment-model.md](docs/experiment-model.md): Digest, Event, Replay, Token, Compare와 Evidence 계약
5. [docs/contracts.md](docs/contracts.md): 구현된 공통 Python 타입과 Package 연결 규칙
6. [docs/config-lock.md](docs/config-lock.md): 구현된 Schema, Canonicalization과 Lock 규칙
7. [docs/architecture.md](docs/architecture.md): 모듈 책임과 의존성 방향
8. [docs/harness-spec.md](docs/harness-spec.md): Harness Draft 명세
9. [docs/task-spec.md](docs/task-spec.md): Task Draft 명세
10. [docs/development.md](docs/development.md): 역할, Issue, Branch, Commit, PR 원칙
11. [CONTRIBUTING.md](CONTRIBUTING.md)와 담당 GitHub Issue

## 제품 중심

Rigmetry는 범용 Agent Framework가 아니라 다음을 위한 Harness 실험 엔진입니다.

- 실행 구성 fingerprint와 Lock
- 제한된 Runtime과 append-only Event Trace
- 기록된 경계 결과를 사용하는 무호출 Runtime replay
- 동일 Task·Model·Budget의 통제된 Harness 비교
- Lock, Event, Run과 Report를 묶은 검증 가능한 Evidence Bundle

Provider 수나 Tool 수를 늘리는 것보다 재현 가능하고 공정한 비교를 우선합니다.

## 구현 전 확인

- Issue의 목표, 완료 조건, 의존 관계와 제외 범위를 확인합니다.
- Branch가 `feature/<issue-number>-<short-name>` 형식인지 확인합니다.
- `git status`로 다른 사람의 변경을 확인하고 관계없는 변경을 수정하지 않습니다.
- 변경할 Package와 연결된 테스트·문서·예시를 먼저 찾습니다.
- 공개 계약 변경이 병렬 Branch에 미치는 영향을 확인합니다.

Issue 없이 새 핵심 기능을 만들지 않습니다.

## Architecture 규칙

- `runtime`은 구체적인 OpenAI-compatible, Ollama 또는 MCP Client 구현에 직접 의존하지 않습니다.
- Provider 응답, 오류와 Token usage는 Adapter 경계에서 내부 타입으로 변환합니다.
- Credential은 환경변수에서 Runtime에만 주입하고 Config, Lock, DB, Trace, 로그, Report에 저장하지 않습니다.
- `run_id`, `harness_digest`, `task_digest`, `environment_digest`를 혼용하지 않습니다.
- Experiment의 `require_same`, `allow_diff` 밖의 차이를 허용하지 않습니다.
- 측정할 수 없는 Token 값은 `0`이 아니라 `null`입니다.
- 서로 다른 Provider/tokenizer의 Token 수를 같은 단위처럼 직접 비교하지 않습니다.
- Task는 disposable Workspace에서 실행하고 원본을 변경하지 않습니다. 이를 보안 Sandbox라고 표현하지 않습니다.
- Skill은 지침 데이터이며 Tool 권한을 부여하지 않습니다.
- 새로운 추상화는 실제 경계가 필요할 때만 추가합니다.

## 재현성 표현

외부 Model의 live rerun이 같은 응답을 생성한다고 주장하지 않습니다. Config 동일성, 저장된 Model·Tool·Evaluator 결과를 사용하는 Runtime replay, 반복 실험의 통계적 비교와 Evidence 내부 무결성을 구분합니다.

## 현재 구현 금지 범위

별도 GitHub Issue가 배정되기 전에는 다음 기능을 구현하지 않습니다.

- 실제 Agent Loop와 Model API 호출
- 실제 MCP 연결과 Tool 실행
- Disposable Workspace와 Evaluator
- Event Replay와 Harness Compare

문서의 목표 CLI와 예시 수치를 구현된 기능이나 실제 Benchmark 결과처럼 표현하지 않습니다.

## 완료 전 검증

```bash
pytest
ruff check .
```

Config나 예시 YAML을 변경했다면 YAML 파싱도 확인합니다. 공개 동작 또는 계약 변경 시 관련 테스트, 문서와 예시를 같은 PR에서 갱신합니다.

## Git 작성 언어

- Commit: 영문 prefix와 한국어 제목 (`feat: Harness Lock 생성 추가`)
- PR 제목과 본문: 한국어
- 자동 Issue 종료 문장: `Closes #<issue-number>`

Agent는 사용자 승인 없이 Commit, Push, PR 생성, Issue 작성 또는 Merge를 수행하지 않습니다.
