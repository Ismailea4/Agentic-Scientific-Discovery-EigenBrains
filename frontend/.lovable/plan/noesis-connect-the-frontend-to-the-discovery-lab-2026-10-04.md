# Noesis: connect the frontend to the discovery lab

## Goal
Rename the project to Noesis and make the four lab views show real data from your teammates' discovery lab (branch `omnigent-efficient-integration`), without changing any of their code.

## What the backend offers (read-only)
The lab ships a small read-only data feed (default port 8765):
- `GET /lab/sources`: live labs and recorded runs (for example `results/run2_prereg_v2`)
- `GET /lab/state?source=`: question, hypotheses with posteriors and trajectories, literature evidence (OpenAlex/arXiv), candidate experiments with expected information gain and utility, scoring rounds, critic analyses, decisions, compute budget
- `GET /lab/activity?source=`: agent handoffs (PI → literature / designer / critic), tool calls, messages, approval requests
- `GET /lab/experiment?source=&id=E#`: verdicts with effect sizes and CIs, AUROC or recovery results, per-generation curves
- `GET /lab/stream?source=`: live `ledger`, `agent`, `heartbeat` events

The existing `/api` and `/health` calls stay unchanged.

## What will be built
1. **Rename to Noesis** everywhere: titles, sidebar, page metadata, copy, AGENTS.md and project memory.
2. **Lab connection setting**: defaults to the local feed; the user can paste a public address (for example a tunnel) in a small settings popover. The setting is saved in the browser and shows a connected / offline badge.
3. **Source picker** in the toolbar: choose a live lab or a recorded run.
4. **Discovery Loop**: agent graph driven by real activity (PI, literature, designer, critic), showing who is working now, handoffs and tool calls; the six-stage loop highlights the current stage from ledger events.
5. **Hypotheses**: real hypotheses with statement, family, status, posterior and a posterior-over-time trajectory; candidate experiments ranked by expected information gain and utility, with the argmax and the PI's actual choice and justification.
6. **Human Approval Gate**: approval requests from activity (confirmatory held-out runs), compute used vs budget, feasibility violations. Read-only: it shows what is pending; approval happens in the lab terminal.
7. **Research Record**: question, evidence citations (OpenAlex/arXiv links), experiments with verdicts, effect sizes and confidence intervals, critic interpretations and threats to validity, per-generation curves, and decisions. Live mode appends events from the stream.
8. **Samples swapped** from reinforcement learning to the real genetic-algorithm stagnation study (population entropy as early warning), labelled SAMPLE. Samples are shown only when the feed is offline or no source is picked.
9. **Honest states**: LIVE for `lab_home/*`, RECORD for `results/*`, SAMPLE for fixtures; clear loading, empty, offline and error states.

## Out of scope
No changes to teammates' code, no Start-run button, no running Omnigent from the app.

## Technical details
- New `src/noesis/api/lab.ts` (typed client) and `lab-types.ts` mirroring `bridge.py` / `views.py` shapes; base URL from saved setting, falling back to `VITE_LAB_URL` then `http://127.0.0.1:8765`.
- The feed sends no CORS headers. For local runs, add a dev proxy `/lab → 127.0.0.1:8765` in `vite.config.ts` and default to same-origin `/lab`. For a public address, document running the tunnel or a reverse proxy that adds CORS; the app shows a clear message if blocked.
- Reuse `subscribeSSE` with events `ledger`, `agent`, `heartbeat`; TanStack Query for state/activity/experiment with refetch on ledger events.
- Rename folder `src/neosis` → `src/noesis` and the logo asset pointer; update imports.
- Data loads only in the browser (no SSR fetching).
- Verify with a recorded run fixture served locally (copy of `results/run2_prereg_v2` responses) via Playwright: every view renders real hypotheses, citations, verdicts and curves; offline state falls back to samples.
