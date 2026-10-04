"""Evidence-producing experiments of the entropy early-warning study.

Every function here is an SDK ``@experiment``: it declares its outputs, units,
roles and censoring up front, draws all study randomness from the SDK RNG, and
accounts its evaluations against a budget. Simulation, features and models are
the laboratory's own unmodified code (discolab.ga, discolab.features,
discolab.predict, discolab.stats). The frozen design is passed in
``run.params`` by run_study.py, which derives it from protocol.yaml; the
protocol's SHA-256 is recorded in every run's provenance.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from discolab import ArtifactSchema, FieldSchema, MetricSpec, experiment
from discolab import controllers as C
from discolab import ga
from discolab.features import FEATURE_SETS, feature_matrix, stagnation_labels
from discolab.landscapes import get_landscape, make_shift_schedule
from discolab.predict import fit_logistic
from discolab.stats import auroc
from discolab.telemetry import ENTROPY_BINS, population_entropy

PROTOCOL = "protocol.yaml"
SCORE_SETS = ("fitness", "fitness+entropy", "fitness+dispersion", "fitness+dispersion+entropy", "entropy_only")
RULES = ("progress_rate_rule", "diversity_rule")
SCORES = SCORE_SETS + RULES
CONTRASTS = {  # id -> (model, comparator)
    "EW1": ("fitness+entropy", "fitness"),
    "EW2": ("fitness+dispersion+entropy", "fitness+dispersion"),
    "EW3": ("fitness+dispersion", "fitness"),
    "EW4": ("entropy_only", "fitness"),
}


def column(name: str) -> str:
    return "score_" + name.replace("+", "_")


# --------------------------------------------------------------------- schemas

TRACES = ArtifactSchema("traces", 1, "table", role="observation", fields=(
    FieldSchema("landscape", "string", role="stratum"),
    FieldSchema("seed", "integer", role="cluster", minimum=0),
    FieldSchema("policy", "string", role="condition"),
    FieldSchema("generation", "integer", unit="generations", role="index", minimum=0),
    FieldSchema("best_error", "number", unit="objective_error", role="observation", minimum=0),
    FieldSchema("H", "number", unit="normalized_entropy", role="observation", minimum=0, maximum=1),
    FieldSchema("D", "number", unit="dispersion_ratio", role="observation", minimum=0),
    FieldSchema("disp", "number", unit="log10_error_sd", role="observation", minimum=0),
    FieldSchema("improved", "boolean", role="event"),
    FieldSchema("stall", "integer", unit="generations", role="observation", minimum=0),
))
RUN_INDEX = ArtifactSchema("run_index", 1, "table", role="design", fields=(
    FieldSchema("landscape", "string", role="stratum"),
    FieldSchema("seed", "integer", role="cluster", minimum=0),
    FieldSchema("policy", "string", role="condition"),
    FieldSchema("mutation_multiplier", "number", unit="genes_per_individual", minimum=0),
    FieldSchema("evaluations", "integer", unit="evaluations", minimum=0),
    FieldSchema("improvement_events", "integer", unit="count", minimum=0),
    FieldSchema("final_best_error", "number", unit="objective_error", minimum=0),
))
SNAPSHOTS = ArtifactSchema("population_snapshots", 1, "array", dtype="float64", ndim=3, unit="decision_space",
                           role="state")
SNAPSHOT_BOUNDS = ArtifactSchema("snapshot_bounds", 1, "array", dtype="float64", ndim=2, unit="decision_space",
                                 role="design")
SNAPSHOT_INDEX = ArtifactSchema("snapshot_index", 1, "table", role="index", fields=(
    FieldSchema("snapshot", "integer", role="index", minimum=0),
    FieldSchema("landscape", "string", role="stratum"),
    FieldSchema("seed", "integer", role="cluster", minimum=0),
    FieldSchema("policy", "string", role="condition"),
    FieldSchema("generation", "integer", unit="generations", minimum=0),
    FieldSchema("lower", "number", unit="decision_space"),
    FieldSchema("upper", "number", unit="decision_space"),
    FieldSchema("H_python", "number", unit="normalized_entropy", role="observation", minimum=0, maximum=1),
))
SPLIT = ArtifactSchema("split_manifest", 1, "table", role="design", fields=(
    FieldSchema("cluster", "string", role="cluster"),
    FieldSchema("landscape", "string", role="stratum"),
    FieldSchema("seed", "integer", minimum=0),
    FieldSchema("policy", "string", role="condition"),
    FieldSchema("partition", "string", role="split"),
    FieldSchema("at_risk_points", "integer", unit="generations", minimum=0),
    FieldSchema("stagnation_events", "integer", unit="generations", minimum=0),
))
MODELS = ArtifactSchema("models", 1, "json", role="model")
PREDICTIONS = ArtifactSchema("predictions", 1, "table", role="prediction", fields=(
    FieldSchema("cluster", "string", role="cluster"),
    FieldSchema("landscape", "string", role="stratum"),
    FieldSchema("seed", "integer", minimum=0),
    FieldSchema("policy", "string", role="condition"),
    FieldSchema("generation", "integer", unit="generations", minimum=0),
    FieldSchema("stagnates", "boolean", role="label"),
    *(FieldSchema(column(s), "number", unit="risk_score", role="score") for s in SCORES),
))
BOOTSTRAP = ArtifactSchema("bootstrap_auroc", 1, "array", dtype="float64", ndim=2, unit="auroc", role="resamples")
RESULT = ArtifactSchema("result", 1, "json", role="analysis")
TIMING = ArtifactSchema("python_timing", 1, "json", role="benchmark")
COMPARED = ArtifactSchema("compared_values", 1, "table", role="comparison", fields=(
    FieldSchema("check", "string", role="check"),
    FieldSchema("item", "string", role="index"),
    FieldSchema("reference", "number", role="reference"),
    FieldSchema("candidate", "number", role="candidate"),
    FieldSchema("abs_difference", "number", minimum=0),
))
PARITY = ArtifactSchema("parity_report", 1, "json", role="analysis")

RUNS = MetricSpec("simulated_runs", "runs", role="primary", minimum=0)
DELTA = MetricSpec("delta_auroc", "auroc", role="primary", minimum=-1, maximum=1)
DELTA_LOW = MetricSpec("delta_auroc_ci_low", "auroc", role="secondary", minimum=-1, maximum=1)
DELTA_HIGH = MetricSpec("delta_auroc_ci_high", "auroc", role="secondary", minimum=-1, maximum=1)
PY_MEDIAN = MetricSpec("python_median_batch_seconds", "seconds", role="primary", minimum=0)
MAX_DIFF = MetricSpec("max_abs_entropy_difference", "normalized_entropy", role="primary", minimum=0)
MAX_AUROC_DIFF = MetricSpec("max_abs_auroc_difference", "auroc", role="secondary", minimum=0)


# --------------------------------------------------------------------- simulation

@contextmanager
def _record_populations(sink: list, wanted):
    """Observe the populations whose entropy the GA computes, without changing it:
    the wrapper calls the original function and returns its value unchanged."""
    original = ga.population_entropy

    def observed(X, lo, hi, bins=ENTROPY_BINS):
        value = original(X, lo, hi, bins)
        if wanted(len(sink_gen)):
            sink.append((np.array(X, dtype=np.float64, copy=True), float(lo), float(hi), value))
        sink_gen.append(None)
        return value

    sink_gen: list = []
    ga.population_entropy = observed
    try:
        yield
    finally:
        ga.population_entropy = original


def _simulate(run, landscapes, with_snapshots: bool) -> None:
    p = run.params
    cfg = ga.GAConfig(pop_size=p["pop_size"], dim=p["dim"])
    seeds = range(p["seeds"][0], p["seeds"][1] + 1)
    rows, index = [], []
    snaps, bounds, snap_rows = [], [], []
    snap_seeds = set(range(p["snapshot_seeds"][0], p["snapshot_seeds"][1] + 1)) if with_snapshots else set()
    for name in landscapes:
        land = get_landscape(name)
        for seed in seeds:
            for policy, mult in p["data_policies"].items():
                schedule = make_shift_schedule(land, cfg.dim, 1, p["generations"], 0.0, seed)
                captured: list = []
                every = p["snapshot_every"]
                if seed in snap_seeds:
                    with _record_populations(captured, lambda g: g % every == 0):
                        tr = ga.run_ga(land, schedule, C.Fixed(mult=mult), cfg, p["generations"], seed)
                else:
                    tr = ga.run_ga(land, schedule, C.Fixed(mult=mult), cfg, p["generations"], seed)
                run.consume(cfg.pop_size * p["generations"])
                for g in range(len(tr.gen)):
                    rows.append({"landscape": name, "seed": seed, "policy": policy, "generation": tr.gen[g],
                                 "best_error": tr.best_err[g], "H": tr.H[g], "D": tr.D[g], "disp": tr.disp[g],
                                 "improved": bool(tr.improved[g]), "stall": int(tr.stall[g])})
                index.append({"landscape": name, "seed": seed, "policy": policy, "mutation_multiplier": mult,
                              "evaluations": cfg.pop_size * p["generations"],
                              "improvement_events": int(sum(tr.improved)), "final_best_error": tr.best_err[-1]})
                for k, (X, lo, hi, h) in enumerate(captured):
                    generation = k * every
                    if tr.H[generation] != h:
                        raise AssertionError("observed population does not match the recorded entropy")
                    snap_rows.append({"snapshot": len(snaps), "landscape": name, "seed": seed, "policy": policy,
                                      "generation": generation, "lower": lo, "upper": hi, "H_python": h})
                    snaps.append(X)
                    bounds.append((lo, hi))
    run.emit.table("run_index", index, schema=RUN_INDEX.id)
    run.emit.table("traces", rows, schema=TRACES.id)
    if with_snapshots:
        run.emit.array("population_snapshots", np.stack(snaps), schema=SNAPSHOTS.id)
        run.emit.array("snapshot_bounds", np.array(bounds, dtype=np.float64), schema=SNAPSHOT_BOUNDS.id)
        run.emit.table("snapshot_index", snap_rows, schema=SNAPSHOT_INDEX.id)
    run.metric("simulated_runs", len(index))


@experiment(capability="ga-simulation",
            hypothesis="Development data: GA traces on development landscapes under three fixed mutation rates.",
            protocol=PROTOCOL, outputs=(RUN_INDEX, TRACES, SNAPSHOTS, SNAPSHOT_BOUNDS, SNAPSHOT_INDEX),
            primary_metric=RUNS)
def simulate_development(run):
    _simulate(run, run.params["landscapes"], with_snapshots=True)


@experiment(capability="ga-simulation",
            hypothesis="Held-out data: GA traces on landscapes never used for development.",
            protocol=PROTOCOL, outputs=(RUN_INDEX, TRACES), primary_metric=RUNS)
def simulate_held_out(run):
    _simulate(run, run.params["landscapes"], with_snapshots=False)


# --------------------------------------------------------------------- analysis helpers

def _read_rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _runs(rows: list[dict]) -> dict[tuple, dict[str, np.ndarray]]:
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        grouped.setdefault((row["landscape"], row["seed"], row["policy"]), []).append(row)
    out = {}
    for key, items in grouped.items():
        items.sort(key=lambda r: r["generation"])
        out[key] = {k: np.array([r[k] for r in items]) for k in
                    ("generation", "best_error", "H", "D", "disp", "improved", "stall")}
    return out


def _points(key, arr, horizon: int) -> dict:
    """At-risk points of one run: every feature set's matrix, rule scores, labels."""
    obs = SimpleNamespace(gen=arr["generation"], best_err=arr["best_error"], stall=arr["stall"], H=arr["H"],
                          D=arr["D"], disp=arr["disp"])
    improved = arr["improved"].astype(bool)
    y, mask = stagnation_labels(improved, np.zeros(len(improved), dtype=int), horizon)
    window = np.convolve(improved.astype(float), np.ones(10))[: len(improved)]  # events in t-9..t
    return {
        "key": key, "cluster": f"{key[0]}:{key[1]}", "generation": arr["generation"][mask], "y": y[mask],
        "X": {fs: feature_matrix(obs, FEATURE_SETS[fs])[mask] for fs in SCORE_SETS},
        "rules": {"progress_rate_rule": -window[mask], "diversity_rule": -arr["D"][mask]},
    }


