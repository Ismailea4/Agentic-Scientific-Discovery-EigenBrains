"""Portfolio-inspired workload allocation diagnostics, not literal finance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

from .covariance import ErrorCovarianceMatrix


@dataclass(frozen=True)
class ComputationalAllocation:
    labels: tuple[str, ...]
    routing_probabilities: tuple[float, ...]
    expected_quality: float
    covariance_risk: float
    normalized_cost: float
    normalized_latency: float
    utility: float
    interpretation: str = "routing probabilities over a workload"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_computational_allocation(
    *,
    weights: Sequence[float],
    mean_quality: Sequence[float],
    mean_cost: Sequence[float],
    mean_latency: Sequence[float],
    covariance: ErrorCovarianceMatrix,
    allowed_budget: float,
    latency_limit: float,
    lambda_risk: float,
    eta_cost: float,
    rho_latency: float,
) -> ComputationalAllocation:
    size = len(covariance.labels)
    vectors = (weights, mean_quality, mean_cost, mean_latency)
    if any(len(vector) != size for vector in vectors):
        raise ValueError("allocation vectors must align to covariance labels")
    if any(weight < 0 for weight in weights) or abs(sum(weights) - 1.0) > 1e-9:
        raise ValueError("routing probabilities must be non-negative and sum to one")
    if allowed_budget <= 0 or latency_limit <= 0:
        raise ValueError("budget and latency normalization limits must be > 0")
    if any(value < 0 for value in (lambda_risk, eta_cost, rho_latency)):
        raise ValueError("allocation penalty weights must be >= 0")
    expected_quality = sum(weight * quality for weight, quality in zip(weights, mean_quality, strict=True))
    expected_cost = sum(weight * cost for weight, cost in zip(weights, mean_cost, strict=True))
    expected_latency = sum(weight * latency for weight, latency in zip(weights, mean_latency, strict=True))
    covariance_risk = sum(
        weights[row] * covariance.matrix[row][column] * weights[column]
        for row in range(size)
        for column in range(size)
    )
    normalized_cost = expected_cost / allowed_budget
    normalized_latency = expected_latency / latency_limit
    utility = (
        expected_quality
        - lambda_risk * covariance_risk
        - eta_cost * normalized_cost
        - rho_latency * normalized_latency
    )
    return ComputationalAllocation(
        labels=covariance.labels,
        routing_probabilities=tuple(float(weight) for weight in weights),
        expected_quality=expected_quality,
        covariance_risk=covariance_risk,
        normalized_cost=normalized_cost,
        normalized_latency=normalized_latency,
        utility=utility,
    )
