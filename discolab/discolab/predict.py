"""Phase 1: does population-state information predict stagnation onset?

Dataset: at-risk generations (an improvement just happened) with label
"no further improvement within K generations". Models: L2-regularised
logistic regression on standardised features, fitted only on training runs.
Inference: AUROC on held-out runs, with a *paired, run-clustered* bootstrap
for the difference between feature sets (both models scored on the same
resampled runs; generations are never resampled individually).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from .controllers import LogisticModel
from .features import FEATURE_SETS, feature_matrix, stagnation_labels
from .ga import ObsView, Trace
from .stats import Interval, auroc

L2 = 1e-2


@dataclass
class RunPoints:
    run_id: str
    function: str
    X: dict[str, np.ndarray]  # feature-set name -> (n_points, n_features)
    y: np.ndarray


def run_points(run_id: str, function: str, tr: Trace, feature_sets, horizon: int) -> RunPoints:
    arr = tr.to_arrays()
    y, mask = stagnation_labels(arr["improved"], arr["epoch"], horizon)
    view = ObsView(tr)
    X = {fs: feature_matrix(view, FEATURE_SETS[fs])[mask] for fs in feature_sets}
    return RunPoints(run_id, function, X, y[mask])


def fit_logistic(X: np.ndarray, y: np.ndarray, feature_set: str) -> LogisticModel:
    if len(np.unique(y)) < 2:
        raise ValueError("training labels contain a single class; cannot fit")
    mean = X.mean(axis=0)
    scale = X.std(axis=0)
    scale[scale < 1e-12] = 1.0
    Z = (X - mean) / scale
    yf = y.astype(float)

    def nll(w):
        z = Z @ w[1:] + w[0]
        p = 1 / (1 + np.exp(-np.clip(z, -40, 40)))
        loss = -np.mean(yf * np.log(p + 1e-12) + (1 - yf) * np.log(1 - p + 1e-12)) + L2 * np.sum(w[1:] ** 2)
        g = np.concatenate([[np.mean(p - yf)], Z.T @ (p - yf) / len(yf) + 2 * L2 * w[1:]])
        return loss, g

    res = minimize(nll, np.zeros(Z.shape[1] + 1), jac=True, method="L-BFGS-B")
    if not res.success:
        raise RuntimeError(f"logistic fit failed: {res.message}")
    return LogisticModel(feature_set, FEATURE_SETS[feature_set], mean, scale, res.x[1:], float(res.x[0]))


def stack(points: list[RunPoints], fs: str) -> tuple[np.ndarray, np.ndarray]:
    return np.concatenate([p.X[fs] for p in points]), np.concatenate([p.y for p in points])


def evaluate_feature_sets(folds: list[tuple[list[RunPoints], list[RunPoints]]], feature_sets: list[str],
                          baseline: str, n_boot: int = 2000, seed: int = 0,
                          pairs: list[tuple[str, str]] | None = None, level: float = 0.95) -> dict:
    """Fit per fold on train runs only; pool held-out scores across folds."""
    if baseline not in feature_sets:
        raise ValueError("baseline feature set must be among those evaluated")
    models: dict[str, list] = {fs: [] for fs in feature_sets}
    scores: dict[str, list] = {fs: [] for fs in feature_sets}
    test: list[RunPoints] = []
    train_runs = 0
    for train, fold_test in folds:
        train_runs += len(train)
        test.extend(fold_test)
        for fs in feature_sets:
            Xtr, ytr = stack(train, fs)
            m = fit_logistic(Xtr, ytr, fs)
            models[fs].append(m)
            scores[fs].extend(m.predict_proba(p.X[fs]) for p in fold_test)
    ys = [p.y for p in test]
    y_all = np.concatenate(ys)
    point = {fs: auroc(np.concatenate(scores[fs]), y_all) for fs in feature_sets}
    brier = {fs: float(np.mean((np.concatenate(scores[fs]) - y_all) ** 2)) for fs in feature_sets}

    # paired run-cluster bootstrap, stratified by test function
    rng = np.random.default_rng(seed)
    funcs = np.array([p.function for p in test])
    groups = [np.flatnonzero(funcs == f) for f in np.unique(funcs)]
    boot = {fs: np.empty(n_boot) for fs in feature_sets}
    for b in range(n_boot):
        pick = np.concatenate([g[rng.integers(0, g.size, g.size)] for g in groups])
        yb = np.concatenate([ys[i] for i in pick])
        for fs in feature_sets:
            boot[fs][b] = auroc(np.concatenate([scores[fs][i] for i in pick]), yb)

    tail = (1.0 - level) / 2.0

    def ci(arr, est):
        return Interval(float(est), float(np.nanquantile(arr, tail)), float(np.nanquantile(arr, 1.0 - tail)), level)

    def compare(a: str, b: str) -> dict:
        d = boot[a] - boot[b]
        est = point[a] - point[b]
        sd = float(np.nanstd(d))
        return {
            "delta_auroc": ci(d, est).to_dict(),
            # standardised per-run effect, used by the planner to update its power model
            "standardised_effect": float(est / (sd * np.sqrt(len(test)))) if sd > 0 else 0.0,
        }

    comparisons = {fs: compare(fs, baseline) for fs in feature_sets if fs != baseline}
    pair_comparisons = {}
    for a, b in pairs or []:
        if a not in feature_sets or b not in feature_sets:
            raise ValueError(f"comparison {a} - {b} needs both feature sets evaluated")
        pair_comparisons[f"{a} - {b}"] = compare(a, b)
    return {
        "n_folds": len(folds),
        "n_train_runs": train_runs,
        "n_test_runs": len(test),
        "n_test_points": int(y_all.size),
        "test_prevalence": float(y_all.mean()),
        "auroc": {fs: ci(boot[fs], point[fs]).to_dict() for fs in feature_sets},
        "brier": brier,
        "baseline": baseline,
        "comparisons": comparisons,
        "pair_comparisons": pair_comparisons,
        "models": {fs: [m.to_dict() for m in ms] for fs, ms in models.items()},
    }