def _fit_and_score(train: list[dict], test: list[dict]) -> tuple[dict, dict[str, np.ndarray]]:
    models, scores = {}, {}
    for fs in SCORE_SETS:
        X = np.concatenate([p["X"][fs] for p in train])
        y = np.concatenate([p["y"] for p in train])
        model = fit_logistic(X, y, fs)
        models[fs] = model.to_dict()
        scores[fs] = np.concatenate([model.predict_proba(p["X"][fs]) for p in test]) if test else np.array([])
    for rule in RULES:
        scores[rule] = np.concatenate([p["rules"][rule] for p in test])
    return models, scores


def _cluster_bootstrap(test: list[dict], scores: dict[str, np.ndarray], rng: np.random.Generator,
                       n_boot: int) -> np.ndarray:
    """Paired, stratified (by landscape) bootstrap over (landscape, seed) clusters.
    Columns follow SCORES; every column uses the same resamples."""
    offsets = np.cumsum([0] + [len(p["y"]) for p in test])
    by_cluster: dict[str, list[int]] = {}
    for i, p in enumerate(test):
        by_cluster.setdefault(p["cluster"], []).append(i)
    strata: dict[str, list[np.ndarray]] = {}
    for cluster, runs in sorted(by_cluster.items()):
        idx = np.concatenate([np.arange(offsets[i], offsets[i + 1]) for i in runs])
        strata.setdefault(cluster.split(":")[0], []).append(idx)
    y = np.concatenate([p["y"] for p in test])
    out = np.empty((n_boot, len(SCORES)))
    for b in range(n_boot):
        pick = np.concatenate([groups[j] for _, groups in sorted(strata.items())
                               for j in rng.integers(0, len(groups), len(groups))])
        for c, name in enumerate(SCORES):
            out[b, c] = auroc(scores[name][pick], y[pick])
    return out


