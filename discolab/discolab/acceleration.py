"""Acceleration study (acceleration_protocol.yaml): planner vs conventional sweep.

    python -m discolab.acceleration --out results/acceleration [--replicates 5]

Each strategy runs in its own lab directory with a derived pre-registration
that differs from prereg.yaml only in its seed blocks and compute budget, so
the ledger of every strategy run is a complete, replayable record. No LLM is
involved: this measures the deterministic selection machinery.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import yaml

from . import lab
from .ledger import Ledger
from .prereg import PREREG_PATH, load_prereg
from .stats import bootstrap_mean_diff

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_PATH = ROOT / "acceleration_protocol.yaml"
ACTOR = "acceleration-harness"
MIN_UTILITY = 0.01
SIZES = (6, 12, 24)
SWEEP_N = 24
REFERENCE_N = 48
FULL_BASELINES = ["B0_fixed", "B1_stall", "B2_entropy", "B4a_hypermutation", "B4b_immigrants"]


def menu_spec(hid: str, h: dict, n: int, prereg: dict) -> dict:
    dev = prereg["landscapes"]["development"]
    if h["family"] == "prediction":
        base = h.get("baseline_feature_set") or prereg["prediction_study"]["baseline_features"]
        fsets = list(dict.fromkeys(["fitness", base, h["feature_set"]]))
        return {"kind": "prediction", "title": f"{hid} development test, {n} seeds",
                "rationale": f"acceleration study design for {hid}", "hypotheses": [hid], "landscapes": dev,
                "n_seeds": n, "feature_sets": fsets}
    comp = h.get("comparator") or "best_baseline"
    ctrls = FULL_BASELINES + [h["controller"]] if comp == "best_baseline" else ["B0_fixed", h["controller"], comp]
    return {"kind": "control", "title": f"{hid} development test, {n} seeds",
            "rationale": f"acceleration study design for {hid}", "hypotheses": [hid], "landscapes": dev,
            "n_seeds": n, "controllers": list(dict.fromkeys(ctrls))}


def derived_prereg(dest: Path, dev_start: int, budget: float) -> Path:
    data = yaml.safe_load(PREREG_PATH.read_text(encoding="utf-8"))
    data["seeds"]["development"] = [dev_start, dev_start + 9999]
    data["seeds"]["experiment_offset"] = 0
    data["planner_policy"]["compute_budget_seconds"] = budget
    data["derived_for"] = "acceleration study (seeds and budget only differ from prereg.yaml)"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return dest


def _run_one(root: Path, eid: str, justification: str) -> None:
    lab.select_experiment(eid, justification, ACTOR, root)
    lab.run_selected_experiment(ACTOR, root)
    lab.record_analysis(eid, "automated acceleration-study analysis (no agent)", [], ACTOR, root)


def run_strategy(root: Path, strategy: str, hyps: list[str], dev_start: int, budget: float) -> dict:
    os.environ["DISCOLAB_PREREG"] = str(derived_prereg(root / "prereg_derived.yaml", dev_start, budget))
    try:
        lab.init_lab(root, actor=ACTOR)
        pr = load_prereg()
        state = Ledger(root).state()
        t0 = time.perf_counter()
        if strategy == "sweep":
            ids = [lab.propose_experiment(menu_spec(h, state["hypotheses"][h], SWEEP_N, pr), ACTOR, root)["id"]
                   for h in hyps]
            for eid in ids:
                lab.score_experiments(ACTOR, root)
                _run_one(root, eid, "fixed sweep order")
        elif strategy == "reference":
            for h in hyps:
                eid = lab.propose_experiment(menu_spec(h, state["hypotheses"][h], REFERENCE_N, pr), ACTOR, root)["id"]
                lab.score_experiments(ACTOR, root)
                _run_one(root, eid, "reference")
        elif strategy == "lab":
            for h in hyps:
                for n in SIZES:
                    lab.propose_experiment(menu_spec(h, state["hypotheses"][h], n, pr), ACTOR, root)
            while True:
                st = Ledger(root).state()
                if all(st["hypotheses"][h]["status"] != "open" for h in hyps):
                    break
                scored = lab.score_experiments(ACTOR, root)
                best = next((r for r in scored["scores"] if r["feasible"]), None)
                if best is None or best["utility"] < MIN_UTILITY:
                    break
                _run_one(root, best["id"], "planner argmax")
        else:
            raise ValueError(strategy)
        wall = time.perf_counter() - t0
    finally:
        os.environ.pop("DISCOLAB_PREREG", None)
    st = Ledger(root).state()
    done = [c for c in st["candidates"].values() if c["status"] == "analyzed"]
    return {
        "strategy": strategy,
        "experiments": [{"id": c["id"], "title": c["spec"]["title"],
                         "generations": c["derived"]["plan"]["weighted_generations"],
                         "runtime_sec": c["runtime_sec"],
                         "verdicts": {h: v["verdict"] for h, v in c["result"]["verdicts"].items()}} for c in done],
        "generations": float(sum(c["derived"]["plan"]["weighted_generations"] for c in done)),
        "wall_seconds": wall,
        "status": {h: st["hypotheses"][h]["status"] for h in hyps},
        "posterior": {h: round(st["hypotheses"][h]["posterior"], 4) for h in hyps},
        "verdicts": {h: [e["verdict"] for e in st["hypotheses"][h]["history"] if e.get("experiment")]
                     for h in hyps},
    }


MATCH = {("supported", "supported"), ("refuted", "refuted"), ("open", "inconclusive")}


def agreement(result: dict, reference: dict) -> dict:
    per = {h: (result["status"][h], reference["verdicts"][h][-1]) for h in result["status"]}
    return {"agree": sum((s, r) in MATCH for s, r in per.values()), "of": len(per),
            "disagreements": {h: {"status": s, "reference": r} for h, (s, r) in per.items() if (s, r) not in MATCH}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/acceleration")
    ap.add_argument("--replicates", type=int, default=None)
    args = ap.parse_args()
    proto = yaml.safe_load(PROTOCOL_PATH.read_text(encoding="utf-8"))
    hyps, budget = proto["hypotheses"], float(proto["budget_seconds"])
    reps = args.replicates or proto["replicates"]
    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} exists; study records are not overwritten")
    out.mkdir(parents=True)
    print("reference ...", flush=True)
    ref = run_strategy(out / "reference", "reference", hyps, 300000, budget)
    rows = []
    for r in range(reps):
        sweep = run_strategy(out / f"rep{r}" / "sweep", "sweep", hyps, 100000 + 20000 * r, budget)
        labr = run_strategy(out / f"rep{r}" / "lab", "lab", hyps, 110000 + 20000 * r, budget)
        row = {"replicate": r, "sweep": sweep, "lab": labr,
               "ratio_generations": sweep["generations"] / labr["generations"],
               "ratio_wall": sweep["wall_seconds"] / labr["wall_seconds"],
               "agreement_sweep": agreement(sweep, ref), "agreement_lab": agreement(labr, ref)}
        rows.append(row)
        print(f"rep {r}: sweep {sweep['generations']:.0f} gens, lab {labr['generations']:.0f} gens, "
              f"ratio {row['ratio_generations']:.2f}; agreement sweep {row['agreement_sweep']['agree']}/{len(hyps)}, "
              f"lab {row['agreement_lab']['agree']}/{len(hyps)}", flush=True)
    ratios = np.array([r["ratio_generations"] for r in rows])
    summary = {
        "protocol": proto, "reference": ref, "replicates": rows,
        "ratio_generations": {"mean": float(ratios.mean()), "per_replicate": ratios.tolist(),
                              "ci95": (bootstrap_mean_diff(ratios).to_dict() if len(ratios) > 1 else None)},
        "agreement": {"sweep": [r["agreement_sweep"]["agree"] for r in rows],
                      "lab": [r["agreement_lab"]["agree"] for r in rows], "of": len(hyps)},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("ratio_generations", "agreement")}, indent=2))


if __name__ == "__main__":
    main()
