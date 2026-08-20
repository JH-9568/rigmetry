# 2026 오픈소스 개발자대회 MVP 계획

목표 제출일은 2026년 8월 27일입니다. 2명이 7일 안에 완성된 Vertical Slice와 실제 비교 결과를 만드는 것을 최우선으로 합니다.

전체 진행 상황은 [Issue #9](https://github.com/JH-9568/rigmetry/issues/9)에서 추적합니다.

## 수상용 핵심 주장

> Rigmetry는 Agent Harness 변경을 content-addressed Lock으로 고정하고, 동일한 Task·Model·Budget의 통제된 반복 실행과 무호출 Replay로 성공률과 Token 효율 변화를 검증 가능한 Evidence로 만든다.

이 문장을 실제 실행 결과로 증명하지 못하는 기능은 제출 전 우선순위가 아닙니다.

## 역할 분담

### JH-9568: 실행 재현성 Track

- 공통 Model과 Event 계약
- Harness/Task Canonicalization과 Digest
- OpenAI-compatible·Ollama Native Model Adapter
- Step·Timeout·Token Budget Runtime
- SQLite Event Trace와 Offline Replay
- Event 무결성 검증, CI, License 검증과 최종 제출 통합

담당 Issue:

- [#1 Experiment·Evidence 핵심 계약과 Schema](https://github.com/JH-9568/rigmetry/issues/1)
- [#2 Harness·Task·Experiment 검증과 Lock Digest](https://github.com/JH-9568/rigmetry/issues/2)
- [#4 Model Adapter Capability와 Token Budget Runtime](https://github.com/JH-9568/rigmetry/issues/4)
- [#5 Event hash chain과 Boundary Offline Replay](https://github.com/JH-9568/rigmetry/issues/5)
- [#8 CI·Evidence 검증·3분 시연 제출 패키지](https://github.com/JH-9568/rigmetry/issues/8)

### minsub1489: 평가·비교 Track

- disposable Workspace lifecycle
- Terminal Tool과 Command Evaluator
- Task Runner
- Experiment 통제 검증, Metric 집계와 Harness Compare
- Evidence Bundle과 Verify
- Benchmark Fixture와 실제 30 Run 결과

담당 Issue:

- [#3 Disposable Workspace·Terminal Tool·Command Evaluator](https://github.com/JH-9568/rigmetry/issues/3)
- [#6 통제 Experiment·Metric·Evidence Bundle](https://github.com/JH-9568/rigmetry/issues/6)
- [#7 사전 동결 Benchmark 3종과 실제 비교 결과](https://github.com/JH-9568/rigmetry/issues/7)

역할은 조정 책임이며 독점 소유권이 아닙니다. 담당자가 아닌 Contributor가 PR을 Review합니다.

## Dependency Graph

```text
                         ┌─→ #2 Config / Lock ───────┐
#1 공통 계약 ────────────┤                           ├─→ #4 Budget Runtime ─→ #5 Replay ─┐
                         └─→ #3 Workspace / Eval ────┴──────────────────────────────────┤
                                                                                       ↓
                                                                               #6 Compare / Evidence
                                                                                       ↓
                                                                               #7 Benchmark
                                                                                       ↓
                                                                               #8 제출 패키지
```

#2와 #3은 #1 Merge 후 병렬 진행합니다. #4에서 정한 Event를 #5가 저장·재생하고, #3의 Workspace/Evaluator와 #4/#5의 실행 결과를 #6이 연결합니다.

## MVP Model 전략

- 원격 기준선은 `openai-compatible` Adapter로 구현합니다.
- 로컬 기준선은 Ollama Native `/api/chat` Adapter로 구현합니다.
- DeepSeek 등 OpenAI 호환 서비스는 별도 Adapter를 만들지 않습니다.
- 두 Adapter는 같은 내부 Model 요청·응답·Usage 계약을 만족해야 합니다.
- 실제 비교 실험에서는 Model 차이와 Harness 차이를 한 번에 섞지 않고, 같은 Model 안에서 Harness Variant를 비교합니다.

## 실험 프로토콜

- `experiment.yaml`이 Variant, 공유 조건, 허용 Diff, 반복 횟수와 실행 순서를 정의합니다.
- 실행 전에 Experiment, Harness, Task, Workspace Fixture와 Evaluator를 Lock합니다.
- `allow_diff` 밖의 Config 차이가 있으면 실행을 거부합니다.
- Baseline과 Candidate 순서는 무작위화하거나 교차 배치합니다.
- 첫 Run 이후 Fixture 또는 Evaluator가 바뀌면 새 Experiment로 취급합니다.
- 성공한 Run만 고르지 않고 Infrastructure 오류를 포함한 전체 종료 사유를 보존합니다.
- OpenAI-compatible과 Ollama 결과는 Provider별로 집계하며 Token 수를 직접 순위화하지 않습니다.

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

최소 CI는 첫 구현 PR부터 병렬로 구성합니다. #8의 후반 작업은 License 검증, 결과보고서, 3분 시연과 Release 통합이며 CI 시작을 선행 Issue 완료까지 막지 않습니다.

## 제출 필수 조건

- [ ] `rigmetry validate`가 잘못된 Config를 설명 가능한 오류로 거부한다.
- [ ] `rigmetry lock`이 Experiment와 참조 Artifact에서 같은 Digest를 생성한다.
- [ ] `rigmetry run`이 disposable Workspace에서 원본을 변경하지 않고 Task를 실행·평가한다.
- [ ] Adapter Capability가 Experiment 요구사항을 충족하지 않으면 외부 호출 전에 거부한다.
- [ ] Step, Timeout, Token Budget 종료 사유를 구분한다.
- [ ] Event hash chain과 Result가 SQLite에 Credential 없이 저장된다.
- [ ] `rigmetry replay --offline` 중 Model, Tool과 Evaluator 외부 호출이 0회다.
- [ ] Replay가 같은 Runtime 상태 전이, 종료 사유와 파생 Metric을 재계산한다.
- [ ] `rigmetry compare`가 허용된 Diff와 실제 반복 Run으로 `success@budget`과 성공당 Token을 계산한다.
- [ ] `rigmetry verify evidence/`가 Lock, Event chain, Run 누락과 Report 재계산을 검증한다.
- [ ] 3 Task × 2 Variant × 5회인 총 30 Run 결과를 공개한다.
- [ ] Benchmark Config와 Fixture를 첫 Run 전에 고정하고 전체 Raw Result를 공개한다.
- [ ] 새 Clone에서 설치·테스트·시연 명령이 동작한다.
- [ ] 3분 시연에서 Lock → Run → Compare → Replay → Verify 흐름을 보여준다.

## Scope Freeze

제출 전에는 다음을 구현하지 않습니다.

- Claude, Gemini, vLLM 등 세 번째 Provider Adapter
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
4. Provider 간 종합 비교

다음 항목은 제외하지 않습니다.

- Config Digest
- Experiment 통제 조건과 허용 Diff 검증
- Token Budget
- 원본 보호용 disposable Workspace
- Command Evaluator
- 실제 Run 기반 Compare
- 무호출 Runtime Replay와 Evidence 검증
- Secret Redaction

## 3분 시연 순서

1. Baseline과 Debugging Skill Candidate의 허용된 한 가지 Config Diff를 보여줍니다.
2. Experiment와 참조 Artifact의 Lock Digest를 생성합니다.
3. 같은 Task·Model·50,000 Token Budget에서 무작위 순서로 반복 실행합니다.
4. 실제 `success@budget`, 성공당 Token, 단계 수와 전체 종료 사유를 비교합니다.
5. 한 Run을 Offline Replay하고 Model·Tool·Evaluator 외부 호출 0회를 확인합니다.
6. Evidence Bundle을 Verify하고 Event 하나를 바꾸면 내부 일관성 검사가 실패함을 보여줍니다.
7. live rerun의 Model 출력, 보안 Sandbox와 통계적 유의성을 보장하지 않는 경계를 설명합니다.
