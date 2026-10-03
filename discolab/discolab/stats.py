"""Inference utilities. Adapted from the EigenBrains benchmark layer
(backend/app/benchmark/statistics.py, bounds.py), re-implemented here without
its BenchmarkRun types.

Resampling is always done over independent units (runs or seeds), never over
generations, because generations within a run are strongly autocorrelated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy import stats as st


@dataclass(frozen=True)
class Interval:
    estimate: float
    low: float
    high: float
    level: float = 0.95

    def excludes_zero(self) -> bool:
        return self.low > 0 or self.high < 0

    def to_dict(self) -> dict:
        return asdict(self)


def bootstrap_mean_diff(diffs, n_boot: int = 4000, seed: int = 0, level: float = 0.95,
                        strata=None) -> Interval:
    """Percentile bootstrap CI for the mean of paired differences (optionally stratified)."""
    diffs = np.asarray(diffs, dtype=float)
    if diffs.size < 2:
        raise ValueError("need at least two paired units")
    rng = np.random.default_rng(seed)
    if strata is None:
        idx = rng.integers(0, diffs.size, size=(n_boot, diffs.size))
        boots = diffs[idx].mean(axis=1)
    else:
        strata = np.asarray(strata)
        groups = [np.flatnonzero(strata == s) for s in np.unique(strata)]
        boots = np.empty(n_boot)
        for b in range(n_boot):
            pick = np.concatenate([g[rng.integers(0, g.size, g.size)] for g in groups])
            boots[b] = diffs[pick].mean()
    a = (1 - level) / 2
    return Interval(float(diffs.mean()), float(np.quantile(boots, a)), float(np.quantile(boots, 1 - a)), level)


def wilson(successes: int, total: int, level: float = 0.95) -> Interval:
    if total <= 0:
        raise ValueError("total must be positive")
    z = st.norm.ppf(1 - (1 - level) / 2)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * np.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return Interval(p, max(0.0, centre - half), min(1.0, centre + half), level)


def mcnemar_exact(rescue: int, damage: int) -> float:
    """Two-sided exact McNemar p-value on discordant pairs."""
    n = rescue + damage
    if n == 0:
        return 1.0
    return float(min(1.0, 2 * st.binom.cdf(min(rescue, damage), n, 0.5)))


def hodges_lehmann(diffs) -> float:
    d = np.asarray(diffs, dtype=float)
    walsh = (d[:, None] + d[None, :]) / 2
    return float(np.median(walsh[np.triu_indices(d.size)]))


def wilcoxon_p(diffs) -> float:
    d = np.asarray(diffs, dtype=float)
    if np.allclose(d, 0):
        return 1.0
    return float(st.wilcoxon(d, zero_method="zsplit").pvalue)


def holm(pvals: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm-Bonferroni step-down: returns reject decisions per key."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out, still = {}, True
    for i, (k, p) in enumerate(items):
        still = still and p <= alpha / (m - i)
        out[k] = still
    return out


def cvar(losses, alpha: float = 0.9) -> float:
    """Mean of the worst (1-alpha) tail of losses (EigenBrains downside-risk measure)."""
    x = np.sort(np.asarray(losses, dtype=float))
    if x.size == 0:
        return float("nan")
    var = np.quantile(x, alpha)
    return float(x[x >= var].mean())


def auroc(scores, labels) -> float:
    """Mann-Whitney AUROC with average ranks for ties."""
    s = np.asarray(scores, dtype=float)
    y = np.asarray(labels, dtype=bool)
    n1, n0 = int(y.sum()), int((~y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = st.rankdata(s)
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
