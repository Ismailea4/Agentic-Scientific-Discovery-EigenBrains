# discolab — an Omnigent-orchestrated lab for evolutionary-search stagnation

**Question (pre-registered in [`prereg.yaml`](prereg.yaml)).** Do the dynamics of
population entropy give early warning of evolutionary-search stagnation beyond
what the fitness history already shows — and can that signal drive a mutation
intervention that recovers faster when the landscape changes?

The lab is a closed discovery loop. Omnigent agents decide; deterministic tools
compute; an append-only ledger records every transition:

```
Question → Evidence → Hypothesis → ≥2 competing experiments → scored selection
        → real GA simulations → pre-registered statistics → Bayesian update
        → recorded decision → next round's candidates (re-scored on the new beliefs)
```

## Architecture

```
scripts/run_session.py ── HTTP/SSE ──▶ Omnigent server ──▶ host/runner (this machine)
                                              │
                         discolab-pi  (supervisor, claude-sdk)
            sys_session_send │      │       │  sys_read_inbox
             ┌───────────────┘      │       └────────────────┐
        literature             designer                    critic
            │                       │                         │
            └──────── stdio MCP: python -m discolab.mcp_server ┘   (per-agent tool allow-lists)
                                    │
     lab.py ─ ledger.jsonl ─ planner.py ─ experiments.py ─ ga.py / controllers.py / landscapes.py
                                    │
                    lab_home/<lab>/runs/E#/  (traces.npz, outcomes.jsonl, manifest.json, summary.json)
```

Agents never produce numbers. Seeds, costs, simulations, statistics, verdicts and
posterior updates all come from `discolab` code; agents contribute choices and
attributed text (rationales, interpretations, decisions).

## Agents (Omnigent bundle: [`omnigent/lab_pi`](omnigent/lab_pi))

| Agent | Scientific decision it owns | Inputs | Outputs | Tools (allow-list) |
|---|---|---|---|---|
| `discolab-pi` (supervisor) | Which experiment runs next; when to run it; what the lab concludes and investigates next | research state, scoring table, critic report | selection with justification, run, decision record, final report | `get_research_state`, `get_experiment_result`, `select_experiment`, `run_experiment`, `record_decision` + sub-agents `literature`, `designer`, `critic` |
| `literature` | Which prior work is evidence for/against the hypotheses; how novel the question is | hypotheses | OpenAlex-verified evidence records | `get_research_state`, `search_literature`, `record_evidence` |
| `designer` | Which competing experiments the lab should consider | state, design space, prior results | ≥2 validated candidate specs + deterministic scores | `get_research_state`, `list_design_space`, `propose_experiment`, `score_experiments`, `register_hypothesis` |
| `critic` | What a result does and does not show; threats to validity | experiment result, state | analysis record (triggers the Bayesian update), optional new hypothesis | `get_research_state`, `get_experiment_result`, `record_analysis`, `register_hypothesis` |

Least privilege is structural: the literature agent cannot run experiments, the
designer cannot select or run them, the critic cannot change specs, and only the
PI can spend compute.

## Policies (Omnigent guardrails)

| Policy | Where | Effect |
|---|---|---|
| `discolab.policies.approve_confirmatory_runs` | PI | **Human approval (ASK)** before any run on held-out landscapes — held-out data can only be seen for the first time once |
| `max_tool_calls_per_session` | every agent | bounds each agent's loop (PI 120, literature/designer 30, critic 20) |
| `cost_budget` | PI | hard model-spend cap with an approval threshold |
| ledger transition guards | all tools | invalid transitions (select unscored/infeasible/completed, run unselected, analyse before completion, unsourced evidence) fail loudly and write nothing |
| planner hard constraints | scoring | compute budget; confirmatory test of a hypothesis only after a development-stage test |

## Experiment selection (deterministic)

`U(E) = EIG(E) − η·wall_seconds(E) − λ·held-out landscapes used(E)` after hard
constraints, with EIG in bits from a pre-registered likelihood table over the
three verdicts (supported / inconclusive / refuted) and the design's power. The
same table converts an observed verdict into the posterior, so the planner's
expectations and the belief update agree. Measured effects replace the assumed
effect size for later scoring — the planner learns from results. The form is the
EigenBrains constrained utility (quality − risk − cost − latency), re-targeted from
choosing model architectures to choosing experiments: decision theory inspired by
portfolio allocation, not literal finance.

## Science core

- **Landscapes**: Rastrigin, Ackley (development); Griewank, Levy, Styblinski–Tang
  (held-out), centered so the optimum is 0, translated by seeded shifts with a
  known moving optimum.
- **GA**: SBX + Gaussian mutation, tournament selection, re-evaluated elitism,
  common random numbers across controllers.
- **Telemetry**: population entropy H_t, genotypic dispersion D_t, fitness spread.
- **Controllers**: B0 fixed, B1 stall-adaptive, B2 entropy-level, B3 predictive
  (frozen logistic risk model), B4a triggered hypermutation, B4b random immigrants.
- **Phase 1 (prediction)**: AUROC for stagnation onset, fitness-only baseline vs
  entropy/dispersion/spread features; paired run-clustered bootstrap.
- **Phase 2 (control)**: restricted mean recovery time after shifts, Wilson
  recovery rates, rescue/damage vs B0 with exact McNemar, CVaR90, Holm correction.

## Run it

```bash
cd discolab
python -m venv .venv && .venv/Scripts/python -m pip install -e . "omnigent==0.16.0" "omnigent-client==0.16.0" pytest
.venv/Scripts/python -m pytest -q                      # invariant + statistics + ledger + end-to-end tests
bash scripts/start_lab.sh main 6810                    # Omnigent server + host, lab_home/main
DISCOLAB_HOME="$PWD/lab_home/main" .venv/Scripts/python scripts/run_session.py --port 6810 \
    --prompt "Run 2 complete discovery rounds, then give the final report."
DISCOLAB_HOME="$PWD/lab_home/main" .venv/Scripts/python -m discolab.cli trace   # who decided what, when
bash scripts/stop_lab.sh main
```

Requires `ANTHROPIC_API_KEY` in the environment (never written to disk by the lab).
On Linux/macOS use `.venv/bin/python`. Windows notes are in `scripts/start_lab.sh`.

## Python SDK and language bridge

The package exports a stable Python facade:

```python
from discolab import DiscoveryLab, Experiment

lab = DiscoveryLab("lab_home/example", actor="researcher")
lab.initialize()
```

Rust and Julia clients use the same validated transitions through
`python -m discolab.rpc --root <lab>`. The protocol and language packages live
under [`../sdk`](../sdk/README.md). The RPC bridge is a command interface for
SDKs; `discolab.bridge` is the separate read-only HTTP/SSE projection for the UI.

## Results

_Filled from the ledger and artifacts after each recorded run; see below._
