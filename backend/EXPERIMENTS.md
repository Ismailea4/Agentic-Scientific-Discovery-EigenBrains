# EigenBrains experimental laboratory

The benchmark system extends the existing project spine rather than creating
a parallel application:

```text
AIProvider / provider adapters
  -> MetricsRecorder and normalized observations
  -> BenchmarkRun
  -> model + architecture analysis
  -> hard constraints, Pareto, and dynamic router
  -> ArchitectureRegistry
  -> existing /api/system/architectures endpoint
```

It does not run providers by itself and contains no fabricated performance
results. A challenge-specific executor supplies real observations to
`BenchmarkRunner`.

## Implemented laboratory

- Environment-only OpenAI adapter and provider-neutral normalized results.
- Secret-free credential status schema and minimal validation orchestrator.
- Explicit pilot projections and limits for spend, total calls, calls per
  model, and concurrency. No benchmark provider call is authorized without a
  configured spend ceiling and known projected cost.
- Bounded exponential retries with jitter for retryable failures.
- Immutable cache keys over case, model, model configuration, and prompt
  configuration.
- A deterministic 72-case generic-prior corpus across twelve objective task
  categories, with 48 `dev`, 12 `tuning`, and 12 `held_out` cases. The
  original 12-case file remains a fast smoke fixture; the runner defaults to
  `dev` only.
- Seven bounded architecture templates:
  - A0 strongest single solver
  - A1 solver -> verifier
  - A2 two independent solvers -> synthesizer
  - A3 specialist -> solver -> verifier
  - A4 solver -> critic -> revision
  - A5 two solvers -> disagreement detector -> conditional critic
  - A6 router -> task-specific solver -> verifier
- Model metrics for correctness, rubric score, latency/p95, tokens, checked
  cost, failures, malformed output, abstention, constraint violations,
  disagreement, and variance.
- Architecture aggregation, component ablations, empirical lower-tail risk,
  covariance/Pearson-or-Phi correlation, failure overlap, Jaccard similarity,
  and diversity-aware pair selection.
- Calibration bins, ECE, Brier score, over/underconfidence, coverage, answered
  error, abstention, and verification rates.
- Deterministic percentile bootstrap intervals, paired bootstrap differences,
  Wilson intervals, probability-of-dominance estimates, and exact McNemar
  tests. Paired claims require identical case and repeat coverage.
- Architecture distributions by task and risk level; empirical and
  confidence-bound Pareto frontiers; downside semivariance, VaR/CVaR at 90%
  and 95%, worst-decile loss, and instability labels.
- Error covariance, conditional failure, pair-selection diagnostics, and a
  portfolio-style workload objective. Portfolio weights are routing
  probabilities, and cost/latency terms are dimensionless budget ratios.
- Marginal-agent economics with paired uncertainty and significance gates,
  static-versus-conditional verification comparisons, weak bounded priors,
  robust confidence-bound routing, sequential racing, stress tests, and
  human/machine-readable architecture cards.
- Hard capability/privacy constraints, Pareto classification, explicit
  weighted utility, value-of-information gating, Bayesian updates, and
  evidence-filtered routing with `ANSWER`, `VERIFY`,
  `INSUFFICIENT_EVIDENCE`, `OUT_OF_DISTRIBUTION`, `INFEASIBLE`, and `NO_CALL`.
- Required baseline mapping for B0 single, B1 static multi-agent, B2 adaptive,
  B3 cheapest viable, and B4 maximum-quality.

## Repository layout

`../benchmark/` contains versioned cases, non-secret configuration, and the
secret-free key inventory. Generated artifacts, reports, and cache entries are
ignored. Python implementation remains in `app/benchmark/` so it shares the
project's provider, instrumentation, optimization, fallback, registry, and API
types.

Evidence states remain distinct:

- `SAMPLE`: interface fixture only; never decision evidence.
- `BENCHMARK`: recorded experiment on a named dataset and split.
- `LIVE`: actual challenge-runtime telemetry.

