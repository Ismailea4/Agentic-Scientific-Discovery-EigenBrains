"""Selective-escalation acceleration study (escalation_protocol.yaml).

    python -m discolab.escalation --out results/escalation [--replicates 5]

Transfers the EigenBrains benchmark's selective-escalation policy from model
calls to experiments: run a small design first and add seeds only when the
pre-registered verdict is inconclusive. Data are generated once per replicate
(every hypothesis at 24 seeds) plus a 48-seed reference; smaller looks are the
same analysis restricted to the first k seeds, so looks are nested exactly as
in a real sequential design. No LLM is involved.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import yaml

from .acceleration import run_strategy
from .experiments import CALIBRATION_SEEDS, ExperimentSpec, _verdict, run_plan
from .features import FEATURE_SETS
from .ga import Trace
from .ledger import Ledger
from .predict import evaluate_feature_sets, run_points
from .prereg import PREREG_PATH, load_prereg
from .stats import Interval, bootstrap_mean_diff

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_PATH = ROOT / "escalation_protocol.yaml"
LOOKS = (6, 12, 24)
LEVEL_SINGLE = 0.95
LEVEL_SEQUENTIAL = 1.0 - 0.05 / len(LOOKS)  # Bonferroni over three looks
STATUS = {"supported": "supported", "refuted": "refuted", "inconclusive": "open"}
MATCH = {("supported", "supported"), ("refuted", "refuted"), ("open", "inconclusive")}
TRACE_COLS = ("gen", "epoch", "best_err", "mean_log_err", "H", "D", "disp", "improved", "stall", "p_mut",
              "immigrant_frac")


def _load_traces(path: Path) -> dict[tuple[str, int, str], Trace]:
    z = np.load(path)
    cols: dict[tuple[str, int, str], dict] = {}
    for key in z.files:
        tag, land, seed, ctrl, col = key.split("|")
        if tag == "eval":
            cols.setdefault((land, int(seed), ctrl), {})[col] = z[key].tolist()
    return {k: Trace(**{c: v[c] for c in TRACE_COLS}) for k, v in cols.items()}


def verdict_at(lab_root: Path, cand: dict, hyps: dict, prereg: dict, k: int, level: float) -> dict:
    """The pre-registered verdict of a recorded design restricted to its first k seeds."""
    spec = cand["spec"]
    hid = spec["hypotheses"][0]
    h = hyps[hid]
    manifest = json.loads((lab_root / cand["artifacts"] / "manifest.json").read_text(encoding="utf-8"))
    seeds = set(manifest["seeds"][:k])
    sesoi = prereg["decision_rules"]["smallest_effect_of_interest"]
    if spec["kind"] == "prediction":
        traces = _load_traces(lab_root / cand["artifacts"] / "traces.npz")
        base = h.get("baseline_feature_set") or prereg["prediction_study"]["baseline_features"]
        fsets = spec["feature_sets"]
        K = prereg["prediction_study"]["horizon_K"]
        pts = [run_points(f"{land}|{seed}|{pol}", land, tr, fsets, K)
               for (land, seed, pol), tr in sorted(traces.items()) if seed in seeds]
        folds = [([p for p in pts if p.function != f], [p for p in pts if p.function == f])
                 for f in spec["landscapes"]]
        ev = evaluate_feature_sets(folds, fsets, prereg["prediction_study"]["baseline_features"],
                                   pairs=[(h["feature_set"], base)], level=level)
        ci = Interval(**ev["pair_comparisons"][f"{h['feature_set']} - {base}"]["delta_auroc"])
        return {"verdict": _verdict(ci, sesoi["prediction_delta_auroc"]), "effect": ci.to_dict()}
    rows = [json.loads(line) for line in (lab_root / cand["artifacts"] / "outcomes.jsonl").read_text(
        encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if r["seed"] in seeds]
    rmst = {(r["landscape"], r["seed"], r["controller"]): r["rmst_gens"] for r in rows}
    ctrl, comp = h["controller"], h.get("comparator") or "best_baseline"
    if comp == "best_baseline":
        pool = [c for c in spec["controllers"] if c != ctrl and not c.startswith("B3")]
        comp = min(pool, key=lambda c: np.mean([v for (l, s, cc), v in rmst.items() if cc == c]))
    units = sorted({(l, s) for (l, s, c) in rmst})
    d = np.array([rmst[(l, s, ctrl)] - rmst[(l, s, comp)] for l, s in units])
    raw = bootstrap_mean_diff(d, strata=[l for l, _ in units], level=level)
    ci = Interval(-raw.estimate, -raw.high, -raw.low, level)  # positive = faster recovery
    return {"verdict": _verdict(ci, sesoi["control_rmst_generations"]), "effect": ci.to_dict(),
            "comparator": comp}


def design_cost(cand: dict, prereg: dict, k: int) -> float:
    spec = ExperimentSpec(**{**cand["spec"], "n_seeds": k})
    derived = {"stage": "development", "dev_landscapes": prereg["landscapes"]["development"]}
    calibrated = {f: 0.0 for f in spec.landscapes}  # calibration is charged once per replicate
    return run_plan(spec, prereg, derived, calibrated)["weighted_generations"]


def replay_replicate(sweep_root: Path, reference: dict, hyps_order: list[str]) -> dict:
    prereg = load_prereg(str(PREREG_PATH))
    st = Ledger(sweep_root).state()
    hyps = st["hypotheses"]
    by_h = {c["spec"]["hypotheses"][0]: c for c in st["candidates"].values() if c["status"] == "analyzed"}
    cs = prereg["control_study"]
    calibration = CALIBRATION_SEEDS * len(prereg["landscapes"]["development"]) * cs["epochs"] * cs["period_generations"]
    per_h, cost = {}, {"always_large": 0.0, "always_small": 0.0, "escalate": 0.0}
    for hid in hyps_order:
        cand = by_h[hid]
        ref = reference[hid]
        large = verdict_at(sweep_root, cand, hyps, prereg, 24, LEVEL_SINGLE)
        small = verdict_at(sweep_root, cand, hyps, prereg, 6, LEVEL_SINGLE)
        looks = []
        for k in LOOKS:
            v = verdict_at(sweep_root, cand, hyps, prereg, k, LEVEL_SEQUENTIAL)
            looks.append({"k": k, **v})
            if v["verdict"] != "inconclusive":
                break
        stop_k = looks[-1]["k"]
        cost["always_large"] += design_cost(cand, prereg, 24)
        cost["always_small"] += design_cost(cand, prereg, 6)
        cost["escalate"] += design_cost(cand, prereg, stop_k)
        first, final = STATUS[looks[0]["verdict"]], STATUS[looks[-1]["verdict"]]
        per_h[hid] = {
            "reference": ref,
            "always_large": STATUS[large["verdict"]], "always_small": STATUS[small["verdict"]],
            "escalate": final, "escalate_looks": looks, "stop_seeds": stop_k,
            "gate_fired_at_first_look": looks[0]["verdict"] == "inconclusive",
            "rescue": (first, ref) not in MATCH and (final, ref) in MATCH,
            "damage": (first, ref) in MATCH and (final, ref) not in MATCH,
        }
    if any(c["spec"]["kind"] == "control" for c in by_h.values()):
        for s in cost:
            cost[s] += calibration
    agree = {s: sum((per_h[h][s], per_h[h]["reference"]) in MATCH for h in hyps_order)
             for s in ("always_large", "always_small", "escalate")}
    return {"per_hypothesis": per_h, "cost_generations": cost, "agreement": agree,
            "ratio_large_over_escalate": cost["always_large"] / cost["escalate"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/escalation")
    ap.add_argument("--replicates", type=int, default=None)
    ap.add_argument("--hypotheses", default=None, help="comma list (smoke tests only)")
    args = ap.parse_args()
    proto = yaml.safe_load(PROTOCOL_PATH.read_text(encoding="utf-8"))
    hyps = args.hypotheses.split(",") if args.hypotheses else proto["hypotheses"]
    reps = args.replicates or proto["replicates"]
    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} exists; study records are not overwritten")
    out.mkdir(parents=True)
    budget = 100000.0
    print("reference (48 seeds) ...", flush=True)
    ref_run = run_strategy(out / "reference", "reference", hyps, 300000, budget)
    reference = {h: ref_run["verdicts"][h][-1] for h in hyps}
    rows = []
    for r in range(reps):
        print(f"replicate {r}: running every hypothesis at 24 seeds ...", flush=True)
        run_strategy(out / f"rep{r}", "sweep", hyps, 100000 + 20000 * r, budget)
        row = replay_replicate(out / f"rep{r}", reference, hyps)
        row["replicate"] = r
        rows.append(row)
        c, a = row["cost_generations"], row["agreement"]
        print(f"rep {r}: generations large {c['always_large']:.0f} | escalate {c['escalate']:.0f} | "
              f"small {c['always_small']:.0f}; ratio {row['ratio_large_over_escalate']:.2f}; agreement "
              f"large {a['always_large']}/{len(hyps)} escalate {a['escalate']}/{len(hyps)} "
              f"small {a['always_small']}/{len(hyps)}", flush=True)
    ratios = np.array([r["ratio_large_over_escalate"] for r in rows])
    cells = [ph for r in rows for ph in r["per_hypothesis"].values()]
    summary = {
        "protocol": proto,
        "reference_verdicts": reference,
        "replicates": rows,
        "acceleration": {"mean_ratio": float(ratios.mean()), "per_replicate": ratios.tolist(),
                         "ci95": bootstrap_mean_diff(ratios).to_dict() if len(ratios) > 1 else None,
                         "mean_cost_saving": float(1 - 1 / ratios.mean())},
        "agreement": {s: [r["agreement"][s] for r in rows] for s in ("always_large", "always_small", "escalate")},
        "economics": {"P_gate_first_look": float(np.mean([c["gate_fired_at_first_look"] for c in cells])),
                      "rescues": int(sum(c["rescue"] for c in cells)),
                      "damages": int(sum(c["damage"] for c in cells)),
                      "hypothesis_replicates": len(cells)},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("acceleration", "agreement", "economics")}, indent=2))


if __name__ == "__main__":
    main()
