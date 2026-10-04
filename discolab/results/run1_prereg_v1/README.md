# Run 1 — pilot under pre-registration v1

First complete, live discovery loop of the lab: an Omnigent PI session that
delegated to the literature, designer and critic agents, ran two real
experiments, updated its beliefs and changed its next decision. Wall time
291 s; 34.5 s of experiment compute. Omnigent-reported model cost: USD 0.546
for the PI session; the five sub-agent sessions report USD 0.331 between them
(in our smoke test the parent total rose when its child finished, which
suggests the PI figure already includes sub-agents, i.e. about USD 0.55 in
total — not independently verified).

Files (machine paths replaced by `.` = lab root, `<discolab>` = project dir;
otherwise byte-identical to what the lab wrote):

| File | Content |
|---|---|
| `ledger.jsonl` | the 29 research-ledger events (who decided what, with the prereg SHA-256) |
| `omnigent_events.jsonl` | the Omnigent session stream for the PI and all sub-agent sessions |
| `session.log` | the driver's console view (handoffs, tool calls, agent messages) |
| `final_report.md` | the PI's final report, verbatim |
| `runs/E2`, `runs/E4` | raw artifacts: `traces.npz`, `outcomes.jsonl`, `manifest.json` (seeds, code fingerprint), `summary.json` |
| `prereg_v1.yaml` | the frozen protocol the run used (from commit `1099cb0`) |

Pre-registration check: the ledger's `prereg_sha256`
`93132876…57d8f` equals the SHA-256 of `prereg_v1.yaml` as checked out with
CRLF line endings on the Windows machine that ran it (v2 hashes are
line-ending normalised).

## Decision trace (from `ledger.jsonl`)

| # | Actor | Event |
|---|---|---|
| 2–4 | designer | proposed E1 (H1 entropy), E2 (H2 dispersion + H3 spread), E3 (H4 control) |
| 5 | designer | scored: E2 U=1.6725, E1 U=0.834, E3 U=0.3424 |
| 6 | PI | selected E2 (the argmax) |
| 7–13 | literature | 7 OpenAlex-verified evidence records (in parallel with design) |
| 14 | PI | ran E2 |
| 15–17 | critic → planner | analysis; H2 0.5 → 0.975 (supported); H3 0.5 → 0.667 |
| 18 | critic | registered H5 (agent-generated): entropy beyond dispersion |
| 19 | PI | decision: treat dispersion as a supported development-stage signal; test entropy next |
| 20–23 | designer | proposed E4–E6; re-scored: E4 U=0.4826 … E1 U=0.1232 |
| 24–25 | PI | selected and ran E4 (the argmax) |
| 26–27 | critic → planner | analysis; H4 0.3 → 0.304 |
| 28 | critic | registered H6 (agent-generated): B3 vs a rate-matched fixed rate |
| 29 | PI | decision: no control benefit claimed; test H6 and a dispersion-driven controller next |

## Results

**E2 — prediction, development stage (leave-one-landscape-out, 72 test runs,
5188 at-risk generations, stagnation prevalence 0.028, 11.4 s).**

| Feature set | AUROC [95% CI] | ΔAUROC vs fitness-only |
|---|---|---|
| fitness | 0.677 [0.615, 0.738] | — |
| fitness + dispersion | 0.708 [0.652, 0.763] | **+0.031 [0.021, 0.041]** → H2 supported |
| fitness + spread | 0.685 [0.626, 0.745] | +0.008 [−0.007, 0.023] → H3 inconclusive |

**E4 — control, development stage (Rastrigin + Ackley, 12 seeds each, 5 shifts
per run, 23.1 s).** Restricted mean recovery time (lower is better, horizon 60):

| Controller | RMST | ΔRMST vs B0 [95% CI] | rescue / damage vs B0 |
|---|---|---|---|
| B0 fixed | 51.93 | — | — |
| B3 predictive (entropy risk model) | 51.67 | −0.26 [−3.33, 3.11] | 29 / 18 |
| B4a triggered hypermutation | 54.62 | +2.68 [−0.24, 5.51] | 21 / 30 |
| B1 stall-adaptive | 55.50 | +3.57 [0.29, 6.78] | 15 / 44 |
| B4b random immigrants | 57.51 | +5.58 [2.97, 8.33] (Holm) | 15 / 52 |
| B2 entropy-level | 59.43 | +7.49 [4.78, 10.19] (Holm) | 1 / 61 |

H4 (B3 beats the strongest baseline, here B0): inconclusive. B3's mean mutation
rate was 0.081 vs B0's 0.100, so its small edge in recovered shifts may be a
rate effect rather than timing (the critic's H6).

## What this run taught the lab — and its builders

- **Science (development stage only):** dispersion adds early-warning
  information beyond fitness history; entropy has not yet been tested as a
  predictor; using entropy *level* to set mutation is strongly harmful; the
  entropy-risk controller is not distinguishable from fixed mutation.
- **Method flaws found by the run itself** and fixed in prereg v2 (see its
  changelog): an inconclusive verdict raised H3's posterior (0.5 → 0.667; the
  PI flagged it as an artifact); H1's planned power inherited H3's effect
  through update order (E1's utility fell to 0.123); recovery-rate intervals
  ignored clustering of shifts within runs (flagged by the critic and PI); the
  cost model underestimated wall time about 5×; a hypothesis could be
  registered with a non-existent feature set (H5), which spec validation then
  rejected; an evidence id could be "corrected" by the agent without a title
  check (the corrected id's abstract does support its claim).
