# Reproducibility handbook

Reproducibility is a property of the complete claim-producing process, not only
of a random seed. A result is reproducible when another researcher can identify
the exact question, code, inputs, environment, stochastic state, procedure,
artifacts, and analysis that produced it—and can detect a meaningful mismatch.

## Reproducibility levels

Use these terms precisely:

| Level | Definition |
|---|---|
| Repeatable | The same code, data, environment, and machine reproduce the result. |
| Reproducible | An independent environment using the recorded materials reproduces the result within declared tolerances. |
| Replicable | A new implementation or independently collected dataset supports the same scientific conclusion. |

The SDK primarily supports repeatability and reproducibility. Replication
requires a separately designed study and must not be inferred from deterministic
replay.

## Minimum reproducibility record

Every claim-bearing run must preserve:

- immutable run identifier;
- hypothesis and null hypothesis;
- protocol reference and content hash;
- code commit and dirty-tree status;
- parameters and declared outputs;
- random seed and stream-allocation rule;
- input paths expressed portably plus content hashes;
- operating system, runtime, dependency versions, and relevant hardware;
- compute and provider budgets;
- raw observations, including failures and abstentions;
- artifact schemas, units, roles, and lineage;
- primary and secondary metrics;
- analysis code/version and uncertainty method;
- exclusions, deviations, and stopping reason;
- final evidence status and rationale.

If any item is unavailable, record that absence explicitly. “Unknown” is more
scientifically useful than an inferred or silently substituted value.

## Freeze before execution

Before observing confirmatory outcomes, freeze the following:

1. research question and directional hypothesis;
2. primary outcome and unit;
3. smallest effect of scientific interest;
4. experimental unit and sample-size rule;
5. development, tuning, calibration, and held-out partitions;
6. seed allocation and pairing strategy;
7. inclusion, exclusion, failure, censoring, and missing-data rules;
8. statistical test, confidence interval, bootstrap unit, and multiplicity rule;
9. stopping condition and compute/provider ceilings;
10. decision rule mapping evidence to supported, refuted, or inconclusive.

Store the protocol in a versioned file. Hash it into the run record. A later
change requires a new protocol version and a changelog entry explaining what
triggered the change and which previous results it affects.

## Randomness

### Seed ownership

The experiment specification owns the root seed. All stochastic mechanisms
must derive from it or declare an independently recorded source. Never call a
global unseeded generator in claim-producing code.

Python SDK runs expose:

- `run.rng`: the main NumPy generator;
- `run.child_rng("label")`: a stable stream derived from the root seed and a
  semantic label.

Use named streams for logically separate mechanisms:

```python
initialization_rng = run.child_rng("initial-population")
variation_rng = run.child_rng("mutation-and-crossover")
bootstrap_rng = run.child_rng("paired-bootstrap")
```

Named streams prevent a harmless change in one component's call count from
silently changing another component's samples.

### Common random numbers

For paired controller or algorithm comparisons, the same seed should generate
the same initial population, shift schedule, noise realization, and other shared
conditions. Algorithm-specific randomness may use a separate derived stream.
Document exactly what is shared. Pairing does not exist merely because two runs
use integers with the same printed value.

### Seed ranges

Reserve non-overlapping ranges for:

- development and debugging;
- hyperparameter or threshold tuning;
- calibration;
- held-out confirmation;
- replication or robustness analysis.

Do not recycle a development seed into a confirmatory analysis. The current
discovery protocol records its allocation in `discolab/prereg.yaml`.

## Environment capture

Record at minimum:

```powershell
git rev-parse HEAD
git status --short
python --version
python -m pip freeze
node --version
npm --version
rustc --version
cargo --version
julia --version
```

Only capture tools used by the run. Dependency manifests should be stored as
artifacts or produced automatically by the SDK. Never capture the full process
environment: it may contain credentials and unrelated private data.

For timing-sensitive work, also record:

- CPU model and logical core count;
- GPU model and driver/runtime when applicable;
- memory capacity;
- thread-limit variables;
- warmup policy;
- background-load policy;
- wall-clock source and resolution.

Do not compare wall times from different machines as if they were paired.
Prefer machine-independent work units—function evaluations, simulated
generations, tokens, calls—alongside wall time.

## Artifact discipline

### Raw, derived, analysis

Keep three stages separate:

- `raw`: direct observation from an experiment or provider;
- `derived`: deterministic transformation of raw artifacts;
- `analysis`: statistical summaries, models, plots, and conclusions.

Every derived or analysis artifact must list its parent artifacts. Never
overwrite raw data with a cleaned version.

### Formats

The current SDK uses canonical JSON Lines for tables, NumPy `.npy` for dense
arrays, and canonical JSON for structured objects. Each file has a semantic
schema and SHA-256 content hash. Arrays are loaded with pickle disabled.

For every field or metric, declare:

- data type;
- unit;
- scientific role;
- allowed range when known;
- nullability;
- censoring semantics when relevant.

Units are part of the contract. A comparison between seconds and milliseconds
must fail or perform an explicit conversion; it must not rely on column names.

### Write-once behavior

Evidence files should be created exclusively. If a run is wrong:

1. preserve it;
2. record failure or rejection;
3. create a new run identifier;
4. link the new run to the superseded run;
5. explain the deviation.

## Reproducing an SDK run

Inspect first:

```powershell
eigenbrains-sdk --root .\study inspect RUN-XXXXXXXXXXXX
eigenbrains-sdk --root .\study validate RUN-XXXXXXXXXXXX
```

Check:

- status is complete and validated;
- protocol and runner hashes exist when files were available;
- inputs still match their recorded hashes;
- all declared outputs and the primary metric exist;
- artifact hashes and schemas validate;
- the runner is an allow-listed importable experiment definition.

Then reproduce:

```powershell
eigenbrains-sdk --root .\study reproduce RUN-XXXXXXXXXXXX
```

Compare the original and reproduced run:

```powershell
eigenbrains-sdk --root .\study compare RUN-ORIGINAL RUN-REPRODUCED
```

Deterministic artifacts should match byte-for-byte. Floating-point experiments
that intentionally permit platform variation must preregister a tolerance and
compare scientific conclusions as well as numeric deviations.

## Reproducing model benchmarks

Provider-backed model behavior is inherently time-sensitive. Exact text may not
reproduce even with temperature zero. Preserve enough context to reproduce the
protocol and quantify drift:

- provider and exact model identifier;
- endpoint class and relevant API version;
- prompt template hash;
- system prompt hash;
- temperature and decoding limits;
- ordered case manifest and split;
- evaluator version;
- request timestamp;
- normalized response, usage, latency, status, and error class;
- pricing-table version and distinction between known and unknown cost.

Reproduction means rerunning the same protocol and reporting agreement/drift,
not rewriting the original observation. Cached replay is useful for policy
analysis but is not a new provider-backed execution.

## Reproducing the published acceleration studies

The fast, offline claim check derives the reported values again from committed
machine-readable artifacts:

```powershell
.\scripts\verify.ps1 -ClaimsOnly
```

To rerun the five-replicate selective sample-escalation study under its frozen
protocol and compare the regenerated result with the recorded evidence:

```powershell
.\scripts\verify.ps1 -CoreOnly -ReproduceAcceleration -KeepArtifacts
```

The rerun uses deterministic numerical computation and no model-provider
calls. It must reproduce the protocol, per-replicate compute ratios, agreement
vectors, gate rate, and rescue/damage economics. The committed result is a
development-stage benchmark; successful reproduction does not convert it into
held-out confirmation or prove generalization to other scientific domains.

## Reproducing discovery runs

For a recorded discovery run:

1. identify its frozen preregistration file;
2. verify the preregistration hash recorded in `ledger.jsonl`;
3. fold the event ledger from an empty state and confirm the materialized state;
4. inspect experiment manifests, seed blocks, code fingerprint, and raw files;
5. rerun deterministic numerical experiments with the same code and seeds;
6. regenerate statistical summaries from raw outcomes;
7. compare verdicts and posterior updates;
8. audit agent interpretations separately from numerical facts.

Agent prose need not reproduce verbatim. The scientific transition—candidate
set, selected experiment, measured result, verdict, belief update, and next
decision—must remain traceable.

## Checkpoint and interruption policy

When checkpoint support is used, a valid checkpoint must bind:

- run and checkpoint identifiers;
- monotonic sequence number;
- specification hash;
- parameter hash;
- input hashes;
- consumed evaluation count and elapsed time;
- serialized RNG state;
- algorithm state with an explicit schema;
- checkpoint content hash.

Resume must fail closed when the run is terminal, the state is missing or
corrupted, the specification changed, an input changed, or evidence was emitted
after the checkpoint in a way the resume operation cannot reconcile. A resumed
run should be tested against an uninterrupted run.

## Reproducibility audit checklist

### Identity

- [ ] Commit hash recorded.
- [ ] Dirty-tree status recorded and diff preserved if dirty.
- [ ] Protocol name, version, and hash recorded.
- [ ] Unique run ID used everywhere.

### Inputs and stochasticity

- [ ] Input hashes recorded.
- [ ] Root seed recorded.
- [ ] Stream-allocation rule documented.
- [ ] Split/seed leakage checked.
- [ ] Common-random-number pairing verified where claimed.

### Execution

- [ ] Resource limits recorded.
- [ ] Failures and timeouts retained.
- [ ] No implicit retry changed the experimental unit.
- [ ] Runtime and dependency versions captured.

### Evidence

- [ ] Raw artifacts are write-once.
- [ ] Schemas and units validate.
- [ ] Derived artifacts name their parents.
- [ ] Primary metric is present.
- [ ] Content hashes validate.

### Analysis

- [ ] Analysis matches the frozen plan.
- [ ] Bootstrap resamples the correct independent unit.
- [ ] Pairing and censoring are preserved.
- [ ] Multiplicity correction is applied where promised.
- [ ] Exploratory analyses are labeled.
- [ ] Negative and inconclusive outcomes remain visible.

### Independent replay

- [ ] At least one run reproduced.
- [ ] Artifact equality or tolerance assessed.
- [ ] A deliberate corruption test fails validation.
- [ ] Reproduction differences are explained, not hidden.
