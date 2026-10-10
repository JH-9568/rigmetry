# Rigmetry

**에이전트 하네스의 차이를, 실행 조건과 근거까지 남겨 비교합니다.**

모델 이름이나 최종 답만 비교하지 않고 프롬프트·Skill·Tool·Workspace·Budget·Evaluator를 고정해 실험하는 Python 엔진입니다.

[프로젝트 소개](https://jinhyeong-studio.jinhyeong9568-663.workers.dev/projects/rigmetry) · [실험 명세](docs/experiment-spec.md) · [기여 안내](CONTRIBUTING.md)

```text
Define → Lock → Run → Trace → Evaluate → Replay → Compare → Verify
```

## 핵심 기능

| 단계 | 남기는 근거 |
| --- | --- |
| Lock | Config와 참조 artifact의 content digest |
| Run / Trace | 단계·시간·Token 예산 안의 실행과 redacted event |
| Evaluate | 에이전트와 분리된 성공 판정 |
| Replay | 저장된 Model·Tool·Evaluator 결과를 이용한 무호출 재계산 |
| Compare | 허용한 차이만 가진 variant의 반복 실행 |
| Verify | Lock·Event hash chain·Run·Report의 내부 일관성 |

**Python 3.11+ · Pydantic · SQLite**  
Model adapter: **OpenAI-compatible / Ollama Native**

## 빠르게 시작하기

```bash
git clone https://github.com/JH-9568/rigmetry.git
cd rigmetry
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

rigmetry --help
rigmetry validate examples/experiments/debugging-skill.yaml
rigmetry lock examples/experiments/debugging-skill.yaml
```

실제 모델 실행에는 harness가 지정한 API 환경 변수 또는 로컬 Ollama가 필요합니다. 키는 [.env.example](.env.example)을 참고해 실행 환경에만 주입하고 Config·Lock·Trace·Report에 넣지 않습니다.

<details>
<summary>실행·재생·비교 CLI</summary>

```bash
rigmetry run --harness harness.yaml --task task.yaml --database runs.sqlite
rigmetry replay <run-id> --offline --database runs.sqlite
rigmetry compare experiment.yaml --database runs.sqlite
rigmetry export <experiment-id> --database runs.sqlite --output evidence/
rigmetry verify evidence/
```

입력 예시는 [examples](examples), 필드 정의는 [Harness](docs/harness-spec.md) · [Task](docs/task-spec.md) · [Experiment](docs/experiment-spec.md)를 참고합니다.

</details>

## 결과를 읽을 때

- `success@budget`, 성공당 Token, 호출 수·단계 수·시간·종료 사유를 구분합니다.
- 측정할 수 없는 Token 값은 **0이 아닌 null**입니다.
- 다른 provider/tokenizer의 Token 수를 같은 단위처럼 직접 비교하지 않습니다.
- Offline replay는 **저장된 경계 결과**를 사용합니다. 외부 모델의 live rerun이 같은 답을 생성한다는 보장이 아닙니다.
- disposable Workspace는 작업 사본이며 **Container/VM 보안 sandbox가 아닙니다.**
- Evidence의 hash chain은 내부 무결성 확인이지 외부 공증·전자서명이 아닙니다.

현재 초기 MVP vertical slice가 구현되어 있습니다. 실제 MCP 연결·Terminal 이외 Tool 확장과 실제 benchmark 성과는 별도 범위입니다. 문서 예시 수치를 성능 결과로 사용하지 않습니다.

## 개발과 문서

```bash
pytest
ruff check .
```

[Architecture](docs/architecture.md) · [공통 계약](docs/contracts.md) · [Lock](docs/config-lock.md) · [Runtime](docs/runtime.md) · [Replay](docs/replay.md) · [Experiment Model](docs/experiment-model.md) · [개발 규칙](docs/development.md)

**JH-9568:** 실행 구성·Runtime·Trace·재현성 코어  
**minsub1489:** Task·평가·Metric·비교  
공통 계약과 통합 검증은 함께 진행하며, 변경은 Issue → PR → 다른 기여자 리뷰를 거칩니다.

**License:** [MIT](LICENSE)
