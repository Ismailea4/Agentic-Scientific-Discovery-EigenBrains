"""Deterministic experiment selection and belief update.

Utility (EigenBrains constrained-utility form, re-targeted at experiments):
    U(E) = EIG(E) - eta * wall_seconds(E) - lambda * heldout_landscapes(E)
Hard constraints are checked first; an infeasible experiment is never ranked.

EIG: each tested hypothesis h has prior q. The experiment yields a verdict
o in {supported, inconclusive, refuted} with pre-registered likelihoods
    P(sup|H1)=pi   P(ref|H1)=r1          P(inc|H1)=1-pi-r1
    P(sup|H0)=s0   P(ref|H0)=pi          P(inc|H0)=1-s0-pi
where pi = Phi(delta*sqrt(n) - z_{1-alpha/2}) is the design's power for the
assumed standardised effect delta (the latest measured effect in the same
hypothesis family once one exists). EIG = H(q) - E_o[H(q|o)] in bits.
The same table turns an observed verdict into a posterior, so the planner's
expectations and the belief update are consistent.
"""

from __future__ import annotations

import math

from scipy.stats import norm

from .experiments import ExperimentSpec, estimate_cost, run_plan, validate_spec
from .prereg import initial_prior

VERDICTS = ("supported", "inconclusive", "refuted")


def entropy_bits(q: float) -> float:
    if q <= 0.0 or q >= 1.0:
        return 0.0
    return -(q * math.log2(q) + (1 - q) * math.log2(1 - q))


def power(n_units: int, std_effect: float, alpha: float) -> float:
    z = norm.ppf(1 - alpha / 2)
    return float(min(0.97, max(0.03, norm.cdf(abs(std_effect) * math.sqrt(max(n_units, 1)) - z))))


def likelihood_table(pi: float, lik: dict) -> dict[str, tuple[float, float]]:
    """verdict -> (P(o|H1), P(o|H0))."""
    r1, s0 = lik["refuted_given_H1"], lik["supported_given_H0"]
    return {
        "supported": (pi, s0),
        "refuted": (r1, pi),
        "inconclusive": (max(1e-6, 1 - pi - r1), max(1e-6, 1 - s0 - pi)),
    }


def posterior(q: float, verdict: str, table) -> float:
    l1, l0 = table[verdict]
    return q * l1 / (q * l1 + (1 - q) * l0)


def eig_bits(q: float, table) -> float:
    total = 0.0
    for o in VERDICTS:
        l1, l0 = table[o]
        po = q * l1 + (1 - q) * l0
        total += po * entropy_bits(posterior(q, o, table))
    return entropy_bits(q) - total


def current_prior(hid: str, hyps: dict[str, dict]) -> float:
    h = hyps[hid]
    if h.get("history"):
        return float(h["posterior"])
    if h.get("prior_rule"):
        return initial_prior(h, hyps)
    return float(h["posterior"])


def assumed_effect(hid: str, hyps: dict[str, dict], policy: dict) -> tuple[float, str]:
    h = hyps[hid]
    if "latest_effect" in h:
        return float(h["latest_effect"]), f"measured on {hid}"
    fam = [x for x in hyps.values() if x["family"] == h["family"] and "latest_effect" in x]
    if fam:
        last = max(fam, key=lambda x: x["history"][-1]["seq"])
        return float(last["latest_effect"]), f"latest measured in family '{h['family']}' ({last['id']})"
    return float(policy["assumed_standardised_effect"]), "pre-registered default"


def n_units(spec: ExperimentSpec, prereg: dict, derived: dict) -> int:
    if spec.kind == "prediction":
        return spec.n_seeds * len(prereg["prediction_study"]["data_policies"]) * len(spec.landscapes)
    return spec.n_seeds * len(spec.landscapes)