def _summaries(y: np.ndarray, scores: dict, boot: np.ndarray, sesoi: float) -> dict:
    point = {name: auroc(scores[name], y) for name in SCORES}
    col = {name: c for c, name in enumerate(SCORES)}

    def interval(values, estimate):
        return {"estimate": float(estimate), "low": float(np.quantile(values, 0.025)),
                "high": float(np.quantile(values, 0.975))}

    contrasts = {}
    for cid, (a, b) in CONTRASTS.items():
        d = boot[:, col[a]] - boot[:, col[b]]
        p_two = float(min(1.0, 2 * min(np.mean(d <= 0), np.mean(d >= 0))))
        contrasts[cid] = {"model": a, "comparator": b, **interval(d, point[a] - point[b]),
                          "bootstrap_p_two_sided": p_two}
    pvals = sorted((v["bootstrap_p_two_sided"], k) for k, v in contrasts.items() if k != "EW1")
    m, running = len(pvals), 0.0
    for i, (p, k) in enumerate(pvals):
        running = max(running, min(1.0, (m - i) * p))
        contrasts[k]["holm_p_secondary"] = running
    brier = {name: float(np.mean((scores[name] - y) ** 2)) for name in SCORE_SETS}
    return {"auroc": {n: interval(boot[:, col[n]], point[n]) for n in SCORES},
            "brier": brier, "delta_brier_fitness_minus_fitness_entropy": brier["fitness"] - brier["fitness+entropy"],
            "contrasts": contrasts, "sesoi": sesoi}


