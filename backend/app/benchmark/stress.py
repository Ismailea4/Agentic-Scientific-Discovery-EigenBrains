"""Recompute point-estimate routing under explicit architecture stress scenarios."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Sequence

from ..optimization.models import OptimizationWeights
from ..optimization.router import RoutingRequest, select_architecture_for_task
from .models import ArchitectureBenchmarkResult


@dataclass(frozen=True)
class StressScenario:
    name: str
    available_architecture_ids: frozenset[str] | None = None
    budget: float | None = None
    latency_limit: float | None = None
    max_risk: float | None = None


@dataclass(frozen=True)
class StressResult:
    scenario: str
    selected_architecture_id: str | None
    outcome: str
    quality_change: float | None
    cost_change: float | None
    latency_change: float | None
    tail_risk_change: float | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def recompute_stress_scenarios(
    base_request: RoutingRequest,
    measured: Sequence[ArchitectureBenchmarkResult],
    scenarios: Sequence[StressScenario],
    *,
    weights: OptimizationWeights,
) -> list[StressResult]:
    by_id = {result.architecture_id: result for result in measured}
    baseline = select_architecture_for_task(base_request, list(measured), weights=weights)
    baseline_metrics = by_id.get(baseline.architecture_id) if baseline.architecture_id else None
    output: list[StressResult] = []
    for scenario in scenarios:
        request = replace(
            base_request,
            available_architecture_ids=(
                scenario.available_architecture_ids
                if scenario.available_architecture_ids is not None
                else base_request.available_architecture_ids
            ),
            budget=scenario.budget if scenario.budget is not None else base_request.budget,
            latency_limit=(
                scenario.latency_limit if scenario.latency_limit is not None else base_request.latency_limit
            ),
            max_risk=scenario.max_risk if scenario.max_risk is not None else base_request.max_risk,
        )
        decision = select_architecture_for_task(request, list(measured), weights=weights)
        selected = by_id.get(decision.architecture_id) if decision.architecture_id else None
        output.append(
            StressResult(
                scenario=scenario.name,
                selected_architecture_id=decision.architecture_id,
                outcome=decision.outcome.value,
                quality_change=(
                    selected.expected_quality - baseline_metrics.expected_quality
                    if selected and baseline_metrics else None
                ),
                cost_change=(
                    selected.cost - baseline_metrics.cost
                    if selected and baseline_metrics and selected.cost is not None and baseline_metrics.cost is not None
                    else None
                ),
                latency_change=(selected.latency - baseline_metrics.latency if selected and baseline_metrics else None),
                tail_risk_change=(selected.risk - baseline_metrics.risk if selected and baseline_metrics else None),
                reason=decision.reason,
            )
        )
    return output
