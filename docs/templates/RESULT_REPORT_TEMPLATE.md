# Empirical result report template

## Executive finding

State one bounded conclusion with the studied population, comparator, effect,
uncertainty, and evidence label. Do not lead with architecture complexity.

## Evidence identity

| Field | Value |
|---|---|
| Evidence label | `[REPLAY/BENCHMARK/PROVIDER_BACKED/LIVE]` |
| Protocol | `[path, version, SHA-256]` |
| Code | `[commit; dirty status]` |
| Run IDs | `[identifiers]` |
| Execution time | `[UTC interval]` |
| Environment | `[manifest/artifact link]` |

## Question and design

- Research question: `[text]`
- Primary hypothesis/null: `[text]`
- Experimental unit: `[unit]`
- Splits used: `[development/tuning/calibration/held-out]`
- Sample size: `[planned and realized]`
- Pairing/blocking/randomization: `[description]`
- Stopping rule and budgets: `[description]`

## Primary result

| Candidate/comparison | n | Estimate | Effect vs comparator | 95% interval | Decision |
|---|---:|---:|---:|---:|---|
| `[name]` | `[n]` | `[value unit]` | `[value unit]` | `[low, high]` | `[supported/refuted/inconclusive]` |

Interpret the magnitude in domain terms. A p-value or posterior alone is not a
result statement.

## Reliability and failures

| Failure class | Count | Denominator | Treatment in primary analysis |
|---|---:|---:|---|
| Provider unavailable | | | |
| Timeout | | | |
| Malformed output | | | |
| Abstention | | | |
| Numerical failure | | | |
| Budget exhaustion | | | |
| Censored observation | | | |

For provider work, separately report availability, correctness conditional on
success, and operational correctness.

## Cost and latency

Report units, distribution summaries, unknown costs, and the pricing-table
version. If comparing performance, document warmups, repetitions, hardware, and
whether observations are paired.

## Secondary and exploratory results

Label each analysis. State multiplicity correction for confirmatory secondary
tests. Post-hoc findings generate hypotheses; they do not retroactively modify
the primary claim.

## Robustness and sensitivity

Include, where relevant:

- alternative but defensible evaluator;
- seed/function/task-family stratification;
- outlier influence;
- covariance and failure overlap;
- confidence-bound/robust Pareto status;
- missingness assumptions;
- censoring horizon;
- prior-strength sensitivity.

Report if a ranking or conclusion changes.

## Reproduction

- Validation command: `[command and result]`
- Reproduction command: `[command and new run ID]`
- Artifact comparison: `[byte-identical/tolerance and result]`
- Bundle/archive validation: `[command and result]`
- Corruption negative control: `[change and expected validation failure]`

## Research-acceleration measurement

| Measure | Conventional baseline | Platform workflow | Difference/ratio | Agreement |
|---|---:|---:|---:|---:|
| Machine-independent work | | | | |
| Wall time | | | | |
| Manual validation steps | | | | n/a |
| Runs to conclusion | | | | |

Do not call a reduction acceleration unless the scientific conclusion remains
equally reliable under the preregistered agreement rule.

## Threats to validity

### Internal

`[Confounding, leakage, instrumentation, implementation errors.]`

### Construct

`[Whether metrics measure the intended concept.]`

### Statistical

`[Power, dependence, multiplicity, tail sample, model assumptions.]`

### External

`[Tasks, providers, functions, hardware, and time periods to which results may not generalize.]`

## Claim ledger

### Supported

- `[Exact bounded claim.]`

### Unresolved

- `[Comparison whose interval/sample does not decide it.]`

### Contradicted or refuted

- `[Claim the evidence weighs against.]`

### Not tested

- `[Important claim outside this protocol.]`

## Artifact index

| Artifact | Stage | Schema | Hash/manifest | Purpose |
|---|---|---|---|---|
| | | | | |
