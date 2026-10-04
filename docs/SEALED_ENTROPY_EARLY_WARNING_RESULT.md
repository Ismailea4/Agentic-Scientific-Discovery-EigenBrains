# A sealed held-out test overturned a +0.139 development-stage signal

**Population entropy's added early-warning value for evolutionary-search
stagnation did not generalize to untouched landscapes. Under the frozen
protocol the registered verdict is `no_meaningful_gain`, and the effect is
landscape-dependent.**

This report documents study `entropy-early-warning-v1`: a pre-registered,
sealed, cross-language experiment run through the EigenBrains evidence SDK.
It is an empirical result limited to the frozen experimental scope below, not a
mathematical statement about entropy or evolutionary algorithms in general.

| | |
|---|---|
| Protocol | [`research_prototypes/entropy_early_warning/protocol.yaml`](../research_prototypes/entropy_early_warning/protocol.yaml), SHA-256 `ba0e3e0ad771233ba5a7f5575170ed7e1a05a074fd4597c3c98e9d2882f43e2d` |
| Implementation | [`research_prototypes/entropy_early_warning/`](../research_prototypes/entropy_early_warning/) |
| Sealed evidence bundle | [`evidence/entropy-early-warning-v1.zip`](../research_prototypes/entropy_early_warning/evidence/entropy-early-warning-v1.zip), content identity `e3fcdbc34f93e31d34873816eed6a6fa45c177ec536fa9b2c6851b7e39ed8908` |
| Machine-readable summary | [`evidence/study-summary.json`](../research_prototypes/entropy_early_warning/evidence/study-summary.json) |
| Evidence label | `BENCHMARK` — sealed held-out confirmation under a frozen protocol |
| Confirmatory run | `RUN-960036E6972E`, status `accepted_as_evidence` |
| Registered verdict | **`no_meaningful_gain`** |

## 1. Research question and frozen hypothesis

> Do population-entropy dynamics provide statistically meaningful early
> warning of evolutionary-search stagnation beyond fitness-history features
> alone?

**EW1 (primary, confirmatory).** On held-out landscapes never used for
development, an L2 logistic model on fitness-history plus population-entropy
features predicts stagnation onset with higher AUROC than the same model on
fitness-history features alone.

- Estimand: ΔAUROC = AUROC(fitness+entropy) − AUROC(fitness) on held-out test points.
- Null: ΔAUROC ≤ 0. Smallest effect of interest (SESOI): **+0.02 AUROC**.
- Secondary contrasts (no confirmatory claims): EW2 entropy beyond genotypic
  dispersion (nested), EW3 dispersion vs fitness, EW4 entropy alone vs
  fitness, EW5 per-landscape heterogeneity.

## 2. Timeline: the protocol preceded the evidence

| Time (UTC, 2026-10-04) | Event |
|---|---|
| 05:10:08 | Protocol committed and pushed to `sdk` in `eac845c`. No study data existed. |
| 07:17–07:20 | Development-only rehearsal (`development-gate`): development simulation and exploratory analysis. **No held-out landscape was simulated or analysed.** Its development artifacts are byte-identical to the sealed run's (same seeds, deterministic code). |
| 07:21:20 | Sealed run started in a fresh evidence store (`run_study.py --confirm`); the driver refuses to run unless the protocol hash equals `ba0e3e0a…`. |
| 07:27:16 | Sealed run finished: 356 s wall time end to end. |

The analysis code (`ewstudy.py`: features, models, bootstrap, decision rule)
was written before any study data existed. The protocol file is unchanged
since `eac845c` (its SHA-256 is recorded in the provenance of every run).

## 3. Development / held-out separation

| | Development | Held-out (sealed) |
|---|---|---|
| Landscapes | Rastrigin, Ackley | Griewank, Levy, Styblinski–Tang |
| Seeds | 700000–700049 | 800000–800049 |
| Runs | 300 (2 × 50 × 3 policies) | 450 (3 × 50 × 3 policies) |
| Use | model fitting; exploratory leave-one-landscape-out | testing only, once |

Leakage controls, asserted in code: landscapes disjoint; seeds disjoint;
models and feature standardisation fitted on development runs only; held-out
traces enter only the confirmatory analysis run.

## 4. Experimental design and controlled randomness

- Algorithm: the laboratory's real-coded generational GA (`discolab.ga.run_ga`),
  unmodified. Population 50, dimension 10, SBX (η 15, p 0.9), binary tournament,
  elitism 1, per-gene Gaussian mutation σ = 0.05 × box width, 200 generations,
  static landscape translated by an offset drawn from the run seed.