def decide(interval: dict, sesoi: float) -> str:
    if interval["high"] < sesoi:
        return "no_meaningful_gain"
    if interval["low"] > 0 and interval["estimate"] >= sesoi:
        return "supported"
    return "inconclusive"


def _split_rows(points: list[dict], partition: str) -> list[dict]:
    rows: dict[tuple, dict] = {}
    for p in points:
        rows[p["key"]] = {"cluster": p["cluster"], "landscape": p["key"][0], "seed": int(p["key"][1]),
                          "policy": p["key"][2], "partition": partition, "at_risk_points": int(len(p["y"])),
                          "stagnation_events": int(p["y"].sum())}
    return [rows[k] for k in sorted(rows)]


def _prediction_rows(test: list[dict], scores: dict) -> list[dict]:
    rows, k = [], 0
    for p in test:
        for j in range(len(p["y"])):
            row = {"cluster": p["cluster"], "landscape": p["key"][0], "seed": int(p["key"][1]),
                   "policy": p["key"][2], "generation": int(p["generation"][j]), "stagnates": bool(p["y"][j])}
            row.update({column(s): float(scores[s][k]) for s in SCORES})
            rows.append(row)
            k += 1
    return rows


def _analysis(run, train: list[dict], test: list[dict], stage: str) -> dict:
    p = run.params
    split = _split_rows(train, "train") + _split_rows(test, "test")
    run.emit.table("split_manifest", split, schema=SPLIT.id)
    models, scores = _fit_and_score(train, test)
    run.emit.json("models", models, schema=MODELS.id, stage="derived", parents=["split_manifest"])
    run.emit.table("predictions", _prediction_rows(test, scores), schema=PREDICTIONS.id, stage="derived",
                   parents=["split_manifest", "models"])
    boot = _cluster_bootstrap(test, scores, run.child_rng("bootstrap"), p["n_boot"])
    run.emit.array("bootstrap_auroc", boot, schema=BOOTSTRAP.id, stage="analysis", parents=["predictions"])
    y = np.concatenate([q["y"] for q in test])
    summary = _summaries(y, scores, boot, p["sesoi"])
    primary = summary["contrasts"]["EW1"]
    per_landscape = {}
    for name in sorted({q["key"][0] for q in test}):
        mask = np.concatenate([np.full(len(q["y"]), q["key"][0] == name) for q in test])
        per_landscape[name] = {"auroc_fitness": auroc(scores["fitness"][mask], y[mask]),
                               "auroc_fitness_entropy": auroc(scores["fitness+entropy"][mask], y[mask]),
                               "delta_auroc": auroc(scores["fitness+entropy"][mask], y[mask])
                               - auroc(scores["fitness"][mask], y[mask]),
                               "test_points": int(mask.sum()), "prevalence": float(y[mask].mean())}
    result = {
        "stage": stage, "status": p["status"], "score_columns": {s: column(s) for s in SCORES},
        "bootstrap": {"resamples": p["n_boot"], "unit": "(landscape, seed) cluster", "stratified_by": "landscape",
                      "rng_stream": "bootstrap", "interval": "percentile 95%"},
        "counts": {"train_runs": len({q["key"] for q in train}), "test_runs": len({q["key"] for q in test}),
                   "train_points": int(sum(len(q["y"]) for q in train)), "test_points": int(y.size),
                   "test_clusters": len({q["cluster"] for q in test}), "test_prevalence": float(y.mean()),
                   "runs_without_at_risk_points": int(sum(len(q["y"]) == 0 for q in train + test))},
        **summary, "per_landscape_EW5": per_landscape,
        "decision": decide(primary, p["sesoi"]) if stage == "confirmatory" else None,
        "decision_rule": "no_meaningful_gain if high < sesoi; supported if low > 0 and estimate >= sesoi; "
                         "else inconclusive",
    }
    run.emit.json("result", result, schema=RESULT.id, stage="analysis", parents=["predictions", "bootstrap_auroc"])
    run.metric("delta_auroc", primary["estimate"])
    run.metric("delta_auroc_ci_low", primary["low"], spec=DELTA_LOW)
    run.metric("delta_auroc_ci_high", primary["high"], spec=DELTA_HIGH)
    return result


