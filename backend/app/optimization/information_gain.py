"""Explicit value-of-information gate for optional calls."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class InformationGainDecision:
    invoke: bool
    expected_value_of_information: float
    incremental_cost: float
    incremental_latency: float
    cost_weight: float
    latency_weight: float
    net_value: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_information_gain(
    *,
    expected_value_of_information: float,
    incremental_cost: float,
    incremental_latency: float,
    cost_weight: float,
    latency_weight: float,
) -> InformationGainDecision:
    values = {
        "expected_value_of_information": expected_value_of_information,
        "incremental_cost": incremental_cost,
        "incremental_latency": incremental_latency,
        "cost_weight": cost_weight,
        "latency_weight": latency_weight,
    }
    if any(value < 0 for value in values.values()):
        raise ValueError("information-gain inputs and weights must be >= 0")
    penalty = cost_weight * incremental_cost + latency_weight * incremental_latency
    net = expected_value_of_information - penalty
    invoke = net > 0
    return InformationGainDecision(
        invoke=invoke,
        expected_value_of_information=expected_value_of_information,
        incremental_cost=incremental_cost,
        incremental_latency=incremental_latency,
        cost_weight=cost_weight,
        latency_weight=latency_weight,
        net_value=net,
        reason=(
            "expected information value exceeds incremental cost and latency"
            if invoke
            else "incremental cost and latency are not justified by expected information value"
        ),
    )


def evaluate_additional_agent_value(
    *,
    estimated_quality_improvement: float,
    uncertainty: float,
    incremental_cost: float,
    incremental_latency: float,
    cost_weight: float,
    latency_weight: float,
) -> InformationGainDecision:
    """Practical value-of-information proxy from measured tuning inputs."""

    if not 0 <= uncertainty <= 1:
        raise ValueError("uncertainty must be in [0, 1]")
    if estimated_quality_improvement < 0:
        raise ValueError("estimated_quality_improvement must be >= 0")
    return evaluate_information_gain(
        expected_value_of_information=estimated_quality_improvement * uncertainty,
        incremental_cost=incremental_cost,
        incremental_latency=incremental_latency,
        cost_weight=cost_weight,
        latency_weight=latency_weight,
    )
