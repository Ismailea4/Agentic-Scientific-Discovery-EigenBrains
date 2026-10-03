# Architecture Baseline v0 — FROZEN

This report leads with measured evidence. Offline replay and provider-backed confirmation are reported separately.

## Headline finding

Qwen → selective GPT-OSS escalation matched always-both held-out quality (0.750) while using 16.0% less estimated cost and 35.2% less latency in offline replay.

This is an efficiency result, not evidence of a quality gain: the provider-backed confirmation produced zero rescues and zero damage on this 12-case held-out set, and the paired quality differences remain statistically unresolved.

## Provider diagnosis

| Provider/model | Result | Safe classification | HTTP status |
|---|---|---|---:|
| anthropic/claude-sonnet-5-5 | failure | provider_request_rejected | 400 |
| anthropic/claude-haiku-4-5-20251001 | success | available | — |
| gemini/gemini-3.5-flash-lite | success | available | — |

## Single-model evidence (72 identical cases each)

| Provider/model | Availability (95% Wilson) | Correct given success (95% Wilson) | Operational correct | Severe operational failure | Mean latency on success (ms) |
|---|---:|---:|---:|---:|---:|
| groq/openai/gpt-oss-20b | 0.653 [0.538, 0.752] | 0.915 [0.801, 0.966] | 0.597 | 0.403 | 764.9 |
| groq/qwen/qwen3.8-27b | 0.639 [0.524, 0.740] | 0.913 [0.797, 0.966] | 0.583 | 0.417 | 448.2 |
| openrouter/deepseek/deepseek-v4.1-flash | 1.000 [0.949, 1.000] | 0.861 [0.763, 0.923] | 0.861 | 0.139 | 7755.6 |

## Held-out S0–S4 offline replay (12 sealed cases)

These are counterfactual replay estimates from paired cached single-model observations, not executed multi-agent architectures.

| Policy | Quality (95% bootstrap) | Cost/case (USD) | Latency/case (ms) | Failure rate | Tail risk | Empirical Pareto | Robust Pareto |
|---|---:|---:|---:|---:|---:|---|---|
| S0 | 0.833 [0.583, 1.000] | 0.00003371 | 1065.0 | 0.167 | 1.000 | yes | yes |
| S1 | 0.750 [0.500, 1.000] | 0.00006087 | 526.9 | 0.250 | 1.000 | yes | yes |
| S2 | 0.750 [0.500, 1.000] | 0.00008324 | 1591.9 | 0.250 | 1.000 | no | yes |
| S3 | 0.750 [0.500, 1.000] | 0.00006992 | 1030.9 | 0.250 | 1.000 | no | yes |
| S4 | 0.833 [0.583, 1.000] | 0.00005438 | 1377.8 | 0.167 | 1.000 | no | yes |

## Selective-escalation economics (offline replay)

| Policy | Escalation | Rescue | Damage | Δ quality | Δ cost | Δ latency (ms) | Saving vs always-both |
|---|---:|---:|---:|---:|---:|---:|---:|
| S3 vs S1 | 0.583 | 0.000 | 0.000 | 0.000 | 0.00002038 | 504.0 | 0.00001333 |
| S4 vs S0 | 0.583 | 0.000 | 0.000 | 0.000 | 0.00003200 | 312.9 | 0.00002887 |
| S2 vs S1 | 1.000 | 0.000 | 0.000 | 0.000 | 0.00003371 | 1065.0 | 0.00000000 |

## Provider-backed verifier confirmation

These rows are actual verifier calls on top of cached first-pass held-out observations. They are not offline replay.

| Policy | n | Quality (95% Wilson) | Escalations | Rescues | Damage |
|---|---:|---:|---:|---:|---:|
| S3_PROVIDER_BACKED | 12 | 0.750 [0.468, 0.911] | 7 | 0 | 0 |
| S4_PROVIDER_BACKED | 12 | 0.833 [0.552, 0.953] | 7 | 0 | 0 |

## Failure diversification

| Pair | Error correlation (95% bootstrap) | Failure Jaccard | P(right succeeds | left fails) |
|---|---:|---:|---:|
| groq/openai/gpt-oss-20b@A0 ↔ groq/qwen/qwen3.8-27b@A0 | 0.742 [0.577, 0.886] | 0.735 | 0.138 [0.031, 0.278] |
| groq/openai/gpt-oss-20b@A0 ↔ openrouter/deepseek/deepseek-v4.1-flash@A0 | 0.489 [0.336, 0.634] | 0.345 | 0.655 [0.467, 0.824] |
| groq/qwen/qwen3.8-27b@A0 ↔ openrouter/deepseek/deepseek-v4.1-flash@A0 | 0.394 [0.195, 0.570] | 0.290 | 0.700 [0.520, 0.857] |

## What remains unresolved

- S2 versus S1 quality remains unresolved at 95% confidence.
- S3 versus S1 quality remains unresolved at 95% confidence.
- S4 versus S0 quality remains unresolved at 95% confidence.
- Held-out n=12 is deliberately compact; tail-risk and rescue estimates remain wide.

## Frozen weak priors

Prior strength κ=4.0 (maximum 5.0). The challenge data is intentionally able to overturn these generic priors quickly.

## Execution boundary

Actual inference calls: 233 / 245. Provider requests: 233 / 246. Conservative reserved spend: $0.17888128 / $0.20; actual token-estimated spend: $0.00941611.

Baseline v0 is frozen. No sequential racing, full Claude/Gemini baseline, exhaustive A0–A6 run, extra ablation, UI work, commit, or push was performed.
