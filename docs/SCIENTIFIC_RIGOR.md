# Scientific rigor standard

This standard applies to model benchmarks, architecture experiments, autonomous
discovery runs, SDK research prototypes, and performance studies. It defines
the minimum evidence needed before a result can influence product architecture
or be presented as scientific support.

## 1. Begin with a falsifiable claim

A strong hypothesis specifies:

- the experimental unit;
- the intervention or added information;
- the comparator;
- the directional outcome;
- the population or task domain;
- the smallest scientifically meaningful effect.

Example:

> On held-out dynamic landscapes, adding entropy dynamics to fitness-history
> features increases run-clustered AUROC by more than 0.01 compared with the
> frozen fitness-only predictor.

Avoid claims such as “entropy helps,” “agents collaborate better,” or “the SDK
accelerates science” without a measurable comparator.

## 2. Separate phases of evidence

| Phase | Permitted use |
|---|---|
| Development | Debug implementations, choose candidate features, identify failure modes |
| Tuning | Select thresholds, hyperparameters, routing gates, and model roles |
| Calibration | Set externally needed targets or reference quantities using a declared method |
| Confirmation | Evaluate the frozen design once on sealed held-out units |
| Replication | Test the conclusion using new data, seeds, environments, or implementations |

Held-out outcomes cannot choose a model, threshold, prompt, verifier rule,
metric, exclusion, or stopping condition. If held-out data influence a choice,
the analysis becomes exploratory and a new confirmation set is required.

## 3. Define the experimental unit correctly

Inference assumes some unit is independently sampled. Common errors include:

- treating generations within one run as independent;
- treating multiple shifts within the same seed as independent;
- treating multiple metrics from one case as independent cases;
- treating repeated calls after a provider failure as new independent samples.

Resample or cluster at the highest dependence level. In the discovery lab,
bootstrap resampling is run-clustered because observations within a seeded run
share history. In model benchmarks, paired comparison is by case because every
model receives the same case.

## 4. Preserve pairing

Paired designs remove nuisance variation and enable direct failure analysis.
For model comparisons, require identical case coverage or report why pairing is
broken. For algorithm comparisons, use common random numbers when scientifically
valid. Never compare two unpaired averages and describe the difference as a
paired effect.

Report:

- case-by-case or seed-by-seed outcomes;
- disagreement rate;
- rescue and damage counts;
- conditional failure probabilities;
- covariance/correlation with uncertainty;
- missing pairs and their cause.

## 5. Use uncertainty that matches the data

### Binary outcomes

Use Wilson intervals for a single binomial rate. For paired binary changes, use
McNemar's test or a paired bootstrap as preregistered. Small samples require
wide intervals; do not suppress them because they weaken a headline.

### Continuous outcomes

Use paired differences when observations are paired. Report an effect estimate
and interval, not only a p-value. Bootstrap the independent experimental unit
and stratify by preregistered factors when appropriate.

### Tail risk

CVaR or severe-failure probability is unstable when the tail contains few
observations. Always report the effective tail count and avoid precise tail
claims from tiny held-out sets.

### Censoring

Recovery times that do not complete before a horizon are right-censored. Do not
drop them or replace them with successful times. Use the preregistered restricted
mean survival time or another censoring-aware estimator.

## 6. Control multiplicity

Multiple controllers, features, task families, or architecture policies create
multiple opportunities for a false positive. Predeclare primary contrasts and
apply the frozen correction, such as Holm, to the family of confirmatory tests.
Post-hoc subgroup findings are exploratory even if their uncorrected interval
excludes zero.

## 7. Define success before seeing outcomes

Every study must state:

- primary metric and direction;
- smallest effect of interest;
- confidence level;
- support, refutation, and inconclusive rules;
- severe-failure definition;
- acceptable availability and latency bounds;
- minimum sample before early stopping;
- maximum compute, calls, cost, and time.

“Statistically non-significant” does not mean equivalent. Refutation or
equivalence requires a rule tied to a scientifically meaningful effect region.

## 8. Treat failures as data

Record timeouts, provider rejections, malformed output, abstention, schema
failure, numerical instability, budget exhaustion, and operator cancellation.

Maintain three distinct quantities for provider experiments:

1. model quality conditional on a successful response;
2. provider availability;
3. end-to-end operational quality.

Do not score an unavailable provider as a reasoning failure, but do count it in
operational performance. Unknown billing for a failed request remains unknown.

## 9. Avoid metric and evaluator overfitting

An evaluator is part of the intervention. Freeze it before confirmation and
version any repair. If a sensitivity analysis changes rankings, report the
instability rather than selecting the scoring rule that favors a desired model.

For LLM evaluation:

- prefer deterministic objective checks where possible;
- define accepted aliases before execution;
- retain raw outputs;
- measure malformed and abstention rates separately;
- do not infer abstention from prose unless the rule was frozen;
- blind human raters to model identity when feasible;
- report inter-rater agreement for subjective labels.

## 10. Distinguish replay from execution

Offline replay can estimate a routing or selective-verification policy using
paired cached observations. It cannot establish provider-backed orchestration
latency, correlated runtime failure, or the behavior of a verifier conditioned
on the actual first response unless those interactions were executed.

Reports must say either:

- “offline replay estimate,” or
- “provider-backed architecture result.”