- Data policies: fixed mutation rates 0.5/d, 1/d and 2/d.
- Common random numbers: a seed fixes the initial population and translation
  for every policy on that landscape.
- Label: at-risk generations have an improvement event (> 0.1% drop in best
  error); y = 1 when no improvement event occurs in the next K = 10 generations.
- Features: `discolab.features` (observable history only). Model: L2 logistic
  regression (λ = 0.01) on training-standardised features.
- Classical rules (non-learned): progress rate (minus improvement events in the
  last 10 generations) and diversity (minus genotypic dispersion).
- Randomness: every bootstrap index comes from the SDK child stream
  `bootstrap` of the analysis run's seed; GA randomness comes from the fixed
  study seeds. Every stage is an SDK evidence run with a declared evaluation
  or wall-time budget.

## 5. Primary estimand, SESOI, bootstrap unit, and decision rule

- Interval: paired cluster bootstrap, 2000 resamples of **(landscape, seed)
  clusters**, stratified by landscape, with the same resamples for every
  feature set; percentile 95% interval. Runs of the three policies that share
  a seed are resampled together because they share an initial population.
- Frozen decision rule:
  - `no_meaningful_gain` if the 95% upper bound < SESOI (0.02);
  - `supported` if the 95% lower bound > 0 and the estimate ≥ SESOI;
  - `inconclusive` otherwise.

## 6. Development result (exploratory only)

Leave-one-landscape-out on 300 development runs, 21,617 at-risk points
(prevalence 0.032). This stage was not used to tune the confirmatory design.

| Score | AUROC |
|---|---|
| fitness | 0.6986 |
| fitness + entropy | **0.8379** |
| fitness + dispersion | 0.7374 |
| fitness + dispersion + entropy | 0.8397 |
| entropy only | 0.5611 |
| progress-rate rule | 0.8229 |
| diversity rule | 0.3092 |

| Contrast | ΔAUROC [95% cluster-bootstrap CI] |
|---|---|
| EW1 fitness+entropy − fitness | **+0.1393 [+0.1305, +0.1490]** |
| EW2 entropy beyond dispersion | +0.1023 [+0.0952, +0.1096] |
| EW3 dispersion − fitness | +0.0388 [+0.0363, +0.0415] |
| EW4 entropy only − fitness | −0.1375 [−0.1575, −0.1180] |

On development landscapes this looked like a large, precise discovery,
consistent with the laboratory's earlier development-stage runs.

## 7. Confirmatory result and registered verdict

450 held-out runs, 150 independent (landscape, seed) clusters, 29,011 at-risk
points (prevalence 0.042).

| Score | AUROC [95% CI] |
|---|---|
| fitness | 0.8620 [0.8538, 0.8696] |
| fitness + entropy | 0.8561 [0.8479, 0.8643] |
| fitness + dispersion | 0.8650 [0.8570, 0.8726] |
| fitness + dispersion + entropy | 0.8560 [0.8478, 0.8642] |
| entropy only | 0.5522 [0.5369, 0.5684] |
| progress-rate rule | **0.8828 [0.8751, 0.8902]** |
| diversity rule | 0.5707 [0.5551, 0.5854] |

**EW1: ΔAUROC = −0.00588, 95% cluster-bootstrap CI [−0.01108, −0.00031].**
The upper bound is below the +0.02 SESOI, so the registered verdict is
**`no_meaningful_gain`**.

Read the sign carefully. The bootstrap interval only just excludes zero
(two-sided bootstrap p = 0.035). Julia's analytic clustered interval for the
same contrast (Obuchowski 1997) is [−0.0145, +0.0027], p = 0.18, which
includes zero. Both methods agree that any gain is far below the SESOI. They do
not agree that entropy makes predictions worse. The defensible statement is
that the +0.139 development gain **vanished** on held-out landscapes (to about
zero, with a landscape-dependent sign). "The effect reversed" overstates it.

Secondary held-out contrasts (bootstrap 95% CI, then the analytic Obuchowski
interval in brackets after the bootstrap one):

| Contrast | Held-out ΔAUROC | Development (exploratory) |
|---|---|---|
| EW2 entropy beyond dispersion | −0.0090 [−0.0134, −0.0043]; analytic [−0.0164, −0.0017] | +0.1023 |
| EW3 dispersion − fitness | +0.0030 [+0.0019, +0.0042]; analytic [+0.0014, +0.0046] | +0.0388 |
| EW4 entropy only − fitness | −0.3098 [−0.3287, −0.2894] | −0.1375 |