def _load_points(path: str, horizon: int) -> list[dict]:
    return [_points(key, arr, horizon) for key, arr in sorted(_runs(_read_rows(path)).items())]


ANALYSIS_OUTPUTS = (SPLIT, MODELS, PREDICTIONS, BOOTSTRAP, RESULT)


@experiment(capability="early-warning-analysis",
            hypothesis="Exploratory: entropy features add stagnation warning beyond fitness history "
                       "(leave-one-landscape-out on development landscapes).",
            protocol=PROTOCOL, outputs=ANALYSIS_OUTPUTS, primary_metric=DELTA)
def analyze_development(run):
    points = _load_points(run.spec.inputs["development_traces"], run.params["horizon"])
    folds = sorted({q["key"][0] for q in points})
    if folds != sorted(run.params["development_landscapes"]):
        raise AssertionError("development input contains unexpected landscapes")
    # Leave-one-landscape-out: each landscape is scored by a model fitted on the other.
    test_all, models, parts = [], {}, {s: [] for s in SCORES}
    for held in folds:
        train = [q for q in points if q["key"][0] != held]
        test = [q for q in points if q["key"][0] == held]
        models[f"held_out_{held}"], scores = _fit_and_score(train, test)
        test_all.extend(test)
        for s in SCORES:
            parts[s].append(scores[s])
    scores = {s: np.concatenate(v) for s, v in parts.items()}
    run.emit.table("split_manifest", _split_rows(points, "leave_one_landscape_out"), schema=SPLIT.id)
    run.emit.json("models", models, schema=MODELS.id, stage="derived", parents=["split_manifest"])
    run.emit.table("predictions", _prediction_rows(test_all, scores), schema=PREDICTIONS.id, stage="derived",
                   parents=["split_manifest", "models"])
    boot = _cluster_bootstrap(test_all, scores, run.child_rng("bootstrap"), run.params["n_boot"])
    run.emit.array("bootstrap_auroc", boot, schema=BOOTSTRAP.id, stage="analysis", parents=["predictions"])
    y = np.concatenate([q["y"] for q in test_all])
    summary = _summaries(y, scores, boot, run.params["sesoi"])
    result = {"stage": "exploratory", "status": "exploratory", "scheme": "leave-one-landscape-out",
              "folds": folds, "counts": {"runs": len(points), "test_points": int(y.size),
                                         "test_prevalence": float(y.mean()),
                                         "runs_without_at_risk_points": int(sum(len(q["y"]) == 0 for q in points))},
              **summary, "decision": None}
    run.emit.json("result", result, schema=RESULT.id, stage="analysis", parents=["predictions", "bootstrap_auroc"])
    primary = summary["contrasts"]["EW1"]
    run.metric("delta_auroc", primary["estimate"])
    run.metric("delta_auroc_ci_low", primary["low"], spec=DELTA_LOW)
    run.metric("delta_auroc_ci_high", primary["high"], spec=DELTA_HIGH)


