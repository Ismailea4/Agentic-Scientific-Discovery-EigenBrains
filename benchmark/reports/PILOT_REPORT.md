# EigenBrains empirical pilot report

Evidence: 24 paired cases x 5 models = 120 calls.
Known token-estimated cost: $0.00403632; 31 failed calls have unknown billing status. The preflight worst-case projection was $0.18763776 under the authorized $0.20 ceiling.

## Protocol adherence

- The same 24 development cases were run once per model in the same deterministic order.
- Prompt, evaluator, temperature (0), output cap (256), and case ordering were unchanged across models.
- Concurrency remained 1. No provider-compatibility exception changed the benchmark contract.
- Direct OpenAI inference remained excluded after its discovery probe returned HTTP 429.

## Per-model observations

| Model | Pass | Coverage | Conditional quality | Median latency | Known cost |
|---|---:|---:|---:|---:|---:|
| groq/openai/gpt-oss-20b | 20/24 (83.3%) | 100.0% | 83.3% | 641.9 ms | $0.00089670 |
| groq/qwen/qwen3.8-27b | 19/24 (79.2%) | 100.0% | 79.2% | 371.6 ms | $0.00150640 |
| openrouter/deepseek/deepseek-v4.1-flash | 19/24 (79.2%) | 100.0% | 79.2% | 2874.0 ms | $0.00130052 |
| gemini/gemini-3.5-flash-lite | 13/24 (54.2%) | 70.8% | 76.5% | 856.8 ms | $0.00033270 |
| anthropic/claude-sonnet-5-5 | 0/24 (0.0%) | 0.0% | n/a | 603.2 ms | $0.00000000 |

| Model | Success/failure | Malformed | Abstain | Severe | Mean / p90 / p95 latency | Tokens in/out | Unknown-cost calls |
|---|---:|---:|---:|---:|---:|---:|---:|
| anthropic/claude-sonnet-5-5 | 0/24 | 0 | 0 | 24 | 654.7 / 797.3 / 840.1 ms | 0/0 | 24 |
| gemini/gemini-3.5-flash-lite | 17/7 | 0 | 0 | 11 | 797.0 / 1081.4 / 1130.7 ms | 659/54 | 7 |
| groq/openai/gpt-oss-20b | 24/0 | 0 | 0 | 4 | 699.0 / 957.1 / 959.2 ms | 2660/2324 | 0 |
| groq/qwen/qwen3.8-27b | 24/0 | 0 | 0 | 5 | 386.6 / 452.0 / 525.8 ms | 1308/115 | 0 |
| openrouter/deepseek/deepseek-v4.1-flash | 24/0 | 0 | 0 | 5 | 5566.8 / 12221.3 / 18837.5 ms | 1640/2091 | 0 |

| Model | Wilson 95% pass interval | Bootstrap 95% quality interval |
|---|---:|---:|
| anthropic/claude-sonnet-5-5 | [0.0%, 13.8%] | [0.0%, 0.0%] |
| gemini/gemini-3.5-flash-lite | [35.1%, 72.1%] | [33.3%, 75.0%] |
| groq/openai/gpt-oss-20b | [64.1%, 93.3%] | [66.7%, 95.8%] |
| groq/qwen/qwen3.8-27b | [59.5%, 90.8%] | [62.5%, 95.8%] |
| openrouter/deepseek/deepseek-v4.1-flash | [59.5%, 90.8%] | [62.5%, 91.7%] |

### Task-family exceptions

Only families below perfect coverage/pass are listed; each family has two cases.

| Model | Primary non-perfect families | Narrow-sensitivity non-perfect families |
|---|---|---|
| anthropic/claude-sonnet-5-5 | classification 0/2, code_understanding_debugging 0/2, critique 0/2, evidence_verification 0/2, logical_reasoning 0/2, mathematical_reasoning 0/2, numerical_reasoning 0/2, planning 0/2, structured_extraction 0/2, synthesis 0/2, tool_use_reasoning 0/2, uncertainty_abstention 0/2 | classification 0/2, code_understanding_debugging 0/2, critique 0/2, evidence_verification 0/2, logical_reasoning 0/2, mathematical_reasoning 0/2, numerical_reasoning 0/2, planning 0/2, structured_extraction 0/2, synthesis 0/2, tool_use_reasoning 0/2, uncertainty_abstention 0/2 |
| gemini/gemini-3.5-flash-lite | critique 0/2, planning 0/2, structured_extraction 1/2, synthesis 0/2, tool_use_reasoning 0/2, uncertainty_abstention 0/2 | structured_extraction 1/2, synthesis 0/2, tool_use_reasoning 0/2, uncertainty_abstention 0/2 |
| groq/openai/gpt-oss-20b | critique 0/2, tool_use_reasoning 0/2 | tool_use_reasoning 0/2 |
| groq/qwen/qwen3.8-27b | critique 0/2, planning 0/2, tool_use_reasoning 1/2 | tool_use_reasoning 1/2 |
| openrouter/deepseek/deepseek-v4.1-flash | critique 0/2, planning 1/2, tool_use_reasoning 0/2 | critique 1/2, tool_use_reasoning 0/2 |

Provider failures count as failed benchmark outcomes. Severe failure equals objective score <= 0.2 in this binary pilot. No abstention was inferred from free text; only explicit runner flags count.

## Role hypotheses

- Solver: `groq/openai/gpt-oss-20b`.
- Cheap solver: `groq/openai/gpt-oss-20b`.
- Low-latency solver: `groq/qwen/qwen3.8-27b`.
- Verifier/critic candidate for the leading solver: `groq/qwen/qwen3.8-27b`.
- Most complementary full-coverage pair: `groq/openai/gpt-oss-20b + groq/qwen/qwen3.8-27b`.
- Most redundant full-coverage pair: `groq/openai/gpt-oss-20b + openrouter/deepseek/deepseek-v4.1-flash`.
- Structured-output: unresolved 2/2 tie among `groq/openai/gpt-oss-20b, groq/qwen/qwen3.8-27b, openrouter/deepseek/deepseek-v4.1-flash`.

These are pilot hypotheses, not architecture assignments. Pairwise confidence results and the loss covariance matrix are in the accompanying artifacts.

## Scoring sensitivity audit

The frozen primary evaluator used exact matching and remains the preregistered result. A post-hoc audit counts only case-specific critique taxonomy synonyms and whitespace around planning-list commas. It does not rescue provider failures, blank outputs, malformed outputs, or unapproved tool-name aliases.

| Model | Primary | Narrow sensitivity | Adjustments |
|---|---:|---:|---:|
| groq/qwen/qwen3.8-27b | 19/24 | 23/24 | +4 |
| groq/openai/gpt-oss-20b | 20/24 | 22/24 | +2 |
| openrouter/deepseek/deepseek-v4.1-flash | 19/24 | 21/24 | +2 |
| gemini/gemini-3.5-flash-lite | 13/24 | 17/24 | +4 |
| anthropic/claude-sonnet-5-5 | 0/24 | 0/24 | +0 |

Under this narrow audit, the solver candidate changes to `groq/qwen/qwen3.8-27b`. That ranking sensitivity is itself a pilot result: solver selection is unresolved until the evaluator contract is repaired and rerun on held-out cases.

The sensitivity-audit complementary pair is `groq/qwen/qwen3.8-27b + openrouter/deepseek/deepseek-v4.1-flash`; the redundant pair is `groq/openai/gpt-oss-20b + openrouter/deepseek/deepseek-v4.1-flash`.

## Paired failure structure

The table below is restricted to models with complete 24-case coverage. Conditional columns read P(right fails | left fails) and P(left fails | right fails).

| Pair | Corr(loss) | Disagree | Jaccard failures | Conditional R/L | Rescues R/L |
|---|---:|---:|---:|---:|---:|
| groq/openai/gpt-oss-20b + groq/qwen/qwen3.8-27b | 0.596 | 12.5% | 0.500 | 75.0%/60.0% | 1/2 |
| groq/openai/gpt-oss-20b + openrouter/deepseek/deepseek-v4.1-flash | 0.872 | 4.2% | 0.800 | 100.0%/80.0% | 0/1 |
| groq/qwen/qwen3.8-27b + openrouter/deepseek/deepseek-v4.1-flash | 0.747 | 8.3% | 0.667 | 80.0%/80.0% | 1/1 |

All three full-coverage pairwise quality comparisons remain unresolved at 95% confidence. The complete case matrix, task-family breakdown, paired confidence intervals, covariance matrix, and conditional-failure table are preserved as CSV/JSON artifacts.

## Next-stage projections (not executed)

| Stage | Calls | Conservative dollar ceiling |
|---|---:|---:|
| full_72_case_single_model | 360 | $0.562913 |
| a0_to_a6_upper_bound | 1368 | $6.303744 |
| ablations_three_frontier_candidates_upper_bound | 2592 | $11.943936 |
| conditional_verification_upper_bound | 648 | $2.985984 |
| sequential_racing_two_extra_repeats_upper_bound | 1296 | $5.971968 |

## Reliability limitations

- Anthropic Sonnet produced no successful calls in this pilot, despite the earlier Haiku probe succeeding.
- Gemini completed 17/24 calls; its last seven calls failed at the provider boundary. Its all-case score and conditional-on-success score must not be conflated.
- With only 24 cases and two observations per task type, task-specific rankings and tail claims remain weak.
- Exact provider billing was not queried. The report preserves unknown cost for failed calls.

## Stop condition

No full baseline, multi-agent architecture, ablation, conditional-verification, or sequential-racing calls were launched.
