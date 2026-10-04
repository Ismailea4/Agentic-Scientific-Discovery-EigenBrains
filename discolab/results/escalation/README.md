# Measured acceleration — selective escalation of experiments

**Bottleneck attacked:** the simulation compute a lab spends to reach a reliable
conclusion about each hypothesis. A conventional design runs every test at full
size; most of that compute is wasted on questions whose answer is already clear
from a small sample.

**Policy:** the EigenBrains benchmark's final result transferred from model calls
to experiments. In the benchmark, selective escalation (a cheap model first, a
second model only when a frozen gate fires) kept quality while cutting cost 16%
and latency 35% versus always running both. Here the cheap step is a 6-seed
experiment and the gate is an *inconclusive* pre-registered verdict: escalate to
12, then 24 seeds, only while the evidence is still inconclusive (98.33%
intervals per look, Bonferroni over three looks).

Protocol: [`escalation_protocol.yaml`](../../escalation_protocol.yaml), committed
and pushed before any study data existed. Code: `discolab/escalation.py` at the
pushed commit `39941eb`, run in a clean checkout of that commit.

## Result (5 replicates × 7 hypotheses, development stage)

| | Full-size design (24 seeds) | **Selective escalation** | Small design (6 seeds) |
|---|---|---|---|
| Simulated generations per replicate | 506,304 | 227,232 – 441,504 | 137,376 |
| **Compute ratio vs full-size** | 1× | **1.54× less, 95% CI [1.28, 1.90]** | 3.69× less |
| Agreement with the 48-seed reference | 29/35 | **28/35** | 24/35 |

Per replicate, full-size ÷ escalation: 2.23, 1.51, 1.15, 1.45, 1.37 (every
replicate above 1). Mean compute saving 35%.

**Escalation economics (EigenBrains analysis):** the gate fired on 46% of first
looks; **5 rescues** (the 6-seed look disagreed with the reference and
escalation fixed it: H7 four times, H4 once) and **0 damages** (escalation never
turned a correct early answer wrong).

## Where the speed-up comes from

| Hypothesis | Reference (48 seeds) | Escalation stopped at |
|---|---|---|
| H1 entropy predicts stagnation | supported | 6 seeds, 5/5 replicates |
| H2 dispersion predicts | supported | 6 seeds, 5/5 |
| H5 entropy beyond dispersion | supported | 6 seeds, 5/5 |
| H4 entropy-risk controller beats baselines | supported | 6 seeds ×2, 24 seeds ×3 |
| H7 dispersion-risk controller beats baselines | supported | 6 ×1, 12 ×2, 24 ×2 |
| H3 fitness spread predicts | supported (tiny effect) | 6 ×1, 24 ×4 |
| H6 B3 timing beats a rate-matched fixed rate | inconclusive | 24 seeds, 5/5 |

Large effects are decided cheaply; the true null (H6) correctly runs to full size
and stays open; the moderate control effect H7 is exactly where the cheap design
fails and escalation rescues it.

## What it costs (stated with the speed-up)

- Escalation agreed with the reference once less than the full-size design
  (28 vs 29 of 35). The miss is H3, a very small effect that the full-size design
  also misses in 4 of 5 replicates; the stricter per-look intervals cost that one
  extra case. H4 is missed twice by both strategies.
- Development-stage landscapes only; held-out confirmation is outside this study.
- In replayed control looks the B3 risk models were fitted on the 24-seed
  design's development seeds (declared in the protocol beforehand).
- The speed-up comes from the lab's deterministic decision policy, which the
  Omnigent PI applies through the planner; it is not a property of the language
  models themselves.

## Toward 10×

The 1.54× here is one measured factor. Factors the lab already has, each still
to be *measured* rather than assumed before any multiplier is claimed:

1. **Selective escalation** (this study): 1.54× [1.28, 1.90] on compute.
2. **Planner pruning**: the utility rule drops low-information candidates before
   they run (in run 2, six of nine proposed designs were never run).
3. **Parallel agents**: literature review and experiment design run concurrently
   under Omnigent, shortening wall-clock time per round.
4. **Evidence reuse across hypotheses**: one prediction design tested H1–H3
   together in run 2 (2.6 bits of expected information for one experiment).
5. **Early stopping on nulls via a refutation rule**: nulls currently run to full
   size (H6); a pre-registered futility bound would cut that cost.

Compounding even three independent factors of about 1.5–2× each would put the
lab in the 3–8× range; reaching 10× needs those factors measured on the same
reference and confirmed on held-out landscapes.

## Files

`summary.json` (all numbers above, per hypothesis and per look), and for the
reference and each replicate: `ledger.jsonl` (the lab's research record),
`prereg_derived.yaml` (seed blocks), `runs/E#/manifest.json` (seeds, spec, code
fingerprint). Raw per-generation traces (125 MB) are not committed; they are
regenerated exactly by running `python -m discolab.escalation` at `39941eb`.
