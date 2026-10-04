"""Deterministic experiment selection and belief update (prereg v2).

Utility (EigenBrains constrained-utility form, re-targeted at experiments):
    U(E) = EIG(E) - eta * wall_seconds(E) - lambda * heldout_landscapes(E)
Hard constraints are checked first; an infeasible experiment is never ranked.

Outcome model. For a hypothesis tested on n independent units, the estimate of
the standardised effect is ~ N(delta, 1/n). With z = z_{1-alpha/2} and the
smallest effect of interest s (standardised):
    supported     <=> est - z/sqrt(n) > 0        P = Phi(delta*sqrt(n) - z)
    refuted       <=> est + z/sqrt(n) < s        P = Phi((s - delta)*sqrt(n) - z)
    inconclusive  otherwise
H1 uses delta = assumed effect (> 0); H0 uses delta = 0. EIG is the mutual
information (bits) between the hypothesis and this three-way verdict, and the
same table converts an observed verdict into the posterior, so planning
expectations and belief updates agree. Under this model an inconclusive
verdict from a well-powered design is evidence *against* H1 (prereg v1's
approximation P(refuted|H0) = power made it look like evidence for H1).
"""

from __future__ import annotations

import math
import statistics
from itertools import product

import numpy as np
from scipy.stats import norm

from .experiments import ExperimentSpec, estimate_cost, run_plan, validate_spec
from .prereg import initial_prior

VERDICTS = ("supported", "inconclusive", "refuted")
SUPPORTED_AT, REFUTED_AT = 0.9, 0.1  # prereg decision_rules.hypothesis_status
EPS = 1e-6


def entropy_bits(q: float) -> float:
    if q <= 0.0 or q >= 1.0:
        return 0.0
    return -(q * math.log2(q) + (1 - q) * math.log2(1 - q))


def outcome_probs(delta: float, n: int, sesoi: float, alpha: float) -> dict[str, float]:
    z = norm.ppf(1 - alpha / 2)
    rn = math.sqrt(max(n, 1))
    sup = float(norm.cdf(delta * rn - z))
    ref = float(norm.cdf((sesoi - delta) * rn - z))
    inc = 1.0 - sup - ref
    probs = {"supported": max(sup, EPS), "refuted": max(ref, EPS), "inconclusive": max(inc, EPS)}
    total = sum(probs.values())
    return {k: v / total for k, v in probs.items()}


# Gauss-Legendre nodes mapped to (0, 1) for the half-normal mixture over effect sizes (prereg v3).
_GL_X, _GL_W = np.polynomial.legendre.leggauss(40)
_QUAD_U, _QUAD_W = (_GL_X + 1.0) / 2.0, _GL_W / 2.0


def likelihood_table(delta1: float, n: int, sesoi: float, alpha: float) -> dict[str, tuple[float, float]]:
    """verdict -> (P(o|H1), P(o|H0)).

    H1 is composite (prereg v3): a practically meaningful effect of uncertain
    size, delta = SESOI + HalfNormal(scale = assumed effect). P(o|H1) averages
    the outcome probabilities over that prior, so an inconclusive verdict
    counts against H1 in proportion to the design's sample size without
    deciding it, and a refuted verdict (CI below the SESOI) is decisive.
    """
    h1 = {o: 0.0 for o in VERDICTS}
    for u, w in zip(_QUAD_U, _QUAD_W):
        # inverse-CDF quadrature: half-normal quantile = scale * Phi^{-1}((1 + u) / 2)
        delta = sesoi + delta1 * float(norm.ppf(0.5 + 0.5 * u))
        p = outcome_probs(delta, n, sesoi, alpha)
        for o in VERDICTS:
            h1[o] += w * p[o]
    h0 = outcome_probs(0.0, n, sesoi, alpha)
    return {o: (h1[o], h0[o]) for o in VERDICTS}


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


def power(n_units: int, std_effect: float, alpha: float) -> float:
    """P(supported | true standardised effect) — kept for reporting."""
    return float(norm.cdf(abs(std_effect) * math.sqrt(max(n_units, 1)) - norm.ppf(1 - alpha / 2)))


def current_prior(hid: str, hyps: dict[str, dict]) -> float:
    h = hyps[hid]
    if h.get("history"):
        return float(h["posterior"])
    if h.get("prior_rule"):
        return initial_prior(h, hyps)
    return float(h["posterior"])


def _measured(h: dict) -> list[dict]:
    return [e for e in h.get("history", []) if e.get("experiment") and e.get("effect") is not None]


def assumed_effect(hid: str, hyps: dict[str, dict], policy: dict) -> tuple[float, str]:
    """Effect size H1 is assumed to have when planning a test of `hid`.

    Own latest measurement if any, else the mean of the latest measurements of
    every hypothesis in the same family (order-independent), else the
    pre-registered default. Floored so H1 always claims a positive effect.
    """
    floor = policy["min_assumed_standardised_effect"]
    own = _measured(hyps[hid])
    if own:
        return max(float(own[-1]["effect"]), floor), f"latest measurement of {hid}"
    fam = [(_measured(x)[-1]["effect"], x["id"]) for x in hyps.values()
           if x["family"] == hyps[hid]["family"] and _measured(x)]
    if fam:
        mean = statistics.fmean(float(e) for e, _ in fam)
        return max(mean, floor), "mean of family measurements (" + ", ".join(i for _, i in fam) + ")"
    return float(policy["assumed_standardised_effect"]), "pre-registered default"