@experiment(capability="early-warning-analysis",
            hypothesis="EW1 (confirmatory): on held-out landscapes, fitness+entropy features predict stagnation "
                       "onset with higher AUROC than fitness-history features alone.",
            protocol=PROTOCOL, outputs=ANALYSIS_OUTPUTS, primary_metric=DELTA)
def analyze_confirmatory(run):
    p = run.params
    train = _load_points(run.spec.inputs["development_traces"], p["horizon"])
    test = _load_points(run.spec.inputs["held_out_traces"], p["horizon"])
    train_land = {q["key"][0] for q in train}
    test_land = {q["key"][0] for q in test}
    if train_land & test_land or train_land != set(p["development_landscapes"]) \
            or test_land != set(p["held_out_landscapes"]):
        raise AssertionError(f"landscape leakage or mismatch: train {train_land}, test {test_land}")
    if {q["key"][1] for q in train} & {q["key"][1] for q in test}:
        raise AssertionError("development and held-out seeds overlap")
    _analysis(run, train, test, "confirmatory")


# --------------------------------------------------------------------- Python side of the benchmark

def _batch_entropy(snaps: np.ndarray, bounds: np.ndarray, bins: int) -> np.ndarray:
    return np.array([population_entropy(snaps[i], bounds[i, 0], bounds[i, 1], bins) for i in range(len(snaps))])