Brier score difference (fitness − fitness+entropy): +0.00048, a negligible
calibration gain. Two descriptive observations that were not pre-registered as
contrasts: on held-out landscapes the simplest classical signal, the
non-learned progress-rate rule (0.883), outranked every learned model; and the
diversity rule's AUROC moved from 0.31 (development) to 0.57 (held-out), so
even the direction of the dispersion signal depends on the landscape.

## 8. Landscape heterogeneity (EW5, descriptive)

| Held-out landscape | AUROC fitness | AUROC fitness+entropy | ΔAUROC | Test points |
|---|---|---|---|---|
| Griewank | 0.8590 | 0.9170 | **+0.0580** | 11,707 |
| Levy | 0.8678 | 0.8220 | **−0.0458** | 9,104 |
| Styblinski–Tang | 0.9171 | 0.9014 | −0.0157 | 8,200 |

Entropy helped substantially on one held-out landscape and hurt on two. The
pooled near-zero effect is an average of opposite-signed landscape effects, not
a uniformly small one. That is the discovered generalization boundary.

## 9. Cross-language verification and integrity controls

| Check | Result |
|---|---|
| Rust vs Python entropy, 600 population snapshots | max abs difference **0.0** (600/600 bitwise identical); tolerance 1e-12 |
| Julia vs Python AUROC, 7 scores | max abs difference **4.44e-16** |
| Byte-for-byte reproduction of the confirmatory analysis (`RUN-D3927C818ABD`) | **identical artifacts** |
| All 9 study runs | validate (hash-chained events, schemas, artifact hashes) |
| Bundle export and independent verification | identity `e3fcdbc3…8908`, verified |
| Corruption control: one byte flipped in a bundle copy | verification **failed closed** (hash mismatch reported) |
| Corruption control: one byte flipped in a run copy | validation failed; the copy was recorded as **`rejected_as_evidence`** |

**`accepted_as_evidence` means the confirmatory run passed the integrity and
protocol checks. It does not mean the scientific hypothesis was accepted.** The
accepted evidence is evidence *against* EW1.

Kernel timing, stated narrowly: on the 600 snapshots, in-memory entropy
computation only, 3 warm-ups and 30 measured repetitions, the median batch
time was 40.4 ms for the NumPy reference (IQR 36.7–43.7 ms) and 1.84 ms for the
Rust release build (IQR 1.48–2.48 ms), about **21.9× throughput for this kernel
on this machine**. It is not an end-to-end research speed-up.

## 10. Interpretation and limitations

- Under the registered conditions (this GA, dimension 10, these landscapes,
  fixed-rate policies, horizon K = 10), population entropy is **not justified as
  a universal early-warning signal**: its added value depends on the landscape.
  The large development effect was specific to the development landscapes.
- Three held-out landscapes cannot represent all optimization problems. This is
  a strong empirical negation of the general claim within this scope, not
  evidence that entropy never helps.
- The progress-rate and diversity observations are descriptive and were not
  pre-registered contrasts.
- One GA family, one dimension, static landscapes, a single entropy estimator
  (10 fixed bins). Other estimators or dynamic landscapes may behave differently.
- Results are from one machine (Windows 11, 12 logical CPUs, Python 3.14.4,
  NumPy 2.4.5, SciPy 1.17.1, Rust 1.99.0 release, Julia 1.13.1). Byte-identical
  reproduction was verified there; other platforms may differ in floating
  point at the last bits.

**Disclosed deviations and process notes**

1. The confirmatory run was accepted *before* the bundle export and corruption
   controls ran; the protocol orders those checks first. Both passed
   afterwards, so the outcome is unchanged; the order differed.
2. The evidence-run seeds (2026100401–2026100408) were fixed in the driver
   code, not in the protocol. GA seeds and every scientific setting come from
   the protocol.
3. A development-only rehearsal preceded the sealed run (section 2). It
   touched no held-out data, and its development artifacts are byte-identical
   to the sealed run's.
4. The sealed `spec.json` files record input paths as the absolute local paths
   the driver passed (they show the original folder layout, no credentials).
   They cannot be edited without breaking the bundle's hashes. The SDK now
   records such paths relative to the working directory (`c98fba1`).
