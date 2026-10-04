# Experiment protocol template

Copy this file before collecting confirmatory outcomes. Replace every bracketed
field. Commit the completed protocol and record its SHA-256 in each run.

## Identity

- Protocol name: `[stable-name]`
- Version: `[integer or semantic version]`
- Frozen date/time in UTC: `[ISO-8601]`
- Authors/reviewers: `[roles or names]`
- Code commit: `[full Git SHA]`
- Related prior protocol: `[path/version or none]`
- Change reason: `[required for version > 1]`

## Research question

`[One answerable question with a defined domain and outcome.]`

## Hypotheses

### Primary hypothesis

- ID: `[H1]`
- Statement: `[intervention/predictor improves or changes outcome versus comparator]`
- Null: `[effect region treated as no meaningful improvement]`
- Direction: `[higher/lower/two-sided]`
- Smallest effect of scientific interest: `[value and unit]`

### Secondary hypotheses

`[List separately. Mark exploratory hypotheses explicitly.]`

## Experimental design

- Experimental unit: `[case, seed, subject, run, landscape, etc.]`
- Intervention/candidate: `[definition]`
- Comparator: `[definition]`
- Pairing or blocking: `[what is shared and why]`
- Randomization: `[method and implementation]`
- Blinding: `[what is blinded; if none, why]`
- Repetitions/sample size: `[number and justification]`
- Stopping rule: `[fixed n or valid sequential rule]`

## Data partitions

| Split | Units/seeds | Permitted use |
|---|---|---|
| Development | `[range/list/hash]` | implementation and exploratory design |
| Tuning | `[range/list/hash]` | thresholds and hyperparameters |
| Calibration | `[range/list/hash]` | external target/reference only |
| Held-out | `[range/list/hash]` | one frozen confirmatory evaluation |

State who may unseal held-out results and the required approval.

## Inputs and provenance

| Input | Version/source | Expected hash | License/usage constraint |
|---|---|---|---|
| `[name]` | `[reference]` | `[SHA-256 or generated-at-run]` | `[constraint]` |

## Execution configuration

- Runtime/toolchain versions: `[Python/Rust/Julia/provider API]`
- Hardware constraints: `[CPU/GPU/memory]`
- Root seed: `[integer or allocation rule]`
- Named RNG streams: `[labels and purpose]`
- Concurrency: `[value]`
- Evaluation budget: `[value and unit]`
- Wall-time ceiling: `[value]`
- Provider-call ceiling: `[value]`
- Spend ceiling: `[currency and conservative calculation]`
- Retry policy: `[count, backoff, whether retry remains same experimental unit]`

## Outcomes

### Primary outcome

- Name: `[stable machine name]`
- Definition: `[formula]`
- Unit: `[unit]`
- Direction: `[maximize/minimize]`
- Valid range: `[range]`
- Censoring: `[none/right/left/interval and rule]`

### Secondary and diagnostic outcomes

`[List with units and roles. Diagnostics do not become primary post hoc.]`

## Artifact schemas

| Artifact | Kind | Stage | Fields/dtype/shape | Unit/role | Parents |
|---|---|---|---|---|---|
| `[name.v1]` | `[table/array/json]` | `[raw/derived/analysis]` | `[contract]` | `[semantics]` | `[names or none]` |

## Failure, missingness, and exclusion rules

- Provider/transport failure: `[handling]`
- Timeout: `[handling]`
- Malformed output: `[handling]`
- Numerical failure: `[handling]`
- Budget exhaustion: `[handling]`
- Missing pair: `[handling]`
- Exclusion criteria: `[objective rules known before outcomes]`
- Censoring rule: `[handling]`

Failures must remain in the raw record even when excluded from a specific
conditional analysis.

## Statistical analysis

- Estimand: `[exact target quantity]`
- Point estimator: `[formula/method]`
- Confidence/credible interval: `[method and level]`
- Resampling unit: `[case/run/seed/subject]`
- Number of bootstrap/permutation draws: `[value]`
- Stratification: `[factors]`
- Paired test: `[method]`
- Multiplicity family and correction: `[method]`
- Tail-risk estimator: `[method and effective tail-count rule]`
- Sensitivity analyses: `[predeclared alternatives]`

## Decision rule

- Supported: `[effect and uncertainty condition]`
- Refuted/equivalent: `[SESOI-based condition]`
- Inconclusive: `[otherwise]`
- Operational failure: `[separate condition]`
- Early stopping/elimination: `[valid sequential boundary, if any]`

## Reproducibility plan

- Command to execute: `[repository-relative command]`
- Command to validate: `[command]`
- Independent reproduction: `[who/environment]`
- Required byte equality or numeric tolerance: `[rule]`
- Deliberate corruption test: `[artifact and expected failure]`
- Archive/export plan: `[location and validation command]`

## Planned reporting

- Primary table/figure: `[description]`
- Raw artifact location: `[relative path]`
- Machine-readable summary: `[relative path]`
- Human-readable report: `[relative path]`
- Claims allowed if positive: `[bounded statement]`
- Claims allowed if negative/inconclusive: `[bounded statement]`
- Claims explicitly out of scope: `[list]`

## Approval

- Protocol reviewed: `[yes/no, reviewer, date]`
- Paid execution approved: `[yes/no/not applicable]`
- Held-out execution approved: `[yes/no/not yet]`
- Protocol hash: `[filled after freeze]`
