# Financial mathematics, econometrics, and the EigenBrains meta-agent

EigenBrains treats model and agent selection as a constrained portfolio problem. A model is not valuable only because of its average score; it is valuable when its expected contribution, failure dependence, cost, latency, availability, and downside behavior improve the system that contains it.

This document describes the theory implemented by the optimizer and benchmark layers, then separates that theory from the evidence actually observed in Architecture Baseline v0.

## 1. Random variables and observations

For model or architecture `i` on case `k`, define bounded quality and loss:

\[
Q_{ik} \in [0,1], \qquad L_{ik}=1-Q_{ik}.
\]

The empirical expected loss and variance are:

\[
\hat\mu_i=\frac{1}{n}\sum_{k=1}^{n}L_{ik},
\qquad
\widehat{\operatorname{Var}}(L_i)
=\frac{1}{n}\sum_{k=1}^{n}(L_{ik}-\hat\mu_i)^2.
\]

Paired evaluation matters: every compared model sees the same case. This makes the cross-model covariance estimable:

\[
\hat\Sigma_{ij}
=\widehat{\operatorname{Cov}}(L_i,L_j)
=\frac{1}{n}\sum_{k=1}^{n}(L_{ik}-\hat\mu_i)(L_{jk}-\hat\mu_j).
\]

High positive covariance means models tend to fail on the same cases. Lower covariance can make a weaker individual model valuable as a second opinion.

## 2. Availability is not intelligence

The benchmark explicitly separates three quantities:

\[
P(\text{provider success}),
\]

\[
P(\text{correct}\mid\text{provider success}),
\]

and

\[
P(\text{operationally correct})
=P(\text{provider success})
P(\text{correct}\mid\text{provider success}).
\]

This prevents a transport failure from being mislabeled as weak reasoning and prevents a strong-but-unavailable model from looking deployable. Latency conditional on success and end-to-end severe-failure probability are reported separately for the same reason.

## 3. Portfolio interpretation

Let `w_i` be the share of workload routed to candidate `i`, with:

\[
w_i\ge 0, \qquad \sum_i w_i=1.
\]

The portfolio's expected loss and variance are:

\[
E[L_w]=w^T\mu,
\qquad
\operatorname{Var}(L_w)=w^T\Sigma w.
\]

This is analogous to mean-variance portfolio construction, but the assets are decision policies and the adverse return is task loss. The analogy is not literal finance: routing weights represent workload allocation, and model errors are bounded, paired empirical observations rather than market returns.

The implemented workload objective is a constrained utility:

\[
U(A)=E[Q_A]
-\lambda R_A
-\eta\frac{C_A}{B}
-\rho\frac{T_A}{T_{\max}},
\]

where:

- `Q_A` is expected architecture quality;
- `R_A` is an explicit risk measure;
- `C_A/B` is cost normalized by budget;
- `T_A/T_max` is latency normalized by the service limit;
- `λ`, `η`, and `ρ` are caller-supplied preferences.

Normalization makes cost and latency dimensionless before combining them with quality. The system does not ship hidden “fast,” “balanced,” or “reliable” numerical weights.

## 4. Hard constraints precede utility

Candidate feasibility is a separate stage:

\[
\mathcal F
=\{A:\text{capabilities, privacy, availability, and task scope are satisfied}\}.
\]

Only `A ∈ F` can enter Pareto or utility selection. This matters because an attractive expected score must never compensate for a denied capability or unacceptable privacy class.

## 5. Empirical and robust Pareto frontiers

Architecture `a` empirically dominates `b` when it has:

\[
Q_a\ge Q_b,\quad C_a\le C_b,\quad T_a\le T_b,\quad R_a\le R_b,
\]

with at least one strict inequality. Non-dominated candidates form the empirical frontier.

Small samples make point-estimate frontiers brittle. The robust comparison uses confidence bounds. A candidate is robustly better only when its pessimistic quality bound and adverse cost, latency, and severe-failure bounds still dominate the other candidate's favorable bounds. If intervals overlap, the comparison remains unresolved rather than being forced into a ranking.

The implementation also estimates bootstrap probabilities of dominance. These are descriptive probabilities under empirical resampling, not guarantees about future tasks.

## 6. Downside risk

Average quality can hide rare catastrophic failures. With loss `L`, the laboratory records:

- severe-failure probability at a frozen threshold;
- downside semivariance;
- Value at Risk, `VaR_α`;
- Conditional Value at Risk, `CVaR_α`;
- worst-decile loss and worst observed score.

For loss quantile `VaR_α(L)`, CVaR is:

\[
\operatorname{CVaR}_\alpha(L)
=E[L\mid L\ge \operatorname{VaR}_\alpha(L)].
\]

At small `n`, tail estimates are deliberately labeled unstable. In the 12-case held-out slice, the worst observed outcome dominates the tail statistic, so the result is useful as a warning but not a precise tail estimate.

## 7. Conditional escalation economics

For a first model `F`, verifier `V`, and gate event `G`, selective execution has expected cost and latency:

\[
E[C_{sel}]=E[C_F]+P(G)E[C_V\mid G],
\]

\[
E[T_{sel}]=E[T_F]+P(G)E[T_V\mid G].
\]

Always-both pays both terms on every case. Selective escalation saves resources whenever `P(G)<1`, but this alone does not establish quality value.

For binary correctness, the quality change relative to the first model decomposes into rescue and damage:

\[
\Delta Q
=P(F\text{ wrong},\,A\text{ correct})
-P(F\text{ correct},\,A\text{ wrong}).
\]

The two conditional quantities reported by the system are:

\[
P(\text{rescue}\mid G,F\text{ wrong})
\]

and

\[
P(\text{damage}\mid G,F\text{ correct}).
\]

An escalation policy is attractive only when the expected rescue benefit, reduction in severe failures, or reduction in tail risk justifies its incremental cost and latency.

## 8. The meta-agent policy

The meta-agent is a frozen routing and reconciliation policy, not another unconstrained language model. It can use only information available before seeing ground truth:

- task family;
- schema or constraint failure;
- task risk level;
- historical task-family error upper confidence bound;
- explicit abstention.

Architecture Baseline v0 defines:

| Policy | Behavior |
|---|---|
| `S0` | GPT-OSS only. |
| `S1` | Qwen only. |
| `S2` | Always run Qwen and GPT-OSS, then reconcile. |
| `S3` | Run Qwen first and selectively escalate to GPT-OSS. |
| `S4` | Run GPT-OSS first and selectively escalate to Qwen. |

The gate was fitted on development and tuning observations only. It escalates high-risk cases, schema/constraint failures, explicit abstentions, and task families whose Qwen historical error upper bound crosses the frozen `0.5` threshold. Task-family ownership breaks lower-risk disagreements and was also frozen before held-out evaluation.

## 9. Statistical inference

The laboratory uses methods matched to the estimand:

- Wilson intervals for proportions such as availability and correctness;
- percentile bootstrap intervals for mean quality, cost, latency, and paired differences;
- exact McNemar tests for paired binary outcomes;
- paired case bootstrap for covariance, correlation, Jaccard failure similarity, conditional failure, and rescue probability;
- diagonal shrinkage for small-sample covariance stabilization.

The shrinkage estimator retains empirical variances and contracts off-diagonal covariance toward independence:

\[
\tilde\Sigma
=(1-\gamma)\hat\Sigma+\gamma\operatorname{diag}(\hat\Sigma),
\]

with frozen intensity `γ=0.25` in the baseline.

## 10. Weak Bayesian priors

Generic evidence becomes a weak prior rather than a permanent conclusion. For empirical event rate `p̂` and bounded prior strength `κ`, the stored Beta prior is:

\[
\alpha_0=1+\kappa\hat p,
\qquad
\beta_0=1+\kappa(1-\hat p).
\]

Architecture Baseline v0 uses `κ=4`, capped at `5`, separately for:

- correctness conditional on provider success;
- severe failure conditional on provider success;
- provider availability;
- verifier rescue when a rescue opportunity exists.

New task data updates the sufficient statistics:

\[
\alpha=\alpha_0+s,
\qquad
\beta=\beta_0+f.
\]

Because the prior is weak, a modest amount of task-specific evidence can overturn it.

## 11. Transfer from model portfolios to experiment portfolios

The same policy applies when the scarce asset is simulation compute rather
than a model call. Let `N_1 < N_2 < N_3` be nested sample sizes and let `G_k`
mean that the preregistered verdict remains inconclusive at look `k`. Expected
work under selective escalation is:

