# Evidence-first demo integration runbook

The product demonstration should expose one complete scientific transition
without changing the existing navigation or seven-chapter story. The frontend
already has the visual system, workspace shell, progressive charts, inspectors,
and preserved home position. What remains is to connect those surfaces to the
read-only laboratory bridge and make provenance visible.

## Demonstration contract

The primary path is:

```text
question
  -> verified literature and hypotheses
  -> competing experiment candidates
  -> information-gain/cost scoring
  -> PI selection
  -> real experiment and progressive curves
  -> effect estimate, interval, and verdict
  -> Bayesian posterior update
  -> changed next decision
  -> measured selective-escalation economics
```

The UI must support two explicitly labelled modes:

- `RECORDED`: committed, replayable discovery evidence;
- `LIVE`: a currently running laboratory source.

Do not call a recorded stream live. `SAMPLE` interface fixtures must remain
visually distinct from both.

## Existing data surface

Start the read-only bridge from `discolab/`:

```powershell
python -m discolab.bridge --port 8765
```

It already exposes:

| Endpoint | Frontend use |
|---|---|
| `GET /lab/sources` | recorded/live source picker, event and experiment counts, preregistration hash |
| `GET /lab/state?source=...` | hypotheses, posterior trajectories, scoring rounds, selections, decisions, analyses |
| `GET /lab/activity?source=...` | agent handoffs, tool calls, approvals, and messages |
| `GET /lab/experiment?source=...&id=E#` | experiment result, score, specification, and progressive plot curves |
| `GET /lab/stream?source=...` | named `ledger`, `agent`, and `heartbeat` SSE events |

The browser should reach this through a Vite proxy such as `/lab`, never a
hardcoded machine URL. Add TypeScript response mirrors and a dedicated client;
do not fetch directly inside presentation components.

## Frontend work required

### 1. Evidence source and run header

Add a quiet source selector to the existing toolbar or inspector. The active
workspace header should always display:

- `RECORDED` or `LIVE` evidence label;
- source identifier;
- preregistration hash prefix;
- event and completed-experiment counts;
- connection state and last event time.

### 2. Agent activity timeline

Render PI, literature, designer, and critic activity from `/lab/activity` and
the SSE stream. Use the existing graph as the stable spatial anchor while a
compact timeline records handoff, tool, approval, and completed states. Agent
text is interpretation; numerical facts should link to tool/result cards.

### 3. Candidate experiment decision table

For each scoring round, show:

- experiment ID, title, stage, and hypotheses;
- expected information gain in bits;
- estimated wall time and utility;
- feasibility and violations;
- selected candidate and whether the PI followed the deterministic argmax;
- selection justification.

The table is more important than another architecture diagram because it proves
that the system considered alternatives before spending compute.

### 4. Progressive scientific plots

When an experiment is selected, request `/lab/experiment`. Draw the provided
fitness-error, entropy, and mutation-rate series progressively once per panel
opening. Mark landscape shifts and use textual summaries for accessibility.
Do not continuously loop the animation or recompute scientific values in the
browser.

### 5. Result and belief-update panel

The key result module should include:

- experimental unit, development/held-out stage, sample size, and comparator;
- primary effect and 95% interval;
- supported/refuted/inconclusive verdict;
- posterior before and after;
- critic limitations;
- next decision and how it differs from the previous plan.

Sign conventions must be explicit, especially when lower recovery time is
better.

### 6. Acceleration evidence panel

Add one `BENCHMARK` card derived from the committed summary rather than typed
constants:

| Metric | Display |
|---|---:|
| Mean compute acceleration | `1.54x` |
| 95% interval | `[1.28, 1.90]` |
| Mean compute saved | `35.15%` |
| Selective/full-size agreement | `28/35` / `29/35` |
| Rescue/damage | `5` / `0` |

Place the limitation adjacent to the numbers: development-stage landscapes;
near-matched rather than identical agreement. A secondary card may show the
model-routing replay result: equal observed quality `0.750`, `16.0%` estimated
cost saving, and `35.2%` latency saving versus always-both.

### 7. Provenance inspector

The existing inspector should expose links or copyable values for:

- experiment/run ID;
- protocol and preregistration hash;
- seed block;
- code fingerprint;
- artifact type and evidence label;
- recorded limitations;
- repository-relative artifact location.

### 8. Complete state handling

Implement explicit loading, empty, disconnected, malformed-evidence, recorded,
and live states. Losing SSE should retain the last valid snapshot and show a
reconnect state; it must not silently switch to fixtures.

## Demo sequence

Use a committed source for the main presentation and keep live mode optional:

1. Open the last Home chapter and enter the Trace/Agents workspace.
2. Select recorded run 2.
3. Show two or more competing candidates and the PI selection.
4. Open E1/E4/E7, draw the plot, and show the numerical verdict.
5. Animate the posterior transition and reveal the changed next decision.
6. Open the acceleration card and show the 1.54x/28-of-35 evidence.
7. Show the sealed held-out test: development +0.139 AUROC, held-out −0.006
   [−0.011, −0.0003], verdict `no_meaningful_gain`, Griewank +0.058 vs Levy
   −0.046 ([report](SEALED_ENTROPY_EARLY_WARNING_RESULT.md)). Say plainly that
   `accepted_as_evidence` means the negative result is valid evidence, not that
   the hypothesis was accepted, and keep it separate from the 1.54x claim.
8. Open provenance briefly to prove that every number has a run and artifact.

A recorded evidence path is the reliable default. A live Omnigent session can
run beside it, but provider availability must not be allowed to decide whether
the central demonstration succeeds.

## Acceptance criteria

- No claim-bearing number comes from `src/dev/fixtures.ts`.
- Every number carries an evidence label and source/run identity.
- Recorded and live modes are visually and semantically distinct.
- Candidate alternatives and the selection rationale are visible.
- At least one result changes a posterior and the next decision on screen.
- Plot data come from `/lab/experiment`, with no browser-side scientific math.
- The acceleration card matches `summary.json` exactly.
- Keyboard navigation, reduced motion, contrast, and textual chart summaries
  pass the checklist in `FRONTEND_GUIDE.md`.
- The complete recorded flow succeeds three consecutive times with the network
  restricted to localhost.
