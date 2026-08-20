# OpenHarness Agent 작업 지침

이 파일은 OpenHarness를 수정하는 모든 Coding Agent의 시작점입니다. 작업 요청만 보고 바로 구현하지 말고 아래 문서와 Issue를 먼저 읽습니다.

## 필수 읽기 순서

1. [README.md](README.md): 프로젝트 목표, 현재 구현 상태, MVP 범위
2. [docs/architecture.md](docs/architecture.md): 모듈 책임과 의존성 경계
3. [docs/harness-spec.md](docs/harness-spec.md): Harness Draft 명세
4. [docs/task-spec.md](docs/task-spec.md): Task Draft 명세
5. [docs/development.md](docs/development.md): 역할, Issue, Branch, Commit, PR 원칙
6. [CONTRIBUTING.md](CONTRIBUTING.md): 기여 전 확인사항
7. 담당 GitHub Issue와 선행·후속 Issue

## 구현 전 확인

- Issue의 목표, 완료 조건, 제외 범위가 명확한지 확인합니다.
- 현재 Branch가 `feature/<issue-number>-<short-name>` 형식인지 확인합니다.
- `git status`로 다른 사람의 변경이 있는지 확인하고 관계없는 변경을 수정하지 않습니다.
- 변경할 Package와 연결된 테스트·문서·예시를 먼저 찾습니다.
- 공유 계약을 바꿀 경우 의존 Issue와 병렬 Branch에 미치는 영향을 확인합니다.

Issue 없이 새 핵심 기능을 만들지 않습니다. Issue가 불명확해 제품 동작이 달라질 수 있다면 먼저 질문하거나 Issue를 구체화합니다.

## Architecture 규칙

- `runtime`은 구체적인 OpenAI, DeepSeek 또는 MCP Client 구현에 직접 의존하지 않습니다.
- Provider SDK 객체와 오류는 Adapter 경계 안에서 프로젝트 내부 타입으로 변환합니다.
- Credential은 환경변수에서 Runtime에만 주입하고 Config, DB, Trace, 로그, Report에 저장하지 않습니다.
- Task는 격리된 Workspace에서 실행하며 원본 Workspace를 변경하지 않습니다.
- Skill은 지침 데이터이며 Tool 권한을 부여하거나 보안 경계를 우회하지 않습니다.
- 새로운 추상화는 실제 두 번째 구현이나 명확한 경계가 필요할 때만 추가합니다.

## 현재 구현 금지 범위

별도 GitHub Issue가 배정되기 전에는 다음 기능을 구현하지 않습니다.

- Agent Loop
- 실제 OpenAI-compatible 및 DeepSeek API 호출
- 실제 MCP 연결과 Tool 실행
- 실제 Workspace 격리와 Evaluator
- Experiment Runner, Benchmark, Harness Compare

문서의 예시와 목표 CLI를 구현된 기능처럼 표현하지 않습니다.

## 완료 전 검증

```bash
pytest
ruff check .
```

Config나 예시 YAML을 변경했다면 YAML 파싱도 확인합니다. 공개 동작 또는 계약을 변경했다면 관련 테스트, 문서, 예시를 같은 PR에서 갱신합니다.

## Git 작성 언어

- Commit: 영문 prefix와 한국어 제목 (`feat: 하네스 검증 추가`)
- PR 제목과 본문: 한국어
- 자동 Issue 종료 문장: `Closes #<issue-number>`

Agent는 사용자 승인 없이 Commit, Push, PR 생성, Issue 작성 또는 Merge를 수행하지 않습니다.