@experiment(capability="telemetry-benchmark",
            hypothesis="Reference timing of the authoritative Python entropy telemetry on the study snapshots.",
            protocol=PROTOCOL, outputs=(TIMING,), primary_metric=PY_MEDIAN)
def benchmark_python_entropy(run):
    p = run.params
    snaps = np.load(run.spec.inputs["population_snapshots"], allow_pickle=False)
    bounds = np.load(run.spec.inputs["snapshot_bounds"], allow_pickle=False)
    for _ in range(p["warmup"]):
        _batch_entropy(snaps, bounds, p["bins"])
    samples = []
    for _ in range(p["repeats"]):
        start = time.perf_counter()
        _batch_entropy(snaps, bounds, p["bins"])
        samples.append(time.perf_counter() - start)
        run.consume(len(snaps))
    s = np.sort(samples)
    run.emit.json("python_timing", {
        "implementation": "discolab.telemetry.population_entropy (NumPy)", "snapshots": int(len(snaps)),
        "warmup": p["warmup"], "repeats": p["repeats"], "samples_seconds": samples,
        "median": float(np.median(s)), "q25": float(np.quantile(s, 0.25)), "q75": float(np.quantile(s, 0.75)),
        "min": float(s[0]), "max": float(s[-1])}, schema=TIMING.id)
    run.metric("python_median_batch_seconds", float(np.median(s)))


# --------------------------------------------------------------------- cross-language checks

@experiment(capability="cross-language-check",
            hypothesis="Independent Rust and Julia computations reproduce the Python entropy telemetry and "
                       "AUROC estimates within the protocol tolerance (1e-12).",
            protocol=PROTOCOL, outputs=(COMPARED, PARITY), primary_metric=MAX_DIFF)
def cross_language_check(run):
    inputs = run.spec.inputs
    tol = run.params["tolerance"]
    python_h = {r["snapshot"]: r["H_python"] for r in _read_rows(inputs["snapshot_index"])}
    rust_h = {r["snapshot"]: r["entropy"] for r in _read_rows(inputs["rust_entropy"])}
    if set(python_h) != set(rust_h):
        raise AssertionError("Rust did not cover exactly the Python snapshots")
    rows = [{"check": "entropy_rust_vs_python", "item": str(k), "reference": python_h[k], "candidate": rust_h[k],
             "abs_difference": abs(python_h[k] - rust_h[k])} for k in sorted(python_h)]
    result = json.loads(Path(inputs["confirmatory_result"]).read_text(encoding="utf-8"))
    julia = {r["score"]: r["auroc"] for r in _read_rows(inputs["julia_auroc"])}
    for name, interval in result["auroc"].items():
        rows.append({"check": "auroc_julia_vs_python", "item": name, "reference": interval["estimate"],
                     "candidate": julia[name], "abs_difference": abs(interval["estimate"] - julia[name])})
    run.emit.table("compared_values", rows, schema=COMPARED.id)
    entropy_diff = max(r["abs_difference"] for r in rows if r["check"] == "entropy_rust_vs_python")
    auroc_diff = max(r["abs_difference"] for r in rows if r["check"] == "auroc_julia_vs_python")
    exact = sum(r["abs_difference"] == 0.0 for r in rows if r["check"] == "entropy_rust_vs_python")
    report = {"tolerance": tol, "entropy": {"snapshots": len(python_h), "max_abs_difference": entropy_diff,
                                            "bitwise_identical": exact, "within_tolerance": entropy_diff <= tol},
              "auroc": {"scores": len(julia), "max_abs_difference": auroc_diff, "within_tolerance": auroc_diff <= tol},
              "passed": entropy_diff <= tol and auroc_diff <= tol}
    run.emit.json("parity_report", report, schema=PARITY.id, stage="analysis", parents=["compared_values"])
    run.metric("max_abs_entropy_difference", entropy_diff)
    run.metric("max_abs_auroc_difference", auroc_diff, spec=MAX_AUROC_DIFF)
    if not report["passed"]:
        raise AssertionError(f"cross-language parity failed: {report}")
