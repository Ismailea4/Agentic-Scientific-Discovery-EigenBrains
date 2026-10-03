# Architecture Baseline v0 - approval gate

No provider calls described here have been executed.

## Reduced budget

| Phase | Provider requests | Inference calls | Dollar ceiling |
|---|---:|---:|---:|
| provider_diagnosis | 6 | 5 | $0.00243840 |
| core_72_case_single_model_baseline | 216 | 216 | $0.16293888 |
| s0_to_s4_offline_replay | 0 | 0 | $0.00000000 |
| compact_provider_backed_verifier_confirmation | 24 | 24 | $0.02396160 |
| targeted_sequential_racing | 24 | 24 | $0.02396160 |

Recommended initial approval: **246 provider requests, 245 inference calls, $0.18933888**. This excludes sequential racing.

Maximum including the separately gated racing reserve: **270 provider requests, 269 inference calls, $0.21330048**.

The sequential-racing allocation is a ceiling, not an automatic spend. S0-S4 replay itself makes zero provider calls.

## Compact architecture claim

The first target is Qwen-first selective GPT-OSS escalation versus GPT-OSS-only, Qwen-only, always-both, and reverse escalation. Evidence must report quality, severe/tail risk, escalation probability, rescue/damage, cost, latency, and confidence intervals. It must not claim that all A0-A6 architectures were measured.

## Approval status

`NOT_APPROVED` - stop here until the user authorizes explicit phase ceilings.