def score_candidates(state: dict, prereg: dict) -> list[dict]:
    pol = prereg["planner_policy"]
    alpha = prereg["decision_rules"]["alpha"]
    hyps = state["hypotheses"]
    remaining = state["compute_budget_sec"] - state["compute_used_sec"]
    rows = []
    for eid, cand in state["candidates"].items():
        if cand["status"] not in ("proposed", "scored"):
            continue
        spec = ExperimentSpec(**cand["spec"])
        derived = validate_spec(spec, prereg, hyps)
        plan = run_plan(spec, prereg, derived, state["calibration"])
        cost = estimate_cost(plan, state["sec_per_generation"])
        violations = []
        if cost["wall_seconds"] > remaining:
            violations.append(f"estimated {cost['wall_seconds']}s exceeds remaining budget {remaining:.0f}s")
        if derived["stage"] == "confirmatory":
            for hid in spec.hypotheses:
                dev_done = any(e.get("stage") == "development" for e in hyps[hid]["history"])
                if not dev_done:
                    violations.append(f"{hid} has no completed development-stage test (confirmatory data protected)")
        per_h, eig = {}, 0.0
        for hid in spec.hypotheses:
            q = current_prior(hid, hyps)
            delta, src = assumed_effect(hid, hyps, pol)
            pi = power(n_units(spec, prereg, derived), delta, alpha)
            e = eig_bits(q, likelihood_table(pi, pol["likelihoods"]))
            per_h[hid] = {"prior": round(q, 4), "assumed_effect": round(delta, 4), "effect_source": src,
                          "power": round(pi, 4), "eig_bits": round(e, 4)}
            eig += e
        heldout = len(spec.landscapes) if derived["stage"] == "confirmatory" else 0
        cost_pen = pol["eta_bits_per_second"] * cost["wall_seconds"]
        held_pen = pol["lambda_heldout_bits"] * heldout
        rows.append({
            "id": eid, "title": spec.title, "kind": spec.kind, "stage": derived["stage"],
            "hypotheses": per_h, "eig_bits": round(eig, 4), "cost": cost, "plan": plan,
            "cost_penalty_bits": round(cost_pen, 4), "heldout_penalty_bits": round(held_pen, 4),
            "utility": round(eig - cost_pen - held_pen, 4), "feasible": not violations, "violations": violations,
        })
    rows.sort(key=lambda r: (not r["feasible"], -r["utility"]))
    return rows


def belief_updates(state: dict, prereg: dict, exp_id: str) -> list[dict]:
    """Posterior updates implied by an analysed experiment's verdicts (+ coupled priors)."""
    pol = prereg["planner_policy"]
    rules = prereg["decision_rules"]
    hyps = state["hypotheses"]
    cand = state["candidates"][exp_id]
    score = cand.get("score") or {}
    verdicts = cand["result"]["verdicts"]
    updates = []
    new_post = {}
    for hid, v in verdicts.items():
        q = current_prior(hid, hyps)
        pi = score.get("hypotheses", {}).get(hid, {}).get("power")
        if pi is None:
            raise ValueError(f"{exp_id} has no scored power for {hid}")
        p = posterior(q, v["verdict"], likelihood_table(pi, pol["likelihoods"]))
        new_post[hid] = p
        updates.append({"id": hid, "experiment": exp_id, "verdict": v["verdict"], "prior": q, "power": pi,
                        "posterior": p, "status": _status(p, rules), "effect": v["standardised_effect"],
                        "stage": v["stage"], "measure": v["measure"], "interval": v["effect"]})
    # propagate pre-registered prior couplings to hypotheses not yet tested directly
    for hid, h in hyps.items():
        rule = h.get("prior_rule")
        if rule and not any("experiment" in e and e.get("experiment") for e in h["history"]) \
                and rule["depends_on"] in new_post:
            q = new_post[rule["depends_on"]]
            p = q * rule["if_true"] + (1 - q) * rule["if_false"]
            updates.append({"id": hid, "experiment": None, "verdict": None, "posterior": p,
                            "status": _status(p, rules),
                            "reason": f"pre-registered prior coupling to {rule['depends_on']}"})
    return updates


SUPPORTED_AT, REFUTED_AT = 0.9, 0.1  # prereg decision_rules.hypothesis_status


def _status(p: float, rules: dict) -> str:
    return "supported" if p >= SUPPORTED_AT else "refuted" if p <= REFUTED_AT else "open"
