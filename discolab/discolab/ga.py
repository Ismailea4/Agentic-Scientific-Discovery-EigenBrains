"""Real-coded generational GA on (possibly translated) landscapes.

Design invariants (tested in tests/test_ga.py):
- Common random numbers: the initial population and the shift schedule depend
  only on (seed, landscape, dim), never on the controller, so controllers are
  compared on identical starting conditions.
- Every individual, including carried-over elites, is re-evaluated each
  generation on the *current* landscape: stale fitness cannot survive a shift.
- Controllers observe only population-level quantities (best error, entropy,
  dispersion, stall counter, generation index). The epoch / shift times are
  recorded for analysis but never passed to a controller.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .landscapes import Landscape, ShiftSchedule
from .telemetry import fitness_dispersion, population_dispersion, population_entropy

SOLVED_ERROR = 1e-8  # improvements below this error are not counted
IMPROVEMENT_REL = 1e-3  # an "improvement event" needs a >0.1% drop in best error


@dataclass(frozen=True)
class GAConfig:
    pop_size: int = 50
    dim: int = 10
    crossover_prob: float = 0.9
    sbx_eta: float = 15.0
    elites: int = 1
    mutation_sigma_frac: float = 0.05  # Gaussian step as a fraction of box width


@dataclass(frozen=True)
class Action:
    p_mut: float  # per-gene mutation probability
    immigrant_frac: float = 0.0  # fraction of offspring replaced by uniform random points


OBSERVABLE = ("gen", "best_err", "H", "D", "disp", "improved", "stall")


@dataclass
class Trace:
    """Per-generation record of one run. Columns are plain lists for cheap appends."""

    gen: list[int] = field(default_factory=list)
    epoch: list[int] = field(default_factory=list)  # analysis only — never shown to controllers
    best_err: list[float] = field(default_factory=list)
    mean_log_err: list[float] = field(default_factory=list)
    H: list[float] = field(default_factory=list)
    D: list[float] = field(default_factory=list)
    disp: list[float] = field(default_factory=list)
    improved: list[bool] = field(default_factory=list)
    stall: list[int] = field(default_factory=list)
    p_mut: list[float] = field(default_factory=list)
    immigrant_frac: list[float] = field(default_factory=list)

    def to_arrays(self) -> dict[str, np.ndarray]:
        return {k: np.asarray(v) for k, v in self.__dict__.items()}


class ObsView:
    """Read-only window onto the observable trace columns (no epoch, no shift info)."""

    __slots__ = OBSERVABLE

    def __init__(self, tr: Trace):
        for k in OBSERVABLE:
            object.__setattr__(self, k, getattr(tr, k))

    def __setattr__(self, *_):
        raise AttributeError("ObsView is read-only")


def _rngs(seed: int, landscape: Landscape, dim: int) -> tuple[np.random.Generator, np.random.Generator]:
    tag = sum(ord(c) for c in landscape.name)
    init = np.random.default_rng(np.random.SeedSequence([seed, tag, dim, 1]))
    ops = np.random.default_rng(np.random.SeedSequence([seed, tag, dim, 2]))
    return init, ops


def _sbx(p1: np.ndarray, p2: np.ndarray, cfg: GAConfig, lo: float, hi: float, rng: np.random.Generator):
    u = rng.random(p1.shape)
    e = 1.0 / (cfg.sbx_eta + 1.0)
    beta = np.where(u <= 0.5, (2.0 * u) ** e, (1.0 / (2.0 * (1.0 - u))) ** e)
    c1 = 0.5 * ((1.0 + beta) * p1 + (1.0 - beta) * p2)
    c2 = 0.5 * ((1.0 - beta) * p1 + (1.0 + beta) * p2)
    do_x = (rng.random(p1.shape[0]) < cfg.crossover_prob)[:, None]
    gene_swap = rng.random(p1.shape) < 0.5
    c1 = np.where(do_x & gene_swap, c1, p1)
    c2 = np.where(do_x & gene_swap, c2, p2)
    return np.clip(c1, lo, hi), np.clip(c2, lo, hi)


def run_ga(
    landscape: Landscape,
    schedule: ShiftSchedule,
    controller,
    cfg: GAConfig,
    n_gens: int,
    seed: int,
) -> Trace:
    lo, hi, n, d = landscape.lo, landscape.hi, cfg.pop_size, cfg.dim
    if schedule.offsets.shape[1] != d:
        raise ValueError("shift schedule dimension does not match GAConfig.dim")
    rng_init, rng = _rngs(seed, landscape, d)
    X = rng_init.uniform(lo, hi, size=(n, d))
    controller.reset(cfg, landscape)
    tr = Trace()
    view = ObsView(tr)
    stall = 0
    sigma = cfg.mutation_sigma_frac * landscape.width
    for g in range(n_gens):
        err = landscape.error(X - schedule.offset_at(g))
        best = float(err.min())
        if g == 0:
            improved = False
        else:
            prev = tr.best_err[-1]
            improved = prev > SOLVED_ERROR and best < prev * (1.0 - IMPROVEMENT_REL)
        stall = 0 if improved else stall + 1
        tr.gen.append(g)
        tr.epoch.append(schedule.epoch_of(g))
        tr.best_err.append(best)
        tr.mean_log_err.append(float(np.mean(np.log10(err + 1e-12))))
        tr.H.append(population_entropy(X, lo, hi))
        tr.D.append(population_dispersion(X, lo, hi))
        tr.disp.append(fitness_dispersion(err))
        tr.improved.append(improved)
        tr.stall.append(stall)

        act = controller.act(view)
        if not (0.0 <= act.p_mut <= 1.0 and 0.0 <= act.immigrant_frac <= 1.0):
            raise ValueError(f"controller {controller.name} produced invalid action {act}")
        tr.p_mut.append(act.p_mut)
        tr.immigrant_frac.append(act.immigrant_frac)
        if g == n_gens - 1:
            break

        order = np.argsort(err, kind="stable")
        elites = X[order[: cfg.elites]]
        n_child = n - cfg.elites
        n_pairs = (n_child + 1) // 2
        # binary tournaments on current fitness
        a = rng.integers(0, n, size=(2 * n_pairs, 2))
        winners = np.where(err[a[:, 0]] <= err[a[:, 1]], a[:, 0], a[:, 1])
        c1, c2 = _sbx(X[winners[:n_pairs]], X[winners[n_pairs:]], cfg, lo, hi, rng)
        children = np.concatenate([c1, c2])[:n_child]
        mask = rng.random(children.shape) < act.p_mut
        children = np.clip(children + mask * rng.normal(0.0, sigma, size=children.shape), lo, hi)
        n_imm = int(round(act.immigrant_frac * n_child))
        if n_imm:
            children[-n_imm:] = rng.uniform(lo, hi, size=(n_imm, d))
        X = np.concatenate([elites, children])
    return tr
