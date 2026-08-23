# Frozen MVP Benchmark

이 디렉터리는 Issue #7의 사전 동결 Coding Benchmark 3종을 담습니다. 정식 Experiment는
`llama3.2:3b` Ollama Model, 같은 Task·Terminal Tool·Runtime Budget을 사용하고 Candidate에만
`debugging/SKILL.md`를 추가합니다. 최초 `qwen2.5-coder:1.5b` 실험은 Model이 Tool call을
content로 출력해 10회 모두 실패한 pilot이며 별도 digest와 Evidence로 그대로 보존합니다.

```bash
rigmetry validate benchmarks/experiments/tag-normalization-llama32.yaml
rigmetry validate benchmarks/experiments/discount-calculation-llama32.yaml
rigmetry validate benchmarks/experiments/retry-schedule-llama32.yaml

rigmetry compare benchmarks/experiments/tag-normalization-llama32.yaml -d results/tag-normalization.sqlite
rigmetry compare benchmarks/experiments/discount-calculation-llama32.yaml -d results/discount-calculation.sqlite
rigmetry compare benchmarks/experiments/retry-schedule-llama32.yaml -d results/retry-schedule.sqlite
```

각 Task·Variant는 5회 실행되며 Experiment별 seed가 Variant 순서를 고정합니다. 작은 표본의
관측 결과이며 통계적 유의성이나 Skill의 일반적인 인과 효과를 주장하지 않습니다.
