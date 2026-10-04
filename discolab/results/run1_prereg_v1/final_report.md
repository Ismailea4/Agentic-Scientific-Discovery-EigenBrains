## Final report

**Question.** Do population-entropy dynamics warn of GA stagnation beyond fitness history, and can that signal drive a mutation intervention that recovers faster after a landscape change?

**Evidence (OpenAlex ids, literature agent).**
- Entropy-driven adaptation: W2350741577, W2368004679.
- Fitness diversity as an adaptive trigger: W3132915544.
- Self-adaptive mutation baseline: W2167823546.
- Dynamic-environment baselines (immigrants, hypermutation): W2132340807, W1856400953.
- Early-warning methodology: W3200303296.
- Prior work uses entropy for control. The agent found none that tests it as an out-of-sample predictor, or a frozen risk model driving mutation. That novelty claim comes from the agent's searches and is not independently checked.

**Hypotheses and posteriors (before → after).** All results are development stage only.

| Hypothesis | Posterior | Status |
|---|---|---|
| H1: entropy features add AUROC | 0.5 → 0.5 | untested |
| H2: dispersion features add AUROC | 0.5 → 0.975 | supported |
| H3: fitness-spread features add AUROC | 0.5 → 0.667 | inconclusive |
| H4: predictive controller (B3) recovers faster | 0.3 → 0.304 (state showed 0.5 before E4) | inconclusive |
| H5 (agent-generated): entropy adds beyond dispersion | 0.5 | untested |
| H6 (agent-generated): B3 beats a rate-matched fixed mutation | 0.5 | untested |

- H3's rise is an artifact of the pre-registered update rule. The verdict was inconclusive, so it is not support.

**Experiments run.**
- **E2** (leave-one-landscape-out, 72 runs, stagnation prevalence 0.028):
  - Fitness-only AUROC was 0.677 [0.615, 0.7381].
  - Fitness plus dispersion gave +0.0306 [0.0213, 0.0407], so H2 is supported.
  - Fitness plus spread gave +0.0081 [-0.0073, 0.0231], so H3 is inconclusive.
  - Brier did not improve (0.0272 vs 0.0271).
- **E4** (24 units, ackley and rastrigin):
  - B3 vs fixed mutation (B0): RMST −0.2583 generations [−3.325, 3.1088], inconclusive.
  - The entropy-threshold controller (B2) was harmful: +7.4917 [4.7831, 10.1921].
  - Immigrants were worse than B0: +5.575 [2.9667, 8.3333].
  - Hypermutation did not beat B0: +2.6833 [−0.2417, 5.5085].

**What the lab learned.**
- A genotypic dispersion signal improves stagnation ranking modestly, and the CI clears the 0.01 smallest effect of interest.
- No evidence yet that entropy helps. As a controller trigger it hurt.
- The predictive controller did not beat fixed mutation. It also mutated less on average (0.0811 vs 0.1), so timing and a lower rate are confounded.
- Negative result: the lab's headline hope, entropy-driven early warning leading to faster recovery, is unsupported so far.

**Next experiment, and why it differs.** Before E2 and E4, I would have run the entropy-vs-fitness test (E1). Now:
- Test B3 against a fixed p_mut of about 0.08 (H6).
- Test a B3 variant whose risk model uses dispersion instead of entropy.
- Cluster the analysis by unit.
- First add a fitness+dispersion+entropy feature set so H5 can be tested. The planner rejected that candidate this round.

**Limitations and validation still needed.**
- Everything is development stage. There is no held-out confirmation, which needs human approval.
- The CIs may ignore clustering within runs. E4 has 24 units but 120 paired runs, so McNemar and recovery-rate CIs are likely too narrow.
- The tail metric (CVaR90) is censored at 60 generations for every controller.
- The risk model was fit on 72 runs with entropy features, although dispersion was the useful signal.
- Transfer across landscapes is untested.
- A slip in my own justification: I wrote E4's utility as 0.4826 correctly, but in round 1 I wrote E2's as "0.6725" when the tool shows 1.6725. That is recorded in the selection text.
- Compute used was 34.5 s of 1800 s.