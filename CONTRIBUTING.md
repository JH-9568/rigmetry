# Rigmetry 기여 가이드

Rigmetry는 초기 개발 단계입니다. 모든 변경은 작고 명확한 GitHub Issue를 기준으로 진행하며, 구현된 기능과 계획된 기능을 문서에서 분명히 구분해야 합니다.

## 작업 전 필수 확인

1. 저장소 루트의 [AGENTS.md](AGENTS.md)를 읽습니다.
2. 담당 GitHub Issue의 범위, 완료 조건, 선행 Issue, 제외 범위를 확인합니다.
3. 최신 `main`에서 `feature/<issue-number>-<short-name>` 브랜치를 만듭니다.
4. 하나의 PR에는 하나의 주요 Issue만 포함합니다.

초기 저장소 생성 이후에는 `main`에서 직접 개발하거나 직접 커밋하지 않습니다.

## 로컬 개발 환경

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
ruff check .
```

## Commit 원칙

Commit prefix는 영문 Conventional Commit 형식을 유지하고, prefix 뒤의 제목은 한국어로 작성합니다.

```text
feat: Harness Lock 생성 추가
fix: 누락된 Provider 오류 처리
docs: Replay 보장 범위 설명
test: Token Budget 종료 회귀 테스트 추가
refactor: Event 변환 로직 단순화
chore: Ruff 설정 정리
```

## PR 원칙

PR 제목과 본문은 한국어로 작성합니다. 변경 이유, 주요 변경사항, 테스트 결과, 제한사항과 후속 Issue를 포함합니다. 자동 Issue 종료를 위해 본문 마지막에 GitHub가 인식하는 영문 keyword를 유지합니다.

```text
Closes #<issue-number>
```

Credential, `.env`, 로컬 DB, 비공개 Workspace 데이터, Secret이 포함된 로그는 절대 Commit하지 않습니다.

역할 분배, 브랜치 전략, Issue 작성 및 Review 기준은 [Development Guide](docs/development.md)를 참고하세요.
