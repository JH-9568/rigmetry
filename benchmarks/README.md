# Frozen MVP Benchmark

이 디렉터리는 Issue #7의 사전 동결 Coding Benchmark 3종을 담습니다. 각 Experiment는
`qwen2.5-coder:1.5b` Ollama Model, 같은 Task·Terminal Tool·Runtime Budget을 사용하고
Candidate에만 `debugging/SKILL.md`를 추가합니다.

```bash
rigmetry validate benchmarks/experiments/tag-normalization.yaml
rigmetry validate benchmarks/experiments/discount-calculation.yaml
rigmetry validate benchmarks/experiments/retry-schedule.yaml

rigmetry compare benchmarks/experiments/tag-normalization.yaml -d results/tag-normalization.sqlite
rigmetry compare benchmarks/experiments/discount-calculation.yaml -d results/discount-calculation.sqlite
rigmetry compare benchmarks/experiments/retry-schedule.yaml -d results/retry-schedule.sqlite
```

각 Task·Variant는 5회 실행되며 Experiment별 seed가 Variant 순서를 고정합니다. 작은 표본의
관측 결과이며 통계적 유의성이나 Skill의 일반적인 인과 효과를 주장하지 않습니다.
