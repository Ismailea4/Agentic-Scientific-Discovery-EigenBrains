"""Small provenance-preserving Beta update for bounded benchmark scores."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class BayesianEstimate:
    prior_source: str
    prior_alpha: float
    prior_beta: float
    challenge_observations: int
    observed_score_sum: float
    posterior_alpha: float
    posterior_beta: float
    posterior_estimate: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def update_bounded_quality(
    *,
    prior_source: str,
    prior_alpha: float,
    prior_beta: float,
    observed_scores: list[float],
) -> BayesianEstimate:
    if prior_alpha <= 0 or prior_beta <= 0:
        raise ValueError("Beta prior parameters must be > 0")
    if any(score < 0 or score > 1 for score in observed_scores):
        raise ValueError("observed scores must be in [0, 1]")
    successes = sum(observed_scores)
    failures = len(observed_scores) - successes
    posterior_alpha = prior_alpha + successes
    posterior_beta = prior_beta + failures
    return BayesianEstimate(
        prior_source=prior_source,
        prior_alpha=prior_alpha,
        prior_beta=prior_beta,
        challenge_observations=len(observed_scores),
        observed_score_sum=successes,
        posterior_alpha=posterior_alpha,
        posterior_beta=posterior_beta,
        posterior_estimate=posterior_alpha / (posterior_alpha + posterior_beta),
    )