`publish_measured_architectures` publishes only complete measured candidates
to the existing `ArchitectureRegistry`, adding `evidence_state=BENCHMARK` in
metadata. No frontend redesign is required.

## Reproducible workflow

1. Lock dataset version, split, exact models, prompts/configuration, prices,
   repeats, and seeds.
2. Develop on `benchmark/cases/generic_prior.json` using the `dev` split.
3. Run a tiny pilot and call `project_full_benchmark`.
4. Set explicit `MAX_BENCHMARK_SPEND_USD`, `MAX_TOTAL_CALLS`,
   `MAX_CALLS_PER_MODEL`, and `MAX_CONCURRENCY` values.
5. Use tuning data for architecture/threshold selection. Never use held-out
   results for those choices.
6. Freeze the system, then run the required B0/B1/B2 held-out comparison.
7. Export ordinary benchmark artifacts from already-recorded runs offline:

```powershell
cd F:\hack7\backend
python -m app.benchmark.cli --runs ..\benchmark\artifacts\recorded-runs.jsonl --output ..\benchmark\artifacts --report-dir ..\benchmark\reports --dataset generic-prior-1 --split held_out --methodology frozen-paired-comparison --lower-percentile 0.1 --severe-failure-threshold 0.2 --failure-threshold 0.5
```

The export produces:

```text
benchmark/artifacts/runs.jsonl
benchmark/artifacts/model_summary.csv
benchmark/artifacts/architecture_summary.csv
benchmark/artifacts/ablation_results.csv
benchmark/artifacts/error_correlation.csv
benchmark/artifacts/failure_overlap.csv
benchmark/artifacts/pareto_frontier.json
benchmark/artifacts/calibration.json
benchmark/artifacts/tail_risk.csv
benchmark/artifacts/failure_cases.json
benchmark/artifacts/benchmark_summary.json
benchmark/reports/BENCHMARK_REPORT.md
```

Unknown pricing stays `null` and excludes the affected architecture from
cost-aware optimization. It is never treated as free.

## Architecture Baseline v0

Baseline v0 is a stricter analytical layer over the same recorded
`BenchmarkRun` contract. It does not contact providers. It refuses empty run
sets and mixed splits, and it records the benchmark version/date, split,
confidence level, bootstrap count, seed, failure thresholds, and bounded
prior strengths in the report.

After a real, authorized run has been recorded, export one split at a time:

```powershell
cd F:\hack7\backend
python -m app.benchmark.baseline_cli --runs ..\benchmark\artifacts\recorded-runs.jsonl --benchmark-root ..\benchmark --benchmark-version generic-prior-v0 --benchmark-date 2026-10-03 --split dev --confidence-level 0.95 --bootstrap-resamples 2000 --seed 0 --lower-percentile 0.1 --severe-failure-threshold 0.2 --failure-threshold 0.5 --prior-strength 2 --maximum-prior-strength 5 --correlation-penalty 1
```

The command creates the following scrubbed artifacts under
`benchmark/artifacts/baseline_v0/`, plus the report under
`benchmark/reports/`:

```text
raw_runs.jsonl
model_statistics.csv
model_reliability.csv
architecture_statistics.csv
architecture_task_statistics.csv
confidence_bounds.csv
covariance.csv
pairwise_uncertainty.json
shrinkage_covariance.json
failure_overlap.csv
ablations.csv
marginal_agent_value.csv
escalation_economics.csv
empirical_frontier.json
robust_frontier.json
tail_risk.csv
stress_tests.csv
routing_scenarios.csv
priors.json
binary_priors.json
architecture_cards.json
PRECHALLENGE_BASELINE_V0.md
```

The baseline report remains explicitly conditional on its recorded split.
Generic-prior evidence is an architecture prior, not a challenge result. No
frontier, diversification benefit, marginal-agent claim, or routing
recommendation exists until the corresponding observations have been run.

Prepare the frozen protocol and reduced budget without contacting providers:

