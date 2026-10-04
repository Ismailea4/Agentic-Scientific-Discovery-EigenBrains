"""Compact, agent- and UI-friendly projections of the research state.

Full detail stays in the ledger and the artifact directories; these views
keep tool responses small enough for an LLM context window.
"""

from __future__ import annotations


def _r(x, n=4):
    return None if x is None else round(float(x), n)


def _ci(d: dict) -> dict:
    return {"estimate": _r(d["estimate"]), "ci95": [_r(d["low"]), _r(d["high"])]}


def state_summary(s: dict) -> dict:
    hyps = []
    for h in s["hypotheses"].values():
        tests = [e for e in h["history"] if e.get("experiment")]
        hyps.append({
            "id": h["id"], "family": h["family"], "origin": h.get("origin", "prereg"),
            "statement": h["statement"], "status": h["status"], "posterior": _r(h["posterior"], 3),
            "n_direct_tests": len(tests),
            "last": ({"experiment": tests[-1]["experiment"], "verdict": tests[-1]["verdict"],
                      "stage": tests[-1].get("stage")} if tests else None),
        })
    cands = []
    for c in s["candidates"].values():
        sc = c.get("score") or {}
        cands.append({
            "id": c["id"], "title": c["spec"]["title"], "kind": c["spec"]["kind"],
            "stage": c.get("derived", {}).get("stage"), "hypotheses": c["spec"]["hypotheses"],
            "status": c["status"], "proposed_by": c["proposed_by"],
            "utility": sc.get("utility"), "eig_bits": sc.get("eig_bits"),
            "est_wall_seconds": (sc.get("cost") or {}).get("wall_seconds"),
            "feasible": sc.get("feasible"), "violations": sc.get("violations"),
        })
    return {
        "question": s["question"],
        "compute_seconds": {"used": _r(s["compute_used_sec"], 1), "budget": s["compute_budget_sec"]},
        "hypotheses": hyps,
        "evidence": [{"openalex_id": e["openalex_id"], "title": e.get("title"), "year": e.get("year"),
                      "relation": e.get("relation"), "hypothesis_id": e.get("hypothesis_id"),
                      "claim": e.get("claim")} for e in s["evidence"]],
        "candidates": cands,
        "selected": s["selected"],
        "latest_scoring_round": ({"round": s["scoring_rounds"][-1]["round"],
                                  "argmax": s["scoring_rounds"][-1]["argmax"]} if s["scoring_rounds"] else None),
        "next_decision": s["next_decision"],
    }


def result_summary(cand: dict) -> dict:
    res = cand.get("result")
    if res is None:
        return {"id": cand["id"], "status": cand["status"], "result": None, "error": cand.get("error")}
    out = {"id": cand["id"], "title": cand["spec"]["title"], "kind": res["kind"], "stage": res["stage"],
           "runtime_sec": _r(cand.get("runtime_sec"), 1), "artifacts": cand.get("artifacts"),
           "verdicts": {h: {"verdict": v["verdict"], "measure": v["measure"], "effect": _ci(v["effect"]),
                            "standardised_effect": _r(v["standardised_effect"], 3), "n_units": v["n_units"]}
                        for h, v in res["verdicts"].items()}}
    if res["kind"] == "prediction":
        out.update({
            "design": res["design"], "n_test_runs": res["n_test_runs"], "n_test_points": res["n_test_points"],
            "stagnation_prevalence": _r(res["test_prevalence"], 3),
            "auroc": {fs: _ci(v) for fs, v in res["auroc"].items()},
            "delta_auroc_vs_fitness": {fs: _ci(v["delta_auroc"]) for fs, v in res["comparisons"].items()},
            "hypothesis_contrasts": {k: _ci(v["delta_auroc"]) for k, v in res.get("pair_comparisons", {}).items()},
            "brier": {fs: _r(v) for fs, v in res["brier"].items()},
        })
    else:
        out.update({
            "eps": {k: _r(v) for k, v in res["eps"].items()},
            "per_controller": {c: {"rmst_gens": _r(v["rmst_gens_mean"], 2),
                                   "recovery_rate": _ci(v["recovery_rate"]),
                                   "cvar90_recovery_gens": _r(v["cvar90_recovery_gens"], 2),
                                   "mean_p_mut": _r(v["mean_p_mut"], 4)}
                               for c, v in res["per_controller"].items()},
            "vs_B0": {c: {"delta_rmst_gens": _ci(v["delta_rmst_gens"]),
                          "delta_recovery_rate": _ci(v["delta_recovery_rate"]),
                          "holm_reject": v.get("holm_reject"), "rescue_damage": v["rescue_damage"],
                          "mcnemar_p_descriptive": _r(v["mcnemar_p_descriptive"])}
                      for c, v in res["vs_B0"].items()},
            "hypothesis_contrasts": {h: {"controller": v["controller"], "comparator": v["comparator"],
                                         "delta_rmst_gens": _ci(v["delta_rmst_gens"])}
                                     for h, v in res["contrasts"].items()},
            "risk_models": {k: {"feature_set": v["feature_set"], "n_fit_runs": v["n_fit_runs"]}
                            for k, v in (res.get("risk_models") or {}).items()},
        })
    if cand.get("analysis"):
        a = cand["analysis"]
        out["analysis"] = {"by": a["by"], "interpretation": a["interpretation"],
                           "threats_to_validity": a["threats_to_validity"]}
    return out
