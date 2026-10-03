"""Population-state features x_t, computed only from observable history.

The same function builds the offline prediction dataset and feeds the online
predictive controller (B3), so the two cannot silently diverge.

Fitness-history features are made roughly scale-free across landscapes by
measuring best error relative to the first generation of the run.
"""

from __future__ import annotations

import numpy as np

FITNESS = ("rel_log_best", "dlog_1", "dlog_5", "dlog_10", "stall", "log_gen")
ENTROPY = ("H", "dH_5")
DISPERSION = ("D", "dD_5")
FITNESS_SPREAD = ("disp", "ddisp_5")

FEATURE_SETS: dict[str, tuple[str, ...]] = {
    "fitness": FITNESS,
    "fitness+entropy": FITNESS + ENTROPY,
    "fitness+dispersion": FITNESS + DISPERSION,
    "fitness+spread": FITNESS + FITNESS_SPREAD,
    "entropy_only": ENTROPY,
    "full": FITNESS + ENTROPY + DISPERSION + FITNESS_SPREAD,
}


def _lag_diff(x: np.ndarray, k: int) -> np.ndarray:
    idx = np.maximum(np.arange(len(x)) - k, 0)
    return x - x[idx]


def feature_matrix(obs, names: tuple[str, ...]) -> np.ndarray:
    """Features for every generation of an observable history (rows = generations)."""
    best = np.asarray(obs.best_err, dtype=float)
    logb = np.log10(best + 1e-12)
    cols = {
        "rel_log_best": logb - logb[0],
        "dlog_1": _lag_diff(logb, 1),
        "dlog_5": _lag_diff(logb, 5),
        "dlog_10": _lag_diff(logb, 10),
        "stall": np.asarray(obs.stall, dtype=float),
        "log_gen": np.log1p(np.asarray(obs.gen, dtype=float)),
        "H": np.asarray(obs.H, dtype=float),
        "dH_5": _lag_diff(np.asarray(obs.H, dtype=float), 5),
        "D": np.asarray(obs.D, dtype=float),
        "dD_5": _lag_diff(np.asarray(obs.D, dtype=float), 5),
        "disp": np.asarray(obs.disp, dtype=float),
        "ddisp_5": _lag_diff(np.asarray(obs.disp, dtype=float), 5),
    }
    return np.column_stack([cols[n] for n in names])


def stagnation_labels(improved: np.ndarray, epoch: np.ndarray, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    """Onset-of-stagnation labels for the prediction study.

    At-risk generations are those with an improvement event (the search is
    currently progressing). y_t = 1 when no improvement occurs in
    (t, t+horizon]. Generations whose look-ahead window leaves the run or
    crosses a landscape shift are excluded (mask False): the label must be
    about search dynamics, not about the environment changing.
    """
    improved = np.asarray(improved, dtype=bool)
    epoch = np.asarray(epoch)
    T = len(improved)
    y = np.zeros(T, dtype=bool)
    mask = np.zeros(T, dtype=bool)
    csum = np.concatenate([[0], np.cumsum(improved)])
    for t in range(T - horizon):
        if not improved[t] or epoch[t + horizon] != epoch[t]:
            continue
        mask[t] = True
        y[t] = (csum[t + horizon + 1] - csum[t + 1]) == 0
    return y, mask