def sesoi_standardised(hid: str, hyps: dict[str, dict], prereg: dict) -> tuple[float, str]:
    """Smallest effect of interest on the standardised scale.

    Converted from the raw SESOI with the per-unit SD implied by measurements
    in the same family (raw estimate / standardised estimate), else the
    pre-registered default.
    """
    pol = prereg["planner_policy"]
    fam = hyps[hid]["family"]
    raw_sesoi = prereg["decision_rules"]["smallest_effect_of_interest"][
        "prediction_delta_auroc" if fam == "prediction" else "control_rmst_generations"]
    sds = []
    for x in hyps.values():
        if x["family"] != fam:
            continue
        for e in _measured(x):
            raw = (e.get("interval") or {}).get("estimate")
            std = e.get("effect")
            if raw is not None and std and abs(std) > 1e-9 and abs(raw) > 1e-12:
                sds.append(abs(raw / std))
    if sds:
        return raw_sesoi / statistics.median(sds), f"raw SESOI / measured per-unit SD (n={len(sds)})"
    return float(pol["default_sesoi_standardised"]), "pre-registered default"


def n_units(spec: ExperimentSpec, prereg: dict) -> int:
    if spec.kind == "prediction":
        return spec.n_seeds * len(prereg["prediction_study"]["data_policies"]) * len(spec.landscapes)
    return spec.n_seeds * len(spec.landscapes)


def calibrated_sec_per_generation(state: dict) -> tuple[float, str]:
    """Wall seconds per weighted generation, learned from completed runs."""
    obs = []
    for c in state["candidates"].values():
        plan = (c.get("derived") or {}).get("plan")
        if c.get("runtime_sec") and plan and plan.get("weighted_generations"):
            obs.append(c["runtime_sec"] / plan["weighted_generations"])
    if obs:
        return statistics.median(obs), f"calibrated from {len(obs)} completed run(s)"
    return None, "benchmark"


def score_candidates(state: dict, prereg: dict) -> list[dict]:
    pol = prereg["planner_policy"]
    alpha = prereg["decision_rules"]["alpha"]
    hyps = state["hypotheses"]
    remaining = state["compute_budget_sec"] - state["compute_used_sec"]
    wall_per_gen, cost_source = calibrated_sec_per_generation(state)
    rows = []
    for eid, cand in state["candidates"].items():
        if cand["status"] not in ("proposed", "scored"):
            continue
        spec = ExperimentSpec(**cand["spec"])
        derived = validate_spec(spec, prereg, hyps)
        plan = run_plan(spec, prereg, derived, state["calibration"])
        if wall_per_gen is None:
            cost = estimate_cost(plan, state["sec_per_generation"])
        else:
            wall = round(plan["weighted_generations"] * wall_per_gen, 2)
            cost = {"cpu_seconds": None, "wall_seconds": wall}
        cost["model"] = cost_source
        violations = []
        if cost["wall_seconds"] > remaining:
            violations.append(f"estimated {cost['wall_seconds']}s exceeds remaining budget {remaining:.0f}s")
        if derived["stage"] == "confirmatory":
            for hid in spec.hypotheses:
                dev_done = any(e.get("stage") == "development" for e in hyps[hid]["history"])
                if not dev_done:
                    violations.append(f"{hid} has no completed development-stage test (confirmatory data protected)")
        per_h, eig = {}, 0.0
        n = n_units(spec, prereg)
        for hid in spec.hypotheses:
            q = current_prior(hid, hyps)
            delta, src = assumed_effect(hid, hyps, pol)
            s, s_src = sesoi_standardised(hid, hyps, prereg)
            table = likelihood_table(delta, n, s, alpha)
            e = eig_bits(q, table)
            per_h[hid] = {"prior": round(q, 4), "assumed_effect": round(delta, 4), "effect_source": src,
                          "sesoi_std": round(s, 4), "sesoi_source": s_src, "n_units": n,
                          "p_supported_if_H1": round(table["supported"][0], 4),
                          "p_refuted_if_H0": round(table["refuted"][1], 4), "eig_bits": round(e, 4)}
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


# --------------------------------------------------------------- portfolio
def joint_information(q: float, tables: list) -> float:
    """I(h; O_1..O_m) in bits for m experiments testing the same hypothesis.

    Experiments run on disjoint seed blocks, so their verdicts are conditionally
    independent given the hypothesis. The joint information is then exact and
    is less than the sum of the individual EIGs whenever experiments overlap:
    the diminishing return is the redundancy (covariance) between them.
    """
    if not tables:
        return 0.0
    remaining = 0.0
    for combo in product(VERDICTS, repeat=len(tables)):
        l1 = math.prod(t[o][0] for t, o in zip(tables, combo))
        l0 = math.prod(t[o][1] for t, o in zip(tables, combo))
        po = q * l1 + (1 - q) * l0
        if po > 0:
            remaining += po * entropy_bits(q * l1 / po)
    return entropy_bits(q) - remaining