5. The study ran from a working copy with CRLF line endings, so the recorded
   runner SHA-256 is `ad217b87…`; the committed LF file hashes to `ecaab1cd…`.
   The two are identical apart from line endings. At run time the study code
   was uncommitted (provenance: commit `65ce58c`, dirty); it was committed
   afterwards in `1227763`.

## 11. Reproduction commands

From the repository root, with Python ≥ 3.12 and NumPy, SciPy, PyYAML; Rust
and Julia as in [`sdk/README.md`](../sdk/README.md).

Verify the sealed evidence (no recomputation):

```bash
cd discolab
python -m discolab.sdk_cli verify-bundle ../research_prototypes/entropy_early_warning/evidence/entropy-early-warning-v1.zip
```

Re-run the whole study in a fresh store (development stage by default; held-out
only with `--confirm`):

```bash
python research_prototypes/entropy_early_warning/run_study.py --root research_prototypes/entropy_early_warning/output/rerun --confirm
```

A rerun produces new run ids and timestamps, so its bundle identity differs.
The scientific artifacts are what should match. On the recording machine
these were: development traces `f2a81ff8163f7ed9…`, held-out traces
`6a6966107a3d06a1…`, predictions `d0c89ca174bd217b…`, result
`dc4d9250a9a5df58…` (SHA-256 prefixes; full hashes in each run's
`artifacts.json`). Exact SDK `reproduce` of the bundled runs additionally needs
the runner file byte-identical to the recorded one (CRLF form, deviation 5) and
the original input paths (deviation 4), so a fresh rerun is the portable route.

## 12. Bundle identity and provenance

- Bundle: `research_prototypes/entropy_early_warning/evidence/entropy-early-warning-v1.zip`
  - content identity (hash of the canonical file list): `e3fcdbc34f93e31d34873816eed6a6fa45c177ec536fa9b2c6851b7e39ed8908`
  - archive SHA-256: `9a1bf89ca7c1b57ac05b723b47b7be31ffae8fa81a7d36f94b14064d7a92ee48`
- Runs in the bundle:

| Run | Role |
|---|---|
| `RUN-C2162ADD10DB` | development simulation |
| `RUN-5253D734A2BD` | development analysis (exploratory) |
| `RUN-2A2C97E306F9` | held-out simulation |
| `RUN-960036E6972E` | confirmatory analysis, `accepted_as_evidence` |
| `RUN-D3927C818ABD` | byte-identical reproduction of the confirmatory analysis |
| `RUN-EC04160D51A8` | Python entropy benchmark |
| `RUN-CA504C9736ED` | Rust entropy audit |
| `RUN-B980AAB62DC3` | Julia statistics audit |
| `RUN-DDE3027D4C66` | cross-language parity check |

Every run records the protocol SHA-256, its spec, inputs (with SHA-256),
runner source hash, environment, and a hash-chained event log; lineage
between runs follows input hashes (`eigenbrains-sdk lineage`).

## 13. What EigenBrains decided should not be claimed

- That entropy never helps predict stagnation (it helped on Griewank).
- That all evolutionary algorithms, dimensions, or landscapes behave this way.
- That three held-out landscapes represent every optimization problem.
- That `accepted_as_evidence` means EW1 was supported (it means the negative
  result is valid evidence).
- That entropy makes held-out predictions significantly worse (the two interval
  methods disagree on the sign).
- That the 21.9× kernel timing is an end-to-end platform speed-up.
- That this study produced the separate 1.54× compute-efficiency result (that
  is the earlier selective-escalation study, `discolab/results/escalation`).

## 14. The next scientific question (not run)

Which measurable landscape properties predict *when* population entropy adds
early-warning information? On Griewank it added +0.058 AUROC; on Levy it cost
−0.046. A follow-up would pre-register landscape descriptors (for example
ruggedness or basin structure) as moderators, with new held-out landscapes,
and ask separately why a non-learned progress-rate rule outperformed every
learned model here. No such experiment has been run.

## Why this matters for the platform

The development stage showed what looked like a breakthrough: +0.139 AUROC from
adding entropy. A system optimized for favourable results could have stopped
there. Instead the study executed a sealed test on 450 untouched runs, where
the gain vanished and split by landscape. The platform kept the universal
claim from being made, localized the heterogeneity, and preserved the negative
result as verified, reproducible evidence.

This is separate from, and complementary to, the earlier measured acceleration
(selective escalation: 1.54× less compute, 95% CI [1.28, 1.90]). One result is
about reaching research decisions with less compute; this one is about making
those decisions harder to fool.