```powershell
cd F:\hack7\backend
python -m app.benchmark.baseline_plan_cli --benchmark-root ..\benchmark --protocol ..\benchmark\configs\prechallenge_baseline_v0.json --pricing ..\benchmark\configs\pricing_v0.json
```

The approval report is written to
`benchmark/reports/PRECHALLENGE_BASELINE_BUDGET.md`. The compact S0-S4 study
centers Qwen-first selective GPT-OSS escalation rather than exhaustively
running A0-A6. The evidence-first demo contract lives in
`benchmark/reports/EVIDENCE_FIRST_DEMO.md`.

## Credential boundary

The repository's governing rules prohibit reading API-key files. Therefore
this work did not open, transform, validate, overwrite, or delete
`api_keys.txt`, and it did not create an external `working_keys.env` file.
`benchmark/key_status.json` truthfully records `NOT_RUN` with zero tested
credentials.

The validation framework accepts only an already provider-labeled credential
from the process environment, authenticates through that provider's probe,
makes at most one tiny inference, and returns metadata only. It stores no raw,
partial, or hashed credential identifier. A 429 is classified as rate-limited
or quota-exhausted, never invalid.

## Empirical discovery and pilot gate

The 2026-10-03 discovery pass observed environment-backed credentials for
OpenAI, Anthropic, Gemini, OpenRouter, and Groq. Catalogue authentication
succeeded for all five. One tiny inference succeeded for Anthropic, Gemini,
OpenRouter, and Groq; OpenAI returned HTTP 429 and remains excluded from the
active pilot without being labelled invalid. Safe status metadata is recorded
in `../benchmark/key_status.json`; it contains no raw, partial, or hashed
credential identifier.

The compact discovery-only shortlist and checked prices are stored in
`../benchmark/configs/provider_shortlist_v0.json` and `pricing_v0.json`.
Candidate roles are hypotheses, not measured rankings.

Plan the pilot without contacting providers:

```powershell
cd F:\hack7\backend
python -m app.benchmark.pilot_cli --shortlist ..\benchmark\configs\provider_shortlist_v0.json --pricing ..\benchmark\configs\pricing_v0.json --output ..\benchmark\artifacts\pilot_v0\raw_runs.jsonl
```

The current plan selects two dev cases from each of twelve task types: 24
paired cases across five models, or 120 calls. With 1,024 input and 256 output
tokens reserved per call, the conservative published-price ceiling is
`$0.18763776`. Runtime remains unknown until the pilot is measured.

Execution requires both `--execute` and explicit limits:

```powershell
$env:MAX_BENCHMARK_SPEND_USD="0.20"
$env:MAX_TOTAL_CALLS="120"
$env:MAX_CALLS_PER_MODEL="24"
$env:MAX_CONCURRENCY="1"
python -m app.benchmark.pilot_cli --shortlist ..\benchmark\configs\provider_shortlist_v0.json --pricing ..\benchmark\configs\pricing_v0.json --output ..\benchmark\artifacts\pilot_v0\raw_runs.jsonl --execute
```

These values are example minimum limits matching the current plan, not a
standing authorization. The CLI refuses provider calls if the limits are
absent, pricing is unknown, or the projection exceeds a limit.

## Verification

```powershell
cd F:\hack7\backend
python -m pytest tests -q -p no:cacheprovider --basetemp .pytest_lab
```

Network tests, when later added with authorized provider access, must use the
separate `network` marker. The default suite remains fully offline.

## Challenge-day work

- Add challenge-specific cases and objective checkers.
- Lock checked provider pricing and exact accessible model identifiers.
- Run pilot -> projection -> approved benchmark, in that order.
- Fit routing thresholds on tuning evidence only.
- Freeze B0/B1/B2 and evaluate held-out cases.
- Publish measured candidates to the registry and expose them through the
  existing API.
- Report uncertainty, negative results, failures, and limitations; do not
  generalize generic priors to the challenge without new evidence.