def research_portfolio(rows: list[dict], remaining_budget: float, prereg: dict) -> dict:
    """Greedy redundancy-aware selection of up to k experiments for one round.

    Value of a set = sum over hypotheses of the joint information of the
    experiments testing it, minus their cost and held-out penalties. Joint
    information is submodular here, so greedy marginal-gain selection has the
    standard (1 - 1/e) guarantee. Hard constraints apply: only feasible rows,
    within the remaining compute budget.
    """
    pol = prereg["planner_policy"]["portfolio"]
    alpha = prereg["decision_rules"]["alpha"]

    def value(chosen: list[dict]) -> tuple[float, float]:
        by_h: dict[str, tuple[float, list]] = {}
        for r in chosen:
            for hid, ph in r["hypotheses"].items():
                table = likelihood_table(ph["assumed_effect"], ph["n_units"], ph["sesoi_std"], alpha)
                by_h.setdefault(hid, (ph["prior"], []))[1].append(table)
        info = sum(joint_information(q, ts) for q, ts in by_h.values())
        penalty = sum(r["cost_penalty_bits"] + r["heldout_penalty_bits"] for r in chosen)
        return info, penalty

    chosen: list[dict] = []
    steps = []
    spent = 0.0
    while len(chosen) < pol["max_experiments"]:
        base_info, base_pen = value(chosen)
        best = None
        for r in rows:
            if not r["feasible"] or r in chosen or spent + r["cost"]["wall_seconds"] > remaining_budget:
                continue
            info, pen = value(chosen + [r])
            gain = (info - base_info) - (pen - base_pen)
            if best is None or gain > best[0]:
                best = (gain, r, info - base_info)
        if best is None or best[0] < pol["min_marginal_utility_bits"]:
            break
        chosen.append(best[1])
        spent += best[1]["cost"]["wall_seconds"]
        steps.append({"id": best[1]["id"], "marginal_utility_bits": round(best[0], 4),
                      "marginal_eig_bits": round(best[2], 4), "standalone_eig_bits": best[1]["eig_bits"]})
    info, _ = value(chosen)
    standalone = sum(r["eig_bits"] for r in chosen)
    return {"ids": [r["id"] for r in chosen], "steps": steps, "joint_eig_bits": round(info, 4),
            "sum_standalone_eig_bits": round(standalone, 4), "redundancy_bits": round(standalone - info, 4),
            "est_wall_seconds": round(spent, 2)}


def belief_updates(state: dict, prereg: dict, exp_id: str) -> list[dict]:
    """Posterior updates implied by an analysed experiment's verdicts (+ coupled priors)."""
    alpha = prereg["decision_rules"]["alpha"]
    hyps = state["hypotheses"]
    cand = state["candidates"][exp_id]
    score = cand.get("score") or {}
    verdicts = cand["result"]["verdicts"]
    updates = []
    new_post = {}
    for hid, v in verdicts.items():
        planned = score.get("hypotheses", {}).get(hid)
        if planned is None:
            raise ValueError(f"{exp_id} has no scored plan for {hid}")
        q = current_prior(hid, hyps)
        table = likelihood_table(planned["assumed_effect"], planned["n_units"], planned["sesoi_std"], alpha)
        p = posterior(q, v["verdict"], table)
        new_post[hid] = p
        verdicts_so_far = [e["verdict"] for e in hyps[hid]["history"] if e.get("experiment")] + [v["verdict"]]
        updates.append({"id": hid, "experiment": exp_id, "verdict": v["verdict"], "prior": q,
                        "likelihoods": {"H1": table[v["verdict"]][0], "H0": table[v["verdict"]][1]},
                        "posterior": p, "status": _status(p, verdicts_so_far), "effect": v["standardised_effect"],
                        "stage": v["stage"], "measure": v["measure"], "interval": v["effect"]})
    # propagate pre-registered prior couplings to hypotheses not yet tested directly;
    # a coupling moves the prior but can never decide a status (prereg v3)
    for hid, h in hyps.items():
        rule = h.get("prior_rule")
        if rule and not any(e.get("experiment") for e in h["history"]) and rule["depends_on"] in new_post:
            q = new_post[rule["depends_on"]]
            p = q * rule["if_true"] + (1 - q) * rule["if_false"]
            updates.append({"id": hid, "experiment": None, "verdict": None, "posterior": p, "status": "open",
                            "reason": f"pre-registered prior coupling to {rule['depends_on']} (untested)"})
    return updates


def _status(p: float, verdicts: list[str]) -> str:
    """Decided status needs both the posterior threshold and a matching direct verdict (prereg v3):
    a hypothesis is never called refuted on inconclusive evidence, nor supported without support."""
    if p >= SUPPORTED_AT and "supported" in verdicts:
        return "supported"
    if p <= REFUTED_AT and "refuted" in verdicts:
        return "refuted"
    return "open"
