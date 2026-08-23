# MVP Benchmark Results

실행일은 2026-08-24(KST)입니다. 정식 결과는 `llama3.2:3b` Ollama Native Adapter로
3 Task × 2 Variant × 5회, 총 30 Run을 실행한 관측값입니다. Baseline과 Candidate의 유일한
허용 차이는 `harness.skills`이며 Candidate에만 Focused Debugging Workflow가 있습니다.

## 고정 조건

- Provider/Model: `ollama` / `llama3.2:3b`
- Tool: 내장 `terminal`
- Budget: 최대 8 steps, 60초, 6,000 total tokens
- Evaluator: Task별 `python -m unittest discover -s tests -q`, 20초
- 반복: Variant별 5회
- 순서: seed 7201, 7202, 7203으로 Task별 무작위화
- Workspace: 매 Run마다 원본 Fixture의 disposable 사본
- 허용 Diff: `harness.skills`만

## 정식 30 Run 결과

| Task | Variant | success@budget | tokens/success | 평균 total tokens | 평균 steps | 평균 tool calls | 평균 시간(ms) | 종료 사유 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| tag-normalization | baseline | 0/5 | null | 630.6 | 1.4 | 0.4 | 3590.0 | evaluation_failed 5 |
| tag-normalization | candidate | 0/5 | null | 454.4 | 1.0 | 0.0 | 1885.4 | evaluation_failed 5 |
| discount-calculation | baseline | 0/5 | null | 1273.4 | 2.2 | 1.4 | 12207.8 | evaluation_failed 5 |
| discount-calculation | candidate | 0/5 | null | 1039.6 | 1.8 | 0.8 | 6446.6 | evaluation_failed 5 |
| retry-schedule | baseline | 0/5 | null | 1087.0 | 1.8 | 0.8 | 6324.0 | evaluation_failed 5 |
| retry-schedule | candidate | 0/5 | null | 1090.8 | 1.6 | 0.6 | 9932.6 | evaluation_failed 5 |

성공 Run이 없으므로 `tokens_per_success`는 숫자를 만들지 않고 `null`과
`no_successful_runs` 사유로 보존했습니다. Candidate는 세 Task 어디에서도 성공으로 이어지지
않았습니다. 따라서 이 표본은 해당 Skill의 품질 개선을 지지하지 않습니다. 실패 원인은 저장된
Model/Tool Boundary로 추가 분석할 수 있습니다.

이는 작은 로컬 Model과 5회 반복에서 얻은 관측 결과입니다. 통계적 유의성, 다른 Model로의 일반화,
Skill의 보편적인 인과 효과를 주장하지 않습니다. Provider가 하나뿐이므로 Provider 간 Token 비교도
하지 않았습니다.

## Pilot 10 Run

최초 동결한 `qwen2.5-coder:1.5b` tag-normalization 10 Run은 Model이 Tool call을 구조화된
응답 대신 message content로 출력해 Tool 호출 0회, 성공 0/10으로 끝났습니다. 결과가 나쁘다는
이유로 삭제하지 않고 `pilot-tag-normalization-qwen25` Evidence와 raw SQLite를 함께 공개합니다.
정식 Model/Prompt는 별도 Harness와 Experiment digest로 다시 동결했습니다.

## Cache 수정 전 30 Run

최초 정식 30 Run에서는 Evaluator가 원본 Fixture에 생성한 `__pycache__`가 Workspace digest에
포함되는 문제를 발견했습니다. 해당 결과를 선택적으로 폐기하지 않고 `pre-cache-fix-*` Evidence와
raw SQLite로 보존했습니다. 다만 clean clone 재현성을 만족하지 않으므로 위 정식 분석에서는 제외하고,
생성 cache를 Workspace lock과 disposable copy에서 제외한 뒤 같은 동결 조건으로 30 Run을 전부
다시 실행했습니다.

## Evidence 검증

```bash
rigmetry verify results/evidence/tag-normalization
rigmetry verify results/evidence/discount-calculation
rigmetry verify results/evidence/retry-schedule
rigmetry verify results/evidence/pilot-tag-normalization-qwen25
rigmetry verify results/evidence/pre-cache-fix-tag-normalization
rigmetry verify results/evidence/pre-cache-fix-discount-calculation
rigmetry verify results/evidence/pre-cache-fix-retry-schedule
```

일곱 Bundle 모두 Artifact digest, Lock/Control, Event hash chain, 계획 Run 수, Report 재계산,
알려진 Secret pattern과 외부 호출 0회의 Offline Replay 검증을 통과했습니다. 정식 Evidence digest:

- tag-normalization: `sha256:c29ed95e1879bf87b324788ed7f9ae8df9d8b5c37c671b2b13a93da93128c8bb`
- discount-calculation: `sha256:1af68089486957163400577af510072c0d62bb30810ec3ca3054bf9041e293e4`
- retry-schedule: `sha256:88fca071bb1b427ebdb49206840d8b5e1a7ed5cc854279378f711ff2150fb259`

`results/raw/`은 live 실행 직후의 SQLite이며, 각 Evidence의 `runs.sqlite`는 해당 Experiment의
계획 Run만 골라 이식 가능하게 복사한 검증 대상입니다.
