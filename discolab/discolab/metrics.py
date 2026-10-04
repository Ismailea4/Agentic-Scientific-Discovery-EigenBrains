"""Outcome measures computed from a run trace (analysis side: may use epochs).

Recovery after a shift (epochs k >= 1):
    T_k = generations from the shift until the population's best error <= eps.
Every epoch has the same length (``period``), so non-recovery is censored at a
fixed administrative horizon. The mean of min(T_k, period) is therefore exactly
the restricted mean recovery time (RMST) — no survival-model assumptions are
needed for the primary metric.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class RunOutcome:
    recovery_gens: list[int]  # restricted at period
    recovered: list[bool]
    rmst_gens: float
    recovery_rate: float
    offline_error_norm: float  # mean over post-burn-in generations of best_err / eps
    final_error: float

    def to_dict(self) -> dict:
        return asdict(self)


def run_outcome(best_err, epoch, eps: float, period: int) -> RunOutcome:
    best_err = np.asarray(best_err, dtype=float)
    epoch = np.asarray(epoch)
    n_epochs = int(epoch.max()) + 1
    times, rec = [], []
    for k in range(1, n_epochs):
        seg = best_err[epoch == k]
        if len(seg) != period:
            raise ValueError(f"epoch {k} has {len(seg)} generations, expected {period}")
        hit = np.flatnonzero(seg <= eps)
        if hit.size:
            times.append(int(hit[0]))
            rec.append(True)
        else:
            times.append(period)
            rec.append(False)
    post = best_err[epoch >= 1]
    return RunOutcome(
        recovery_gens=times,
        recovered=rec,
        rmst_gens=float(np.mean(times)) if times else float("nan"),
        recovery_rate=float(np.mean(rec)) if rec else float("nan"),
        offline_error_norm=float(np.mean(post / eps)) if post.size else float("nan"),
        final_error=float(best_err[-1]),
    )


def burn_in_level(best_err, epoch) -> float:
    """Best error reached at the end of the static burn-in epoch (epoch 0)."""
    best_err = np.asarray(best_err, dtype=float)
    epoch = np.asarray(epoch)
    return float(best_err[epoch == 0][-1])


def rescue_damage(base_recovered, treat_recovered) -> dict[str, int]:
    """Paired per-shift decomposition (EigenBrains escalation analysis, reused).

    rescue: baseline failed to recover, treatment recovered.
    damage: baseline recovered, treatment failed.
    """
    b = np.asarray(base_recovered, dtype=bool)
    t = np.asarray(treat_recovered, dtype=bool)
    return {
        "rescue": int(np.sum(~b & t)),
        "damage": int(np.sum(b & ~t)),
        "both_recovered": int(np.sum(b & t)),
        "neither": int(np.sum(~b & ~t)),
    }
