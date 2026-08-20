# 2026 오픈소스 개발자대회 MVP 계획

목표 제출일은 2026년 8월 27일입니다. 2명이 7일 안에 완성된 Vertical Slice와 실제 비교 결과를 만드는 것을 최우선으로 합니다.

전체 진행 상황은 [Issue #9](https://github.com/JH-9568/rigmetry/issues/9)에서 추적합니다.

## 수상용 핵심 주장

> Rigmetry는 동일한 Task와 Token Budget에서 Harness 변경이 성공률과 비용에 미친 영향을 Digest로 검증하고, 기록된 Event를 외부 호출 없이 Offline Replay한다.

이 문장을 실제 실행 결과로 증명하지 못하는 기능은 제출 전 우선순위가 아닙니다.

## 역할 분담

### JH-9568: 실행 재현성 Track

- 공통 Model과 Event 계약
- Harness/Task Canonicalization과 Digest
- OpenAI-compatible Model Adapter
- Step·Timeout·Token Budget Runtime
- SQLite Event Trace와 Offline Replay
- CI, License 검증과 최종 제출 통합

담당 Issue:

- [#1 Experiment 핵심 계약과 Schema](https://github.com/JH-9568/rigmetry/issues/1)
- [#2 Harness·Task 검증과 Lock Digest](https://github.com/JH-9568/rigmetry/issues/2)
- [#4 OpenAI-compatible Adapter와 Token Budget Runtime](https://github.com/JH-9568/rigmetry/issues/4)
- [#5 SQLite Event 저장과 Offline Replay](https://github.com/JH-9568/rigmetry/issues/5)
- [#8 CI·라이선스·3분 시연 제출 패키지](https://github.com/JH-9568/rigmetry/issues/8)

### minsub1489: 평가·비교 Track

- 격리 Workspace lifecycle
- Terminal Tool과 Command Evaluator
- Task Runner
- Metric 집계와 Harness Compare
- Benchmark Fixture와 실제 30 Run 결과

담당 Issue:

- [#3 격리 Workspace·Terminal Tool·Command Evaluator](https://github.com/JH-9568/rigmetry/issues/3)
- [#6 Task Runner·Metric 집계·Harness Compare](https://github.com/JH-9568/rigmetry/issues/6)
- [#7 재현 가능한 Benchmark 3종과 실제 비교 결과](https://github.com/JH-9568/rigmetry/issues/7)

역할은 조정 책임이며 독점 소유권이 아닙니다. 담당자가 아닌 Contributor가 PR을 Review합니다.

## Dependency Graph

```text
                         ┌─→ #2 Config / Lock ───────┐
#1 공통 계약 ────────────┤                           ├─→ #4 Budget Runtime ─→ #5 Replay ─┐
                         └─→ #3 Workspace / Eval ────┴──────────────────────────────────┤
                                                                                       ↓
                                                                               #6 Compare
                                                                                       ↓
                                                                               #7 Benchmark
                                                                                       ↓
                                                                               #8 제출 패키지
```

#2와 #3은 #1 Merge 후 병렬 진행합니다. #4에서 정한 Event를 #5가 저장·재생하고, #3의 Workspace/Evaluator와 #4/#5의 실행 결과를 #6이 연결합니다.

## 7일 일정

| 날짜 | 통합 목표 | JH-9568 | minsub1489 |
|---|---|---|---|
| 8/20 | 계약과 범위 고정 | #1 | #1 Review, #3 설계 |
| 8/21 | 양쪽 기반 완료 | #2 Lock | #3 Workspace/Evaluator |
| 8/22 | 실제 Agent 실행 | #4 Runtime | #3 Tool 통합, #4 Review |
| 8/23 | 실행 저장·재생 | #5 Replay | #6 Runner/Metric 시작 |
| 8/24 | End-to-End 비교 | #5 통합 | #6 Compare 완료 |
| 8/25 | 실제 증거 생성 | Benchmark 지원 | #7 총 30 Run |
| 8/26 | 제출 후보 고정 | #8 CI/License | 결과표·시연 검증 |
| 8/27 | 새 Clone 최종 검증 | 공동 제출 | 공동 제출 |

하루 목표가 지연되면 후속 기능을 축소하고 End-to-End 흐름을 먼저 살립니다.

## 제출 필수 조건

- [ ] `rigmetry validate`가 잘못된 Config를 설명 가능한 오류로 거부한다.
- [ ] `rigmetry lock`이 같은 입력에서 같은 Digest를 생성한다.
- [ ] `rigmetry run`이 격리 Workspace에서 Task를 실행하고 평가한다.
- [ ] Step, Timeout, Token Budget 종료 사유를 구분한다.
- [ ] Event와 Result가 SQLite에 Credential 없이 저장된다.
- [ ] `rigmetry replay --offline` 중 Model과 Tool 외부 호출이 0회다.
- [ ] `rigmetry compare`가 실제 반복 Run으로 `success@budget`과 성공당 Token을 계산한다.
- [ ] 3 Task × 2 Variant × 5회인 총 30 Run 결과를 공개한다.
- [ ] 새 Clone에서 설치·테스트·시연 명령이 동작한다.
- [ ] 3분 시연에서 Lock → Run → Compare → Replay 흐름을 보여준다.

## Scope Freeze

제출 전에는 다음을 구현하지 않습니다.

- Claude, Gemini, Ollama 등 추가 Provider
- Web Dashboard
- Multi-agent, Memory와 Human-in-the-loop
- 대규모 Benchmark와 Leaderboard
- 자동 Harness 최적화
- 임의 가중치 기반 종합 점수
- 완전한 Container/VM Sandbox

## 실패 시 축소 순서

일정이 부족하면 다음 순서로 제외합니다.

1. MCP 실제 연결
2. 가격 기반 금액 계산
3. Confidence Interval
4. Replay의 Evaluator 재실행

다음 항목은 제외하지 않습니다.

- Config Digest
- Token Budget
- 격리 Workspace
- Command Evaluator
- 실제 Run 기반 Compare
- Secret Redaction

## 3분 시연 순서

1. Baseline과 Debugging Skill Candidate의 Config Diff를 보여줍니다.
2. 두 Config의 Lock Digest를 생성합니다.
3. 같은 Task와 50,000 Token Budget에서 실행합니다.
4. 실제 `success@budget`, 성공당 Token, 단계 수를 비교합니다.
5. 한 Run을 Offline Replay하고 외부 호출 0회를 확인합니다.
6. live rerun의 Model 출력 동일성은 보장하지 않는다는 재현성 경계를 설명합니다.
