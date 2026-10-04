"""Experiment specifications, execution, raw artifacts and pre-registered verdicts.

An agent may *propose* an ExperimentSpec, but everything numeric (seeds, cost,
runs, statistics, verdicts) is produced here, deterministically.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Literal

import numpy as np
import scipy
from pydantic import BaseModel, ConfigDict, Field

from . import controllers as C
from .features import FEATURE_SETS
from .ga import GAConfig, Trace, run_ga
from .landscapes import get_landscape, make_shift_schedule
from .metrics import rescue_damage, run_outcome
from .predict import evaluate_feature_sets, fit_logistic, run_points, stack
from .stats import Interval, bootstrap_mean_diff, cvar, hodges_lehmann, holm, mcnemar_exact, wilcoxon_p

PKG_DIR = Path(__file__).resolve().parent
B3_RUNTIME_FACTOR = 1.6  # B3 recomputes features each generation; estimate only, actual time is recorded
CALIBRATION_SEEDS = 20


class ExperimentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["prediction", "control"]
    title: str = Field(min_length=5, max_length=140)
    rationale: str = Field(min_length=10, max_length=2000)
    hypotheses: list[str] = Field(min_length=1)
    landscapes: list[str] = Field(min_length=1)
    n_seeds: int = Field(ge=4, le=50)  # <= 50 keeps per-experiment seed blocks (100 wide, +50 train offset) disjoint
    feature_sets: list[str] | None = None
    controllers: list[str] | None = None


# ----------------------------------------------------------------- validation
def validate_spec(spec: ExperimentSpec, prereg: dict, hypotheses: dict[str, dict]) -> dict:
    dev = prereg["landscapes"]["development"]
    held = prereg["landscapes"]["held_out"]
    for name in spec.landscapes:
        get_landscape(name)
    if len(set(spec.landscapes)) != len(spec.landscapes):
        raise ValueError("duplicate landscapes")
    if set(spec.landscapes) <= set(dev):
        stage = "development"
    elif set(spec.landscapes) <= set(held):
        stage = "confirmatory"
    else:
        raise ValueError("an experiment must use only development or only held-out landscapes, not a mix")
    for hid in spec.hypotheses:
        if hid not in hypotheses:
            raise ValueError(f"unknown hypothesis {hid}")
    if spec.kind == "prediction":
        if spec.controllers:
            raise ValueError("prediction experiments do not take controllers")
        fs = spec.feature_sets or []
        if prereg["prediction_study"]["baseline_features"] not in fs:
            raise ValueError("feature_sets must include the pre-registered baseline 'fitness'")
        bad = [f for f in fs if f not in FEATURE_SETS]
        if bad:
            raise ValueError(f"unknown feature sets {bad}; known: {sorted(FEATURE_SETS)}")
        for hid in spec.hypotheses:
            h = hypotheses[hid]
            base = h.get("baseline_feature_set") or prereg["prediction_study"]["baseline_features"]
            if h["family"] != "prediction" or h.get("feature_set") not in fs or base not in fs:
                raise ValueError(f"{hid} needs feature_sets containing {h.get('feature_set')!r} and its "
                                 f"comparison baseline {base!r}")
        if stage == "development" and len(spec.landscapes) < 2:
            raise ValueError("development-stage prediction needs >= 2 landscapes (leave-one-landscape-out)")
    else:
        if spec.feature_sets:
            raise ValueError("control experiments do not take feature_sets")
        cs = spec.controllers or []
        if "B0_fixed" not in cs:
            raise ValueError("controllers must include the B0_fixed reference")
        bad = [c for c in cs if not is_known_controller(c)]
        if bad:
            raise ValueError(f"unknown controllers {bad}; known: {list(C.CONTROLLERS)} + "
                             f"{list(PREDICTIVE_VARIANTS)} + rate-matched 'B0_fixed_x<m>' (0.25 <= m <= 4)")
        for hid in spec.hypotheses:
            h = hypotheses[hid]
            comparator = h.get("comparator") or "best_baseline"
            if h["family"] != "control" or h.get("controller") not in cs or \
                    (comparator != "best_baseline" and comparator not in cs):
                raise ValueError(f"{hid} needs controllers containing {h.get('controller')!r} and its "
                                 f"comparator {comparator!r}")
    return {"stage": stage, "dev_landscapes": dev}


# Predictive (B3-family) controllers and the feature set their frozen risk model uses.
PREDICTIVE_VARIANTS = {"B3_predictive": "fitness+entropy", "B3d_predictive": "fitness+dispersion",
                       "B5_hybrid": "fitness+entropy"}


def is_known_controller(name: str) -> bool:
    if name in C.CONTROLLERS or name in PREDICTIVE_VARIANTS:
        return True
    if name.startswith("B0_fixed_x"):
        try:
            return 0.25 <= float(name.removeprefix("B0_fixed_x")) <= 4.0
        except ValueError:
            return False
    return False


def allocate_seeds(prereg: dict, block: str, ordinal: int, n: int, offset: int = 0, lab_block: int = 0) -> list[int]:
    """Seeds for one experiment. Each lab's development and test seeds are shifted by
    lab_block * lab_block_stride, so separate labs are independent replications;
    calibration seeds are shared because the recovery threshold is a metric definition."""
    lo, hi = prereg["seeds"][block]
    if block != "calibration":
        shift = lab_block * prereg["seeds"].get("lab_block_stride", 0)
        lo, hi = lo + shift, hi + shift
    start = lo + 100 * (prereg["seeds"].get("experiment_offset", 0) + ordinal) + offset
    seeds = list(range(start, start + n))
    if seeds[-1] > hi:
        raise ValueError(f"seed block {block} exhausted")
    return seeds


# ------------------------------------------------------------------- costing
def run_plan(spec: ExperimentSpec, prereg: dict, derived: dict, calibrated: dict) -> dict:
    """Count simulated generations (CPU work) without running anything."""
    ps, cs = prereg["prediction_study"], prereg["control_study"]
    dev = derived["dev_landscapes"]
    n_pol = len(ps["data_policies"])
    if spec.kind == "prediction":
        runs = spec.n_seeds * n_pol * len(spec.landscapes)
        if derived["stage"] == "confirmatory":
            runs += spec.n_seeds * n_pol * len(dev)
        gens = runs * ps["static_generations"]
        return {"runs": runs, "generations": gens, "weighted_generations": gens}
    n_dyn = cs["epochs"] * cs["period_generations"]
    ctrl = spec.controllers or []
    runs = spec.n_seeds * len(spec.landscapes) * len(ctrl)
    weighted = spec.n_seeds * len(spec.landscapes) * n_dyn * sum(
        B3_RUNTIME_FACTOR if c in PREDICTIVE_VARIANTS else 1.0 for c in ctrl)
    if any(c in PREDICTIVE_VARIANTS for c in ctrl):  # fit frozen risk models on fresh development seeds
        runs += spec.n_seeds * n_pol * len(dev)
        weighted += spec.n_seeds * n_pol * len(dev) * ps["static_generations"]
    missing = [f for f in spec.landscapes if f not in calibrated]
    runs += CALIBRATION_SEEDS * len(missing)
    weighted += CALIBRATION_SEEDS * len(missing) * n_dyn
    return {"runs": runs, "generations": int(weighted), "weighted_generations": float(weighted)}


def n_workers() -> int:
    return max(1, min(8, (os.cpu_count() or 2) - 1))


def estimate_cost(plan: dict, sec_per_generation: float) -> dict:
    cpu = plan["weighted_generations"] * sec_per_generation
    return {"cpu_seconds": round(cpu, 2), "wall_seconds": round(cpu / n_workers() + 2.0, 2)}


def measure_sec_per_generation() -> float:
    L = get_landscape("rastrigin")
    cfg = GAConfig()
    sch = make_shift_schedule(L, cfg.dim, 1, 200, 0.2, 0)
    t = time.perf_counter()
    run_ga(L, sch, C.Fixed(), cfg, 200, 0)
    return (time.perf_counter() - t) / 200


# ------------------------------------------------------------------ execution
def _simulate(task: dict) -> tuple[dict, dict]:
    L = get_landscape(task["landscape"])
    cfg = GAConfig()
    sch = make_shift_schedule(L, cfg.dim, task["n_epochs"], task["period"], task["severity"], task["seed"])
    model = C.LogisticModel.from_dict(task["model"]) if task.get("model") else None
    if task["controller"] in PREDICTIVE_VARIANTS:
        if model is None:
            raise ValueError(f"{task['controller']} needs its fitted risk model")
        ctrl = C.HybridPredictive(model) if task["controller"] == "B5_hybrid" else C.Predictive(model)
    else:
        ctrl = C.make_controller(task["controller"])
    tr = run_ga(L, sch, ctrl, cfg, task["n_epochs"] * task["period"], task["seed"])
    return task, {k: list(v) for k, v in tr.__dict__.items()}


def _quiet_worker() -> None:
    # Workers inherit the parent's stdout, which carries the MCP JSON-RPC
    # stream when the lab runs behind the tool server: never write to it.
    import sys

    sys.stdout = sys.stderr


SINGLE_THREAD_ENV = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")


def _run_tasks(tasks: list[dict]) -> list[tuple[dict, Trace]]:
    # Parallelism comes from processes; each worker's BLAS must be single-threaded.
    # Otherwise every worker sizes OpenBLAS buffers for all cores, which exhausted
    # memory on the recording machine (acceleration study attempt 1) and
    # oversubscribes the CPU. Spawned workers inherit these variables.
    for var in SINGLE_THREAD_ENV:
        os.environ.setdefault(var, "1")
    out = []
    with ProcessPoolExecutor(max_workers=n_workers(), initializer=_quiet_worker) as pool:
        for task, cols in pool.map(_simulate, tasks, chunksize=4):
            out.append((task, Trace(**cols)))
    return out


def _static_tasks(landscapes, seeds, prereg) -> list[dict]:
    ps = prereg["prediction_study"]
    return [
        {"landscape": f, "seed": s, "controller": pol, "n_epochs": 1, "period": ps["static_generations"],
         "severity": prereg["control_study"]["severity"]}
        for f in landscapes for s in seeds for pol in ps["data_policies"]
    ]


def _dynamic_tasks(landscapes, seeds, controllers, prereg, models=None) -> list[dict]:
    cs = prereg["control_study"]
    models = models or {}
    return [
        {"landscape": f, "seed": s, "controller": c, "n_epochs": cs["epochs"], "period": cs["period_generations"],
         "severity": cs["severity"], "model": models.get(c)}
        for f in landscapes for s in seeds for c in controllers
    ]


def calibrate_eps(landscapes: list[str], prereg: dict) -> dict[str, float]:
    lo = prereg["seeds"]["calibration"][0]
    seeds = list(range(lo, lo + CALIBRATION_SEEDS))
    res = _run_tasks(_dynamic_tasks(landscapes, seeds, ["B0_fixed"], prereg))
    out = {}
    for f in landscapes:
        ends = []
        for task, tr in res:
            if task["landscape"] != f:
                continue
            b, e = np.asarray(tr.best_err), np.asarray(tr.epoch)
            ends += [b[e == k][-1] for k in range(1, int(e.max()) + 1)]
        out[f] = float(np.median(ends))
    return out


def code_fingerprint() -> dict:
    h = hashlib.sha256()
    for p in sorted(PKG_DIR.glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PKG_DIR, capture_output=True, text=True,
                                timeout=5).stdout.strip() or None
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=PKG_DIR.parent,
                                    capture_output=True, text=True, timeout=5).stdout.strip())
    except Exception:
        commit, dirty = None, None
    return {"discolab_sha256": h.hexdigest(), "git_commit": commit, "git_dirty": dirty,
            "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__}


def _save_traces(path: Path, results: list[tuple[dict, Trace]], tag: str) -> None:
    arrays = {}
    for task, tr in results:
        key = f"{tag}|{task['landscape']}|{task['seed']}|{task['controller']}"
        for col, val in tr.to_arrays().items():
            arrays[f"{key}|{col}"] = val
    np.savez_compressed(path, **arrays)


def run_experiment(spec: ExperimentSpec, exp_id: str, ordinal: int, root: Path, prereg: dict,
                   derived: dict, calibrated: dict, hypotheses: dict[str, dict]) -> dict:
    out_dir = Path(root) / "runs" / exp_id
    if out_dir.exists():
        raise FileExistsError(f"artifacts for {exp_id} already exist; raw records are immutable")
    out_dir.mkdir(parents=True)
    t0 = time.perf_counter()
    block = "development" if derived["stage"] == "development" else "test"
    seeds = allocate_seeds(prereg, block, ordinal, spec.n_seeds, lab_block=derived.get("lab_block", 0))
    manifest = {"id": exp_id, "spec": spec.model_dump(), "derived": derived, "seeds": seeds, "seed_block": block,
                "prereg_sha256": prereg["_sha256"], "code": code_fingerprint(), "workers": n_workers()}
    new_cal = {}
    if spec.kind == "prediction":
        summary = _run_prediction(spec, seeds, prereg, derived, ordinal, out_dir, manifest, hypotheses)
    else:
        missing = [f for f in spec.landscapes if f not in calibrated]
        if missing:
            new_cal = calibrate_eps(missing, prereg)
        eps = {**calibrated, **new_cal}
        summary = _run_control(spec, seeds, prereg, derived, ordinal, out_dir, manifest, eps, hypotheses)
    summary["verdicts"] = verdicts(spec, summary, prereg, hypotheses)
    runtime = time.perf_counter() - t0
    manifest["runtime_sec"] = runtime
    manifest["calibration_added"] = new_cal
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return {"summary": summary, "artifacts": str(out_dir), "runtime_sec": runtime, "calibration": new_cal}


def _run_prediction(spec, seeds, prereg, derived, ordinal, out_dir, manifest, hypotheses) -> dict:
    ps = prereg["prediction_study"]
    K, fsets, base = ps["horizon_K"], spec.feature_sets, ps["baseline_features"]
    if derived["stage"] == "development":
        res = _run_tasks(_static_tasks(spec.landscapes, seeds, prereg))
        _save_traces(out_dir / "traces.npz", res, "eval")
        pts = [run_points(f"{t['landscape']}|{t['seed']}|{t['controller']}", t["landscape"], tr, fsets, K)
               for t, tr in res]
        folds = [([p for p in pts if p.function != f], [p for p in pts if p.function == f]) for f in spec.landscapes]
        design = "leave-one-landscape-out over development landscapes"
    else:
        dev_seeds = allocate_seeds(prereg, "development", ordinal, spec.n_seeds, offset=50,
                                   lab_block=derived.get("lab_block", 0))
        manifest["train_seeds"] = dev_seeds
        res_tr = _run_tasks(_static_tasks(derived["dev_landscapes"], dev_seeds, prereg))
        res_te = _run_tasks(_static_tasks(spec.landscapes, seeds, prereg))
        _save_traces(out_dir / "traces_train.npz", res_tr, "train")
        _save_traces(out_dir / "traces.npz", res_te, "eval")
        tr_pts = [run_points(f"{t['landscape']}|{t['seed']}|{t['controller']}", t["landscape"], tr, fsets, K)
                  for t, tr in res_tr]
        te_pts = [run_points(f"{t['landscape']}|{t['seed']}|{t['controller']}", t["landscape"], tr, fsets, K)
                  for t, tr in res_te]
        folds = [(tr_pts, te_pts)]
        design = "train on development landscapes, test on held-out landscapes"
    pairs = sorted({(hypotheses[h]["feature_set"], hypotheses[h].get("baseline_feature_set") or base)
                    for h in spec.hypotheses})
    ev = evaluate_feature_sets(folds, fsets, base, pairs=pairs)
    return {"kind": "prediction", "stage": derived["stage"], "design": design, **ev}


def _paired(outcomes, a: str, b: str, key: str):
    """Paired per-(landscape, seed) values for controllers a and b."""
    pairs = sorted({(f, s) for (f, s, c) in outcomes if c == a} & {(f, s) for (f, s, c) in outcomes if c == b})
    va = np.array([getattr(outcomes[(f, s, a)], key) for f, s in pairs])
    vb = np.array([getattr(outcomes[(f, s, b)], key) for f, s in pairs])
    return va, vb, [f for f, _ in pairs]


def _run_control(spec, seeds, prereg, derived, ordinal, out_dir, manifest, eps, hypotheses) -> dict:
    cs, ps = prereg["control_study"], prereg["prediction_study"]
    models, model_summary = {}, {}
    variants = [c for c in spec.controllers if c in PREDICTIVE_VARIANTS]
    if variants:
        dev_seeds = allocate_seeds(prereg, "development", ordinal, spec.n_seeds, offset=50,
                                   lab_block=derived.get("lab_block", 0))
        manifest["risk_model_seeds"] = dev_seeds
        res_fit = _run_tasks(_static_tasks(derived["dev_landscapes"], dev_seeds, prereg))
        for v in variants:
            fs = PREDICTIVE_VARIANTS[v]
            pts = [run_points(str(i), t["landscape"], tr, [fs], ps["horizon_K"]) for i, (t, tr) in enumerate(res_fit)]
            m = fit_logistic(*stack(pts, fs), fs)
            models[v] = m.to_dict()
            model_summary[v] = {"feature_set": fs, "n_fit_runs": len(pts),
                                "coef": dict(zip(m.names, map(float, m.coef)))}
        (out_dir / "risk_models.json").write_text(json.dumps(models, indent=2), encoding="utf-8")
    res = _run_tasks(_dynamic_tasks(spec.landscapes, seeds, spec.controllers, prereg, models))
    _save_traces(out_dir / "traces.npz", res, "eval")
    period = cs["period_generations"]
    outcomes = {}
    with (out_dir / "outcomes.jsonl").open("w", encoding="utf-8") as fh:
        for task, tr in res:
            o = run_outcome(tr.best_err, tr.epoch, eps[task["landscape"]], period)
            outcomes[(task["landscape"], task["seed"], task["controller"])] = o
            fh.write(json.dumps({"landscape": task["landscape"], "seed": task["seed"],
                                 "controller": task["controller"], **o.to_dict()}) + "\n")

    per_ctrl = {}
    for c in spec.controllers:
        units = sorted((f, s) for (f, s, cc) in outcomes if cc == c)
        os_ = [outcomes[(f, s, c)] for f, s in units]
        # Shifts within a run are not independent: recovery rate is the mean of
        # per-run rates with a run-clustered bootstrap stratified by landscape.
        per_ctrl[c] = {
            "rmst_gens_mean": float(np.mean([o.rmst_gens for o in os_])),
            "recovery_rate": bootstrap_mean_diff([o.recovery_rate for o in os_],
                                                 strata=[f for f, _ in units]).to_dict(),
            "cvar90_recovery_gens": cvar([t for o in os_ for t in o.recovery_gens], 0.9),
            "offline_error_norm_mean": float(np.mean([o.offline_error_norm for o in os_])),
            "mean_p_mut": None,
        }
    for task, tr in res:  # average mutation rate actually used (shows what a controller did)
        per_ctrl[task["controller"]].setdefault("_p", []).append(float(np.mean(tr.p_mut)))
    for c in per_ctrl:
        per_ctrl[c]["mean_p_mut"] = float(np.mean(per_ctrl[c].pop("_p")))

    vs_b0, pvals = {}, {}
    for c in spec.controllers:
        if c == "B0_fixed":
            continue
        vc, vb, strata = _paired(outcomes, c, "B0_fixed", "rmst_gens")
        d = vc - vb
        rec_b = [r for (f, s, cc), o in sorted(outcomes.items()) if cc == "B0_fixed" for r in o.recovered]
        rec_c = [r for (f, s, cc), o in sorted(outcomes.items()) if cc == c for r in o.recovered]
        rd = rescue_damage(rec_b, rec_c)
        rc, rb, _ = _paired(outcomes, c, "B0_fixed", "recovery_rate")
        pvals[c] = wilcoxon_p(d)
        vs_b0[c] = {
            "delta_rmst_gens": bootstrap_mean_diff(d, strata=strata).to_dict(),
            "delta_recovery_rate": bootstrap_mean_diff(rc - rb, strata=strata).to_dict(),
            "hodges_lehmann": hodges_lehmann(d),
            "wilcoxon_p": pvals[c],
            "rescue_damage": rd,
            # descriptive only: treats shifts as independent although they are clustered in runs
            "mcnemar_p_descriptive": mcnemar_exact(rd["rescue"], rd["damage"]),
            "standardised_effect": float(-d.mean() / d.std(ddof=1)) if d.std(ddof=1) > 0 else 0.0,
        }
    for c, rej in holm(pvals).items():
        vs_b0[c]["holm_reject"] = rej

    contrasts = {}
    for hid in spec.hypotheses:
        h = hypotheses[hid]
        ctrl = h["controller"]
        comparator = h.get("comparator") or "best_baseline"
        if comparator == "best_baseline":
            baselines = [c for c in spec.controllers if c != ctrl and c not in PREDICTIVE_VARIANTS]
            comparator = min(baselines, key=lambda c: per_ctrl[c]["rmst_gens_mean"])
        vt, vb, strata = _paired(outcomes, ctrl, comparator, "rmst_gens")
        d = vt - vb
        contrasts[hid] = {"controller": ctrl, "comparator": comparator,
                          "delta_rmst_gens": bootstrap_mean_diff(d, strata=strata).to_dict(),
                          "standardised_effect": float(-d.mean() / d.std(ddof=1)) if d.std(ddof=1) > 0 else 0.0}
    return {"kind": "control", "stage": derived["stage"], "eps": {f: eps[f] for f in spec.landscapes},
            "n_seeds": spec.n_seeds, "per_controller": per_ctrl, "vs_B0": vs_b0, "contrasts": contrasts,
            "risk_models": model_summary}


# ------------------------------------------------------------------- verdicts
def _verdict(effect: Interval, sesoi: float) -> str:
    """effect is oriented so that positive = in the hypothesised direction."""
    if effect.low > 0:
        return "supported"
    if effect.high < sesoi:
        return "refuted"
    return "inconclusive"


def verdicts(spec: ExperimentSpec, summary: dict, prereg: dict, hypotheses: dict[str, dict]) -> dict:
    sesoi = prereg["decision_rules"]["smallest_effect_of_interest"]
    out = {}
    for hid in spec.hypotheses:
        h = hypotheses[hid]
        if spec.kind == "prediction":
            base = h.get("baseline_feature_set") or prereg["prediction_study"]["baseline_features"]
            comp = summary["pair_comparisons"][f"{h['feature_set']} - {base}"]
            ci = Interval(**comp["delta_auroc"])
            out[hid] = {"verdict": _verdict(ci, sesoi["prediction_delta_auroc"]), "effect": comp["delta_auroc"],
                        "standardised_effect": comp["standardised_effect"], "n_units": summary["n_test_runs"],
                        "stage": summary["stage"], "measure": f"delta AUROC ({h['feature_set']} - {base})"}
        else:
            comp = summary["contrasts"][hid]
            raw = Interval(**comp["delta_rmst_gens"])
            ci = Interval(-raw.estimate, -raw.high, -raw.low)  # orient: positive = faster recovery
            out[hid] = {"verdict": _verdict(ci, sesoi["control_rmst_generations"]), "effect": ci.to_dict(),
                        "standardised_effect": comp["standardised_effect"],
                        "n_units": spec.n_seeds * len(spec.landscapes), "stage": summary["stage"],
                        "measure": f"RMST reduction, {comp['controller']} vs {comp['comparator']} (generations)"}
    return out
