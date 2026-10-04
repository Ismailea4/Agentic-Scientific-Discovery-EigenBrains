"""Lab operations: the only code paths that write the research ledger.

Each function corresponds to one scientific transition and is exposed to the
Omnigent agents as an MCP tool (see mcp_server.py). Agents contribute text
(rationales, interpretations, justifications); every number comes from here.
"""

from __future__ import annotations

import os
from pathlib import Path

from .experiments import ExperimentSpec, estimate_cost, is_known_controller, measure_sec_per_generation, \
    run_experiment, run_plan, validate_spec
from .features import FEATURE_SETS
from .ledger import Ledger, LedgerError, public_state
from .planner import belief_updates, score_candidates
from .prereg import load_prereg


def lab_root() -> Path:
    root = os.environ.get("DISCOLAB_HOME")
    if not root:
        raise RuntimeError("DISCOLAB_HOME is not set; it must point at the lab's working directory")
    return Path(root)


def _ledger(root: Path | None = None) -> Ledger:
    return Ledger(root or lab_root())


def init_lab(root: Path | None = None, actor: str = "operator") -> dict:
    led = _ledger(root)
    if led.events():
        raise LedgerError("this lab directory already has a ledger; use a fresh DISCOLAB_HOME")
    pr = load_prereg()
    hyps = []
    for h in pr["hypotheses"]:
        entry = {k: v for k, v in h.items()}
        entry.setdefault("prior", 0.5)
        entry.setdefault("origin", "prereg")
        hyps.append(entry)
    led.append("lab_initialized", {
        "question": " ".join(pr["question"].split()),
        "prereg_sha256": pr["_sha256"],
        "hypotheses": hyps,
        "compute_budget_sec": pr["planner_policy"]["compute_budget_seconds"],
        "sec_per_generation": measure_sec_per_generation(),
    }, actor)
    return get_state(root)


def get_state(root: Path | None = None) -> dict:
    return public_state(_ledger(root).state())


def propose_experiment(spec: dict, actor: str, root: Path | None = None) -> dict:
    led = _ledger(root)
    state = led.state()
    pr = load_prereg()
    s = ExperimentSpec(**spec)
    derived = validate_spec(s, pr, state["hypotheses"])
    plan = run_plan(s, pr, derived, state["calibration"])
    eid = f"E{state['experiment_counter'] + 1}"
    led.append("experiment_proposed", {"id": eid, "spec": s.model_dump(),
                                       "derived": {**derived, "plan": plan,
                                                   "cost": estimate_cost(plan, state["sec_per_generation"])}},
               actor)
    return {"id": eid, "stage": derived["stage"], "plan": plan}


def score_experiments(actor: str, root: Path | None = None) -> dict:
    led = _ledger(root)
    rows = score_candidates(led.state(), load_prereg())
    if not rows:
        raise LedgerError("no open candidate experiments to score")
    feasible = [r for r in rows if r["feasible"]]
    led.append("experiments_scored", {"scores": rows, "argmax": feasible[0]["id"] if feasible else None}, actor)
    return {"argmax": feasible[0]["id"] if feasible else None, "scores": rows}


def select_experiment(exp_id: str, justification: str, actor: str, root: Path | None = None) -> dict:
    led = _ledger(root)
    state = led.state()
    if not state["scoring_rounds"]:
        raise LedgerError("score candidates before selecting")
    argmax = state["scoring_rounds"][-1]["argmax"]
    led.append("experiment_selected", {"id": exp_id, "argmax": argmax, "followed_argmax": exp_id == argmax,
                                       "justification": justification}, actor)
    return {"selected": exp_id, "argmax": argmax, "followed_argmax": exp_id == argmax}


def run_selected_experiment(actor: str, root: Path | None = None) -> dict:
    led = _ledger(root)
    state = led.state()
    eid = state["selected"]
    if eid is None:
        raise LedgerError("no experiment is selected")
    pr = load_prereg()
    cand = state["candidates"][eid]
    spec = ExperimentSpec(**cand["spec"])
    derived = validate_spec(spec, pr, state["hypotheses"])
    ordinal = int(eid[1:])
    try:
        out = run_experiment(spec, eid, ordinal, led.root, pr, derived, state["calibration"], state["hypotheses"])
    except Exception as exc:
        led.append("experiment_failed", {"id": eid, "error": f"{type(exc).__name__}: {exc}"}, actor)
        raise
    summary = {k: v for k, v in out["summary"].items() if k != "models"}
    # store artifact locations relative to the lab root so the record is portable
    artifacts = Path(os.path.relpath(out["artifacts"], led.root)).as_posix()
    led.append("experiment_completed", {"id": eid, "summary": out["summary"], "artifacts": artifacts,
                                        "runtime_sec": out["runtime_sec"], "calibration": out["calibration"]}, actor)
    return {"id": eid, "runtime_sec": round(out["runtime_sec"], 2), "artifacts": artifacts,
            "summary": summary}


def abort_experiment(exp_id: str, reason: str, actor: str, root: Path | None = None) -> dict:
    """Release a selected experiment whose run was interrupted (e.g. the process was killed)."""
    _ledger(root).append("experiment_failed", {"id": exp_id, "error": f"aborted: {reason}", "aborted": True}, actor)
    return {"aborted": exp_id}


def record_analysis(exp_id: str, interpretation: str, threats_to_validity: list[str], actor: str,
                    root: Path | None = None) -> dict:
    """Critic's interpretation + the deterministic posterior updates it triggers."""
    led = _ledger(root)
    led.append("analysis_recorded", {"id": exp_id, "interpretation": interpretation,
                                     "threats_to_validity": threats_to_validity}, actor)
    state = led.state()
    updates = belief_updates(state, load_prereg(), exp_id)
    for u in updates:
        led.append("hypothesis_updated", u, "discolab.planner")
    return {"updates": updates}


def record_decision(decision: str, rationale: str, next_experiment: str | None, actor: str,
                    root: Path | None = None) -> dict:
    led = _ledger(root)
    led.append("decision_recorded", {"decision": decision, "rationale": rationale,
                                     "next_experiment": next_experiment}, actor)
    return {"recorded": True}


def register_hypothesis(hid: str, statement: str, h0: str, family: str, feature_set: str | None,
                        controller: str | None, actor: str, root: Path | None = None,
                        baseline_feature_set: str | None = None, comparator: str | None = None) -> dict:
    """Register an agent-generated hypothesis; it must be testable by the lab as written."""
    if family == "prediction":
        base = baseline_feature_set or load_prereg()["prediction_study"]["baseline_features"]
        for fs in (feature_set, base):
            if fs not in FEATURE_SETS:
                raise ValueError(f"unknown feature set {fs!r}; known: {sorted(FEATURE_SETS)}")
        if feature_set == base:
            raise ValueError("feature_set and its comparison baseline must differ")
        payload = {"feature_set": feature_set, "baseline_feature_set": base}
    elif family == "control":
        comp = comparator or "best_baseline"
        if not is_known_controller(controller or ""):
            raise ValueError(f"unknown controller {controller!r}")
        if comp != "best_baseline" and not is_known_controller(comp):
            raise ValueError(f"unknown comparator {comp!r}")
        payload = {"controller": controller, "comparator": comp}
    else:
        raise ValueError("family must be 'prediction' or 'control'")
    payload = {"id": hid, "statement": statement, "h0": h0, "family": family, "prior": 0.5, **payload}
    _ledger(root).append("hypothesis_registered", payload, actor)
    return payload