\[
E[C_{seq}]
=C(N_1)+P(G_1)\{C(N_2)-C(N_1)\}
+P(G_1,G_2)\{C(N_3)-C(N_2)\}.
\]

A full-size design always pays `C(N_3)`. As with model verification, saved work
is scientifically valuable only when the sequential policy preserves the
reference conclusion. The recorded study freezes looks at 6, 12, and 24 seeds,
uses Bonferroni-adjusted 98.33% intervals at each look, and escalates only while
the result is inconclusive.

Across five replicates and seven hypotheses, full-size compute divided by
selective compute averaged `1.542` (95% CI `[1.280, 1.901]`), or `35.15%` mean
compute saved. Selective escalation agreed with the 48-seed reference on
`28/35` hypothesis-replicates versus `29/35` for the conventional 24-seed
design. It rescued five incorrect early decisions and damaged none. This is
near-matched agreement, not proof of equivalence, and it is development-stage
evidence only.

The important meta-agent result is therefore structural: uncertainty governs
whether the system buys another model call or another block of experimental
samples. Both policies expose the gate, rescue, damage, cost, latency/work, and
agreement needed to audit the decision.

## 12. Measured model and architecture results

### Single-model operational evidence

Each model saw the same 72 cases.

| Model | Provider availability | Correct given successful call | Operationally correct | Mean successful-call latency |
|---|---:|---:|---:|---:|
| GPT-OSS via Groq | `0.653` | `0.915` | `0.597` | `764.9 ms` |
| Qwen via Groq | `0.639` | `0.913` | `0.583` | `448.2 ms` |
| DeepSeek via OpenRouter | `1.000` | `0.861` | `0.861` | `7755.6 ms` |

The econometric lesson is material: GPT-OSS and Qwen were strong conditional on a successful response, but availability reduced end-to-end performance. DeepSeek was slower and slightly weaker conditionally, yet its observed availability made it strongest operationally in this run.

### Failure dependence

| Pair | Error correlation, 95% bootstrap | Failure Jaccard | `P(right succeeds | left fails)` |
|---|---:|---:|---:|
| GPT-OSS ↔ Qwen | `0.742 [0.577, 0.886]` | `0.735` | `0.138 [0.031, 0.278]` |
| GPT-OSS ↔ DeepSeek | `0.489 [0.336, 0.634]` | `0.345` | `0.655 [0.467, 0.824]` |
| Qwen ↔ DeepSeek | `0.394 [0.195, 0.570]` | `0.290` | `0.700 [0.520, 0.857]` |

GPT-OSS and Qwen were comparatively redundant. DeepSeek was more complementary to both, especially to Qwen. This is precisely why portfolio selection must consider covariance rather than choosing the top two marginal scores.

### Held-out selective architecture evidence

On 12 sealed held-out cases:

| Policy | Quality | Cost/case | Latency/case | Escalation |
|---|---:|---:|---:|---:|
| `S1` Qwen only | `0.750` | `$0.00006087` | `526.9 ms` | `0%` |
| `S2` always both | `0.750` | `$0.00008324` | `1591.9 ms` | `100%` |
| `S3` Qwen → selective GPT-OSS | `0.750` | `$0.00006992` | `1030.9 ms` | `58.3%` |

Relative to always-both, `S3` preserved the same observed quality while using `16.0%` less estimated cost and `35.2%` less latency. Relative to Qwen only, it added cost and latency without an observed quality gain.

The provider-backed confirmation made seven verifier calls for `S3` and seven for `S4`. It observed zero rescues and zero damage. Therefore the supported claim is efficiency versus always-both, not improved accuracy from verification.

### What is unresolved

- All held-out quality differences among `S2/S3` versus `S1`, and `S4` versus `S0`, include zero in their 95% paired intervals.
- Twelve held-out cases are insufficient for a stable tail-risk estimate.
- The benchmark does not establish performance on a new domain.
- The measured GPT-OSS/Qwen gate should not be generalized into a universal architecture rule.

The complete frozen results are in Architecture Baseline v0's historical
ledger file, `benchmark/reports/PRECHALLENGE_BASELINE_V0.md`, and the
machine-readable summary is in
`benchmark/artifacts/baseline_v0/baseline_v0_summary.json`. The legacy filename
is retained to preserve evidence identity; it is not current product wording.

