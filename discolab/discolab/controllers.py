"""Mutation-control policies. Each sees only the observable history (ga.ObsView).

B0  fixed           p = 1/d                                    (standard default)
B1  stall-adaptive  p rises linearly with generations since last improvement
B2  entropy-level   p rises as entropy falls below its initial value
B3  predictive      p = p_min + (p_max - p_min) * r_t, r_t = P(stagnation onset | x_t)
                    from a logistic model frozen after fitting on development data
B4a hypermutation   p = p_max for a fixed window after an observed fitness jump
                    (triggered hypermutation, Cobb 1990)
B4b immigrants      a fixed fraction of offspring replaced by uniform random points
                    every generation (random immigrants, Grefenstette 1992)
B5  hybrid          rate-matched base rate 0.8/d plus predictive timing: a burst to
                    p_max for 5 generations when the frozen risk model's estimate
                    crosses 0.5 (rising edge), then back to the base rate
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .features import feature_matrix
from .ga import Action, GAConfig
from .landscapes import Landscape

P_MIN_MULT = 0.5  # p_min = 0.5 / d
P_MAX_MULT = 4.0  # p_max = 4 / d


class Controller:
    name = "base"

    def reset(self, cfg: GAConfig, landscape: Landscape) -> None:
        self.d = cfg.dim
        self.p_base = 1.0 / cfg.dim
        self.p_min = P_MIN_MULT / cfg.dim
        self.p_max = min(1.0, P_MAX_MULT / cfg.dim)

    def act(self, obs) -> Action:  # pragma: no cover - interface
        raise NotImplementedError


class Fixed(Controller):
    name = "B0_fixed"

    def __init__(self, mult: float = 1.0):
        self.mult = mult

    def act(self, obs) -> Action:
        return Action(p_mut=min(1.0, self.mult / self.d))


class StallAdaptive(Controller):
    name = "B1_stall"

    def __init__(self, ramp: int = 10):
        self.ramp = ramp

    def act(self, obs) -> Action:
        frac = min(1.0, obs.stall[-1] / self.ramp)
        return Action(p_mut=self.p_min + (self.p_max - self.p_min) * frac)


class EntropyLevel(Controller):
    name = "B2_entropy"

    def act(self, obs) -> Action:
        h0 = max(obs.H[0], 1e-9)
        frac = float(np.clip(1.0 - obs.H[-1] / h0, 0.0, 1.0))
        return Action(p_mut=self.p_min + (self.p_max - self.p_min) * frac)


@dataclass(frozen=True)
class LogisticModel:
    feature_set: str
    names: tuple[str, ...]
    mean: np.ndarray
    scale: np.ndarray
    coef: np.ndarray
    intercept: float

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        z = ((X - self.mean) / self.scale) @ self.coef + self.intercept
        return 1.0 / (1.0 + np.exp(-np.clip(z, -40, 40)))

    def to_dict(self) -> dict:
        return {
            "feature_set": self.feature_set,
            "names": list(self.names),
            "mean": self.mean.tolist(),
            "scale": self.scale.tolist(),
            "coef": self.coef.tolist(),
            "intercept": self.intercept,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LogisticModel":
        return cls(
            d["feature_set"], tuple(d["names"]), np.asarray(d["mean"]), np.asarray(d["scale"]),
            np.asarray(d["coef"]), float(d["intercept"]),
        )


class Predictive(Controller):
    name = "B3_predictive"

    def __init__(self, model: LogisticModel):
        self.model = model

    def act(self, obs) -> Action:
        x = feature_matrix(obs, self.model.names)[-1:]
        r = float(self.model.predict_proba(x)[0])
        return Action(p_mut=self.p_min + (self.p_max - self.p_min) * r)


class HybridPredictive(Controller):
    """B5: keep the rate that recovers best on average and add predictive timing.

    Motivated by lab evidence: the risk-driven controller (B3) and a fixed rate
    matched to its average fail on largely different runs, so their mechanisms
    may be complementary. Constants are fixed before testing.
    """

    name = "B5_hybrid"
    BASE_MULT = 0.8
    THRESHOLD = 0.5
    BURST = 5

    def __init__(self, model: "LogisticModel"):
        self.model = model

    def reset(self, cfg, landscape):
        super().reset(cfg, landscape)
        self.base = min(1.0, self.BASE_MULT / cfg.dim)
        self.until = -1
        self.prev_risk = 0.0

    def act(self, obs) -> Action:
        g = obs.gen[-1]
        r = float(self.model.predict_proba(feature_matrix(obs, self.model.names)[-1:])[0])
        if r >= self.THRESHOLD > self.prev_risk:  # rising edge: predicted stagnation onset
            self.until = g + self.BURST
        self.prev_risk = r
        return Action(p_mut=self.p_max if g < self.until else self.base)


class Hypermutation(Controller):
    name = "B4a_hypermutation"

    def __init__(self, window: int = 10):
        self.window = window

    def reset(self, cfg, landscape):
        super().reset(cfg, landscape)
        self.until = -1

    def act(self, obs) -> Action:
        g = obs.gen[-1]
        # With elitism, best error can only rise if the landscape changed.
        if g > 0 and obs.best_err[-1] > obs.best_err[-2] * (1.0 + 1e-9) + 1e-12:
            self.until = g + self.window
        return Action(p_mut=self.p_max if g < self.until else self.p_base)


class RandomImmigrants(Controller):
    name = "B4b_immigrants"

    def __init__(self, frac: float = 0.1):
        self.frac = frac

    def act(self, obs) -> Action:
        return Action(p_mut=self.p_base, immigrant_frac=self.frac)


def make_controller(name: str, model: LogisticModel | None = None) -> Controller:
    if name == "B0_fixed":
        return Fixed()
    if name == "B1_stall":
        return StallAdaptive()
    if name == "B2_entropy":
        return EntropyLevel()
    if name == "B3_predictive":
        if model is None:
            raise ValueError("B3_predictive requires a fitted LogisticModel")
        return Predictive(model)
    if name == "B4a_hypermutation":
        return Hypermutation()
    if name == "B5_hybrid":
        if model is None:
            raise ValueError("B5_hybrid requires a fitted LogisticModel")
        return HybridPredictive(model)
    if name == "B4b_immigrants":
        return RandomImmigrants()
    if name.startswith("B0_fixed_x"):
        return Fixed(mult=float(name.removeprefix("B0_fixed_x")))
    raise ValueError(f"unknown controller {name!r}")


CONTROLLERS = ("B0_fixed", "B1_stall", "B2_entropy", "B3_predictive", "B4a_hypermutation", "B4b_immigrants")