Never use the shorter word “result” when the distinction could be lost.

## 11. Measure complementarity, not only rank

A portfolio of models is valuable when errors are not perfectly correlated.
Mean quality alone cannot choose an architecture. At minimum estimate:

\[
E[L_i],\quad Var(L_i),\quad Cov(L_i,L_j),\quad Corr(L_i,L_j),
\quad P(j\text{ fails}\mid i\text{ fails}).
\]

An additional solver or verifier earns its place through marginal value:
rescues, avoided severe failures, calibration, or uncertainty reduction net of
cost and latency. A redundant high-scoring model may add less value than a
weaker but complementary model.

## 12. Quantify constrained utility transparently

The platform may optimize an architecture or experiment using:

\[
U = E[Q] - \lambda R - \eta C/B - \rho T/T_{max}.
\]

Utility weights express preferences; they do not create evidence. Always show
the underlying quality, risk, cost, latency, availability, and uncertainty
before the weighted score. Hard capability, privacy, authorization, and budget
constraints are filters, not utility penalties.

Use confidence-bound or stress-tested objectives when estimates are uncertain.
Report which candidates are on the empirical frontier and which survive the
robust frontier.

## 13. Use Bayesian updates conservatively

Weak priors may carry generic evidence into a new challenge, but challenge data
must be able to overturn them quickly. Record prior family, parameters,
effective sample strength, likelihood model, and posterior update. Do not mix
prior observations into the challenge sample and then count them twice.

Posterior probabilities do not replace direct verdict consistency. A coupled
prior may move belief in an untested hypothesis but must not independently mark
that hypothesis supported or refuted.

## 14. Protect literature integrity

Literature evidence must include a stable identifier and a title match. The
record should distinguish:

- what the source directly supports;
- the agent's inference;
- relevance to the current hypothesis;
- contradictory or limiting evidence.

Do not attach the first retrieved URL to a claim, invent bibliographic fields,
or treat a search snippet as full-paper verification.

## 15. Define the role of agents

Agents may:

- propose hypotheses and experiments;
- retrieve evidence;
- choose among feasible scored options;
- explain a selection or override;
- identify threats to validity;
- decide what question to investigate next.

Agents may not:

- write measured numerical results;
- bypass preregistration or held-out approval;
- silently change an evaluator;
- overwrite a ledger or raw artifact;
- convert missing data into favorable values;
- claim causality or generality beyond the protocol.

Demonstrate genuine agency by showing that different validated results produce
different next decisions. Scripted narration is not evidence of adaptive
scientific reasoning.

## 16. Validate research acceleration

Acceleration means less resource or elapsed time to reach an equally reliable
scientific conclusion. A valid comparison specifies:

- conventional baseline workflow;
- accelerated workflow;
- equal target conclusion or accuracy requirement;
- machine-independent work measure;
- wall time and environment;
- agreement with a larger reference;
- repeated trials and uncertainty.

Report both speed and agreement. If a sequential method uses half the compute
but frequently reaches a different conclusion, it has not demonstrated useful
acceleration.

The SDK may also reduce time-to-valid-evidence through automatic schemas,
provenance, validation, and reproduction. Quantify saved manual steps and
failure detection; do not translate convenience into an invented multiplicative
speedup.

### Current measured acceleration evidence

The recorded selective-escalation study applies the same frozen-gate idea used
for model verification to experimental sample size. Across five replicates and
seven development-stage hypotheses, it observed:

- mean full-size/selective compute ratio `1.542`, with bootstrap 95% CI
  `[1.280, 1.901]`;
- mean simulation-compute saving `35.15%`;
- reference agreement `28/35` for selective escalation versus `29/35` for the
  conventional 24-seed design;
- five early-look errors rescued and zero correct early decisions damaged.

This supports a bounded compute-efficiency claim, not exact equivalence,
held-out scientific confirmation, or a universal acceleration factor. The
frozen protocol is `discolab/escalation_protocol.yaml`; the report and complete
machine-readable result are under `discolab/results/escalation/`.

## 17. Reporting template

Every empirical report should contain:

1. research question and hypothesis;
2. protocol version and frozen date;
3. design, experimental unit, sample size, and splits;
4. implementation and environment;
5. primary result with effect size and interval;
6. failures, exclusions, missingness, and censoring;
7. secondary and exploratory results, clearly labeled;
8. robustness and sensitivity analyses;
9. threats to internal, external, construct, and statistical validity;
10. exact claims supported, unresolved, and contradicted;
11. links to raw and machine-readable artifacts;
12. commands for validation and reproduction.

## 18. Review checklist

- [ ] Hypothesis is falsifiable and comparator-specific.
- [ ] Protocol predates confirmation outcomes.
- [ ] Experimental unit is correct.
- [ ] Development/tuning/held-out boundaries are intact.
- [ ] Seed blocks do not leak.
- [ ] Primary metric, SESOI, and stopping rule are frozen.
- [ ] Failures and abstentions are retained.
- [ ] Pairing, clustering, censoring, and multiplicity are handled.
- [ ] Effect size and uncertainty are reported.
- [ ] Replay and provider-backed evidence are separated.
- [ ] Raw, derived, and analysis artifacts retain lineage.
- [ ] At least one result is independently reproduced.
- [ ] Claims do not exceed the studied task, split, provider, or environment.
