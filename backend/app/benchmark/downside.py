"""Empirical loss, downside, VaR-like, and CVaR-like diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import fmean
from typing import Any, Sequence

from .statistics import ConfidenceInterval, bootstrap_confidence_interval


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * probability)))
    return ordered[index]


@dataclass(frozen=True)
class DownsideRisk:
    sample_size: int
    loss_mean: float
    downside_semivariance: float
    downside_deviation: float
    var_loss: dict[str, float]
    cvar_loss: dict[str, float]
    cvar_intervals: dict[str, ConfidenceInterval | None]
    worst_decile_quality: float
    severe_failure_probability: float
    unstable_levels: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def empirical_downside_risk(
    qualities: Sequence[float],
    *,
    severe_failure_threshold: float,
    alphas: tuple[float, ...] = (0.90, 0.95),
    minimum_tail_observations: int = 5,
    confidence_level: float = 0.95,
    resamples: int = 1000,
    seed: int = 0,
) -> DownsideRisk:
    if not qualities or any(not 0 <= value <= 1 for value in qualities):
        raise ValueError("qualities must be a non-empty sequence in [0, 1]")
    if any(not 0 < alpha < 1 for alpha in alphas):
        raise ValueError("CVaR alpha values must be in (0, 1)")
    losses = [1.0 - float(value) for value in qualities]
    mean_loss = fmean(losses)
    semivariance = fmean(max(loss - mean_loss, 0.0) ** 2 for loss in losses)
    var_loss: dict[str, float] = {}
    cvar_loss: dict[str, float] = {}
    cvar_intervals: dict[str, ConfidenceInterval | None] = {}
    unstable: list[str] = []
    for offset, alpha in enumerate(alphas):
        label = f"{alpha:.2f}"
        threshold = _quantile(losses, alpha)
        tail = [loss for loss in losses if loss >= threshold]
        var_loss[label] = threshold
        cvar_loss[label] = fmean(tail)
        if len(tail) < minimum_tail_observations:
            unstable.append(label)
            cvar_intervals[label] = None
        else:
            def cvar_statistic(sample: Sequence[float], *, level: float = alpha) -> float:
                sample_threshold = _quantile(sample, level)
                return fmean(value for value in sample if value >= sample_threshold)

            cvar_intervals[label] = bootstrap_confidence_interval(
                losses,
                statistic=cvar_statistic,
                confidence_level=confidence_level,
                resamples=resamples,
                seed=seed + offset,
            )
    worst_count = max(1, round(len(qualities) * 0.1))
    return DownsideRisk(
        sample_size=len(qualities),
        loss_mean=mean_loss,
        downside_semivariance=semivariance,
        downside_deviation=semivariance**0.5,
        var_loss=var_loss,
        cvar_loss=cvar_loss,
        cvar_intervals=cvar_intervals,
        worst_decile_quality=fmean(sorted(float(value) for value in qualities)[:worst_count]),
        severe_failure_probability=sum(value <= severe_failure_threshold for value in qualities) / len(qualities),
        unstable_levels=tuple(unstable),
    )
