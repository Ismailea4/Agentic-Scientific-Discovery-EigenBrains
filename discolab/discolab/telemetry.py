"""Population-state measurements recorded every generation.

H_t (primary, pre-registered): mean over dimensions of the normalised Shannon
entropy of a fixed-bin histogram of gene values over the search box,
    H_j = -sum_b p_b log p_b / log(B),    H_t = mean_j H_j  in [0, 1].
D_t (robustness check): root mean per-dimension variance relative to the
variance of a uniform distribution on the box (width^2 / 12), so a uniform
random population has D ~= 1 and a collapsed one has D -> 0.
"""

from __future__ import annotations

import numpy as np

ENTROPY_BINS = 10


def population_entropy(X: np.ndarray, lo: float, hi: float, bins: int = ENTROPY_BINS) -> float:
    n, d = X.shape
    idx = np.clip(((X - lo) / (hi - lo) * bins).astype(int), 0, bins - 1)
    # counts[j, b] = number of individuals whose gene j falls in bin b
    counts = np.zeros((d, bins))
    np.add.at(counts, (np.repeat(np.arange(d), n), idx.T.ravel()), 1.0)
    p = counts / n
    with np.errstate(divide="ignore", invalid="ignore"):
        h = -np.where(p > 0, p * np.log(p), 0.0).sum(axis=1) / np.log(bins)
    return float(h.mean())


def population_dispersion(X: np.ndarray, lo: float, hi: float) -> float:
    var = X.var(axis=0)
    return float(np.sqrt(var.mean() / ((hi - lo) ** 2 / 12.0)))


def fitness_dispersion(errors: np.ndarray) -> float:
    """Spread of population fitness in log space (scale-free across landscapes)."""
    return float(np.std(np.log10(errors + 1e-12)))
