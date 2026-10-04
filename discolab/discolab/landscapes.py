"""Benchmark landscapes in centered form, plus controlled translations.

Every landscape is stored as ``g(z) = f(z + o) - f*`` so that the global
minimum is exactly 0 at z = 0. A translated (dynamic) problem evaluates
``g(x - s_t)``; its optimum is therefore known exactly: ``x*_t = s_t`` with
error 0. "Error" everywhere in discolab means ``g >= 0``.

Schwefel is deliberately excluded: its optimum sits near the domain corner
and the function keeps decreasing outside the box, so a translated version
is not well posed without extra boundary handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

Array = np.ndarray


def _rastrigin(z: Array) -> Array:
    return 10.0 * z.shape[-1] + np.sum(z * z - 10.0 * np.cos(2.0 * np.pi * z), axis=-1)


def _ackley(z: Array) -> Array:
    d = z.shape[-1]
    a = -20.0 * np.exp(-0.2 * np.sqrt(np.sum(z * z, axis=-1) / d))
    b = -np.exp(np.sum(np.cos(2.0 * np.pi * z), axis=-1) / d)
    return a + b + 20.0 + np.e


def _griewank(z: Array) -> Array:
    i = np.sqrt(np.arange(1, z.shape[-1] + 1, dtype=float))
    return 1.0 + np.sum(z * z, axis=-1) / 4000.0 - np.prod(np.cos(z / i), axis=-1)


def _levy(z: Array) -> Array:
    # Levy is defined with optimum at x = 1; centered by z = x - 1, so w = 1 + z/4.
    w = 1.0 + z / 4.0
    head = np.sin(np.pi * w[..., 0]) ** 2
    mid = np.sum((w[..., :-1] - 1.0) ** 2 * (1.0 + 10.0 * np.sin(np.pi * w[..., :-1] + 1.0) ** 2), axis=-1)
    tail = (w[..., -1] - 1.0) ** 2 * (1.0 + np.sin(2.0 * np.pi * w[..., -1]) ** 2)
    return head + mid + tail


_ST_XSTAR = -2.903534027771177  # per-dimension minimiser of Styblinski-Tang


def _styblinski_tang(z: Array) -> Array:
    x = z + _ST_XSTAR
    f = 0.5 * np.sum(x**4 - 16.0 * x**2 + 5.0 * x, axis=-1)
    f_star = 0.5 * z.shape[-1] * (_ST_XSTAR**4 - 16.0 * _ST_XSTAR**2 + 5.0 * _ST_XSTAR)
    return f - f_star


@dataclass(frozen=True)
class Landscape:
    """A centered benchmark: minimum value 0 at z = 0 inside [lo, hi]^d."""

    name: str
    lo: float
    hi: float
    fn: Callable[[Array], Array]
    reference: str

    @property
    def width(self) -> float:
        return self.hi - self.lo

    def error(self, z: Array) -> Array:
        # Clamp tiny negative values from floating-point cancellation.
        return np.maximum(self.fn(z), 0.0)


LANDSCAPES: dict[str, Landscape] = {
    "rastrigin": Landscape("rastrigin", -5.12, 5.12, _rastrigin, "Rastrigin (1974); Muehlenbein et al. (1991)"),
    "ackley": Landscape("ackley", -32.768, 32.768, _ackley, "Ackley (1987)"),
    "griewank": Landscape("griewank", -600.0, 600.0, _griewank, "Griewank (1981)"),
    "levy": Landscape("levy", -10.0, 10.0, _levy, "Levy & Montalvo (1985)"),
    "styblinski_tang": Landscape(
        "styblinski_tang", -5.0, 5.0, _styblinski_tang, "Styblinski & Tang (1990)"
    ),
}


def get_landscape(name: str) -> Landscape:
    try:
        return LANDSCAPES[name]
    except KeyError as exc:
        raise ValueError(f"unknown landscape {name!r}; known: {sorted(LANDSCAPES)}") from exc


@dataclass(frozen=True)
class ShiftSchedule:
    """Piecewise-constant translation s_k, one per epoch, drawn from a seeded RNG.

    Shifts move the optimum by ``severity * half_width`` in a random direction
    and are clipped to ``max_offset * half_width`` per coordinate so the
    optimum always stays well inside the search box.
    """

    offsets: Array  # shape (n_epochs, d)
    period_gens: int

    def offset_at(self, generation: int) -> Array:
        epoch = min(generation // self.period_gens, len(self.offsets) - 1)
        return self.offsets[epoch]

    def epoch_of(self, generation: int) -> int:
        return min(generation // self.period_gens, len(self.offsets) - 1)


def make_shift_schedule(
    landscape: Landscape,
    dim: int,
    n_epochs: int,
    period_gens: int,
    severity: float,
    seed: int,
    max_offset: float = 0.5,
) -> ShiftSchedule:
    if n_epochs < 1 or period_gens < 1:
        raise ValueError("n_epochs and period_gens must be >= 1")
    if not 0.0 <= severity <= 1.0:
        raise ValueError("severity must be in [0, 1]")
    rng = np.random.default_rng(np.random.SeedSequence([seed, 0x5F17]))
    half = landscape.width / 2.0
    bound = max_offset * half
    offsets = np.empty((n_epochs, dim))
    offsets[0] = rng.uniform(-bound, bound, size=dim)
    for k in range(1, n_epochs):
        u = rng.normal(size=dim)
        u /= np.linalg.norm(u)
        offsets[k] = np.clip(offsets[k - 1] + severity * half * u, -bound, bound)
    return ShiftSchedule(offsets=offsets, period_gens=period_gens)


def recovery_epsilon(landscape: Landscape, dim: int, fraction: float, n_samples: int = 10_000) -> float:
    """Landscape-intrinsic recovery threshold, independent of any algorithm.

    ``fraction`` times the median error of uniformly random points in the box
    (fixed seed). Using a property of the landscape rather than an algorithm's
    performance avoids calibrating the metric on the methods being compared.
    """
    rng = np.random.default_rng(12345)
    z = rng.uniform(landscape.lo, landscape.hi, size=(n_samples, dim))
    return float(fraction * np.median(landscape.error(z)))
