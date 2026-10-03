# Benchmark data and run control

This directory is the repository-level experiment control plane. Python code
stays in `backend/app/benchmark` so it continues to use the existing provider,
instrumentation, optimizer, registry, and API contracts.

- `cases/` contains the 12-case smoke-test snapshot. The deterministic
  `backend/app/benchmark/corpus.py` generator expands this to the 72-case
  Architecture Baseline v0 corpus with 48 dev, 12 tuning, and
  12 held-out cases; it never generates model outputs.
- `configs/` contains explicit non-secret limits and statistical choices.
- `key_status.json` is a secret-free inventory. It remains empty until an
  authorized credential-validation workflow produces real observations.
- `artifacts/` and `reports/` are generated locally and ignored by Git.
- `cache/` stores immutable local run records and is ignored by Git.

The default runner executes only the `dev` split. Tuning and held-out runs
must be explicitly requested. Held-out results must never select weights or
thresholds.

`SCORING_V1` is the frozen Baseline-v0 evaluator. It retains the pilot's
exact-match result as `primary_v0`, while accepting only the critique aliases
and comma-spacing normalization documented before Baseline-v0 execution.

The compact S0-S4 study is intentionally narrower than an exhaustive A0-A6
search. S3 is Qwen-first selective GPT-OSS escalation. Its gate may use only
runtime-observable signals frozen on development/tuning data. Paired
single-model observations support a zero-call offline replay; separately
budgeted verifier calls are required before verifier value is described as
provider-backed architecture evidence.

The Baseline v0 exporter is deliberately offline. Once real observations are
recorded, run `python -m app.benchmark.baseline_cli` from `backend/` to build
the distribution, confidence-bound, covariance, downside-risk, robust
frontier, prior, stress-test, routing-scenario, and architecture-card
artifacts. The exporter will not turn an empty or mixed-split run file into a
report.

The complete experimental basis, call accounting, scoring contract, and
limitations are documented in
[`../docs/BENCHMARK_METHODOLOGY.md`](../docs/BENCHMARK_METHODOLOGY.md).
