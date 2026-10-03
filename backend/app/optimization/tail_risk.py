"""Transparent empirical lower-tail statistics for measured quality scores."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from collections.abc import Sequence


@dataclass(frozen=True)
class TailRiskEstimate:
    score: float | None = None
    alpha: float | None = None
    method: str | None = None
    worst_case_score: float | None = None
    lower_percentile_score: float | None = None
    severe_failure_rate: float | None = None
    cvar_score: float | None = None
    sample_size: int = 0

    def is_specified(self) -> bool:
        return self.score is not None or self.sample_size > 0


def empirical_tail_risk(
    scores: Sequence[float],
    *,
    lower_percentile: float,
    severe_failure_threshold: float,
) -> TailRiskEstimate:
    """Calculate worst case, lower quantile, severe failures, and lower-tail mean.

    Scores must be bounded in ``[0, 1]``. ``cvar_score`` is the empirical mean
    of observations at or below the requested lower quantile; higher is safer.
    The generic ``score`` is ``1 - cvar_score`` so lower remains better in the
    existing optimizer.
    """

    if not 0 < lower_percentile <= 1:
        raise ValueError("lower_percentile must be in (0, 1]")
    if not 0 <= severe_failure_threshold <= 1:
        raise ValueError("severe_failure_threshold must be in [0, 1]")
    if not scores:
        return TailRiskEstimate(alpha=lower_percentile, method="empirical", sample_size=0)
    if any(score < 0 or score > 1 for score in scores):
        raise ValueError("quality scores must be in [0, 1]")

    ordered = sorted(float(score) for score in scores)
    quantile_index = min(len(ordered) - 1, floor((len(ordered) - 1) * lower_percentile))
    quantile = ordered[quantile_index]
    tail = [score for score in ordered if score <= quantile]
    cvar = sum(tail) / len(tail)
    severe = sum(score <= severe_failure_threshold for score in ordered) / len(ordered)
    return TailRiskEstimate(
        score=1.0 - cvar,
        alpha=lower_percentile,
        method="empirical_lower_tail",
        worst_case_score=ordered[0],
        lower_percentile_score=quantile,
        severe_failure_rate=severe,
        cvar_score=cvar,
        sample_size=len(ordered),
    )
