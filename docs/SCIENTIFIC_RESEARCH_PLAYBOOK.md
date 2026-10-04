# Scientific research playbook

This playbook distils established research-method, statistical, computational,
and scientific-communication principles into operational rules for EigenBrains
agents. Domain-specific standards and current primary literature still govern
each real study.

## Knowledge domains synthesized

- Research design: falsifiable questions, experimental and quasi-experimental
  comparisons, power, validity, ethics, criticism, and reproducibility.
- Statistical inference: likelihood, Bayesian and frequentist inference,
  confidence intervals, resampling, regression, causal identification,
  measurement error, and post-selection uncertainty.
- Sequential experimentation: adaptive design, information gain, explicit
  stopping rules, robust comparisons, and conclusion-agreement checks.
- Numerical reliability: floating-point behavior, conditioning, stability,
  convergence, optimization, integration, sensitivity, and performance.
- Machine learning: generalization, regularization, model selection, leakage,
  calibration, and held-out evaluation.
- Research integrity and communication: provenance, responsible data handling,
  peer review, transparent methods, honest figures, limitations, and accurate
  communication to technical and non-technical audiences.

## Operating doctrine

### 1. Start with an identifiable question

Every proposal must state:

1. the phenomenon or parameter of interest;
2. the intervention/exposure and comparator;
3. the observable outcome and unit of analysis;
4. the mechanism that would connect cause and outcome;
5. the result that would count against the hypothesis.

Do not confuse prediction with causation. A predictive feature may be useful
without being causal; an intervention requires a comparison that identifies its
marginal effect.

### 2. Build an evidence map, not a citation pile

For each source record the claim it supports, population/system, intervention,
comparator, outcome, design, limitations, and provenance. Search actively for:

- prior work that removes novelty;
- negative or contradictory evidence;
- stronger baselines;
- alternative mechanisms;
- measurement and external-validity limits.

Agent summaries remain interpretations. Only verified bibliographic metadata
and tool-produced measurements are facts in the ledger.

### 3. Separate exploration, development, and confirmation

- Exploration may generate features and hypotheses, but it cannot confirm them.
- Development data may tune models, thresholds, stopping rules, and policies.
- Held-out data is spent only after all choices are frozen.
- Post-hoc hypotheses must be labelled and tested on fresh data.
- Repeated looks, multiple outcomes, and model selection must be reflected in
  uncertainty or multiplicity control.

### 4. Design comparisons that isolate the mechanism

Use randomization or common random numbers where appropriate. Include the
strongest credible baseline, a simple baseline, and mechanism-matched controls.
For adaptive systems, compare timing against an intervention with the same
average intensity; otherwise a gain may come from dosage rather than adaptation.

Specify confounders, leakage paths, censoring, missingness, measurement error,
dependence, and stopping rules before execution. Prefer the simplest experiment
that can change the decision.

### 5. Treat uncertainty as part of the result

Report effect sizes and intervals, not only tests or posterior labels. Match the
resampling unit to the independent unit; preserve paired structure; use cluster
or stratified methods when observations within runs are dependent. Distinguish:

- statistical significance from practical importance;
- absence of evidence from evidence of absence;
- model uncertainty from provider/operational failure;
- mean performance from tail risk and failure probability.

### 6. Use sequential experimentation without optional-stopping fiction

Adaptive selection is appropriate when decisions are sequential and outcomes
can update which experiment is most informative. It must have:

- a frozen candidate-generation and scoring rule;
- explicit compute/data budgets;
- auditable stopping conditions;
- a fixed reference or exhaustive comparator;
- evaluation of conclusion agreement, not speed alone.

### 7. Demand numerical reliability and reproducibility

Record seeds, software versions, configuration hashes, code fingerprints,
hardware-relevant settings, raw artifacts, and all exclusions. Test invariants.
Perform sensitivity analysis for thresholds and assumptions. Numerical methods
must report convergence, conditioning/stability risks, and failure states rather
than silently returning plausible numbers.

### 8. Communicate so another researcher can reproduce the work

Every result should contain: question, prior evidence, preregistered design,
methods, units, raw/derived artifacts, effect with uncertainty, limitations,
decision, and next experiment. Methods must correspond to every reported result.
Figures need units, denominators, uncertainty, and an honest caption. Negative
results and deviations are part of the contribution.

## Role-specific checklist

### Literature agent

- Map each claim to a verified source and an explicit relation.
- Search for disconfirming evidence and prior art before claiming novelty.
- Distinguish source content from the agent's interpretation.
- State search limitations; never call a short search systematic.

### Designer

- State the estimand, unit, comparator, smallest effect of interest, and decision changed.
- Propose at least two genuinely different experiments.
- Protect held-out data and avoid data-dependent policy selection.
- Include mechanism-matched and literature-standard baselines.
- Anticipate null, adverse, and inconclusive outcomes.

### Critic

- Challenge identification, leakage, dependence, multiplicity, censoring, and external validity.
- Compare interval width with the smallest effect of interest.
- Separate predictive improvement from intervention value.
- Ask whether a simpler mechanism explains the result.
- Recommend the cheapest decisive falsification test.

### Principal investigator

- Select on expected decision value under budget, not narrative appeal.
- Justify overrides and stopping decisions in the ledger.
- Spend held-out evidence only after policy choices are frozen.
- Report acceleration only when a faster policy preserves reference-conclusion agreement.
