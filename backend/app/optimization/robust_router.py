"""Confidence-bound routing over measured discrete architectures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

from ..benchmark.bounds import ArchitectureBounds
from ..benchmark.models import ArchitectureBenchmarkResult, SystemOutcome
from .models import (
    ArchitectureCandidate,
    ArchitectureMetrics,
    OptimizationWeights,
)
from .router import RoutingRequest


@dataclass(frozen=True)
class RobustRoutingDecision:
    architecture_id: str | None
    outcome: SystemOutcome
    conservative_utility: float | None
    feasible_ids: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]
    confidence_level: float | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        return payload


def _matches(result: ArchitectureBenchmarkResult, request: RoutingRequest) -> bool:
    if result.task_types and request.task_type not in result.task_types:
        return False
    difficulty = str(getattr(request.difficulty, "value", request.difficulty))
    risk = str(getattr(request.risk_level, "value", request.risk_level))
    levels = result.metadata.get("difficulty_levels")
    risks = result.metadata.get("risk_levels")
    return not (levels and difficulty not in levels) and not (risks and risk not in risks)


def _hard_violations(candidate: ArchitectureCandidate, request: RoutingRequest) -> list[str]:
    reasons: list[str] = []
    if request.budget is not None and candidate.metrics.cost > request.budget:
        reasons.append("cost UCB above budget")
    if request.latency_limit is not None and candidate.metrics.latency > request.latency_limit:
        reasons.append("latency UCB above limit")
    if request.max_risk is not None and candidate.metrics.risk > request.max_risk:
        reasons.append("risk UCB above maximum")
    for capability in candidate.required_capabilities:
        if capability not in request.capabilities:
            reasons.append(f"missing capability '{capability}'")
        if capability in request.denied_capabilities:
            reasons.append(f"denied capability '{capability}'")
    if (
        request.accepted_privacy_classes is not None
        and candidate.privacy_class not in request.accepted_privacy_classes
    ):
        reasons.append("privacy class is not accepted")
    return reasons


def select_architecture_robust(
    request: RoutingRequest,
    measured: Sequence[ArchitectureBenchmarkResult],
    bounds: Sequence[ArchitectureBounds],
    *,
    weights: OptimizationWeights,
) -> RobustRoutingDecision:
    weights.validate()
    if weights.eta_cost > 0 and request.budget is None:
        raise ValueError("robust cost utility requires an explicit budget normalization limit")
    if weights.rho_latency > 0 and request.latency_limit is None:
        raise ValueError("robust latency utility requires an explicit latency normalization limit")
    bounds_by_id = {item.architecture_id: item for item in bounds}
    measured_by_id = {item.architecture_id: item for item in measured if _matches(item, request)}
    candidates: list[ArchitectureCandidate] = []
    confidence_levels: set[float] = set()
    incomplete: list[tuple[str, str]] = []
    for identifier, result in measured_by_id.items():
        if request.available_architecture_ids is not None and identifier not in request.available_architecture_ids:
            incomplete.append((identifier, "architecture unavailable"))
            continue
        bound = bounds_by_id.get(identifier)
        if bound is None or bound.quality is None or bound.cost is None:
            incomplete.append((identifier, "complete confidence bounds unavailable"))
            continue
        confidence_levels.add(bound.quality.confidence_level)
        candidates.append(
            ArchitectureCandidate(
                id=identifier,
                name=result.architecture_name,
                metrics=ArchitectureMetrics(
                    quality=bound.quality.lower,
                    cost=bound.cost.upper,
                    latency=bound.latency.upper,
                    risk=bound.severe_failure.upper,
                    failure_rate=bound.failure.upper,
                ),
                agents=tuple(result.metadata.get("agents", ())),
                required_capabilities=result.required_capabilities,
                privacy_class=result.privacy_class,
                metadata={**result.metadata, "evidence_state": "BENCHMARK", "routing_mode": "robust"},
            )
        )
    if not measured_by_id:
        return RobustRoutingDecision(None, SystemOutcome.OUT_OF_DISTRIBUTION, None, (), (), None, "no matching benchmark evidence")
    if not candidates:
        return RobustRoutingDecision(None, SystemOutcome.INFEASIBLE, None, (), tuple(sorted(incomplete)), None, "no candidate has complete conservative bounds")
    rejected = [
        (candidate.id, "; ".join(violations))
        for candidate in candidates
        if (violations := _hard_violations(candidate, request))
    ]
    rejected_ids = {identifier for identifier, _ in rejected}
    feasible = [candidate for candidate in candidates if candidate.id not in rejected_ids]
    if not feasible:
        return RobustRoutingDecision(
            None,
            SystemOutcome.INFEASIBLE,
            None,
            (),
            tuple(sorted((*incomplete, *rejected))),
            next(iter(confidence_levels)) if len(confidence_levels) == 1 else None,
            "no candidate satisfies conservative hard constraints",
        )

    def utility(candidate: ArchitectureCandidate) -> float:
        normalized_cost = candidate.metrics.cost / request.budget if request.budget else 0.0
        normalized_latency = candidate.metrics.latency / request.latency_limit if request.latency_limit else 0.0
        return (
            weights.quality_weight * candidate.metrics.quality
            - weights.lambda_risk * candidate.metrics.risk
            - weights.eta_cost * normalized_cost
            - weights.rho_latency * normalized_latency
        )

    selected = sorted(
        feasible,
        key=lambda candidate: (
            -utility(candidate),
            -candidate.metrics.quality,
            candidate.metrics.cost,
            candidate.metrics.latency,
            candidate.id,
        ),
    )[0]
    return RobustRoutingDecision(
        architecture_id=selected.id,
        outcome=SystemOutcome.VERIFY if request.require_verification else SystemOutcome.ANSWER,
        conservative_utility=utility(selected),
        feasible_ids=tuple(sorted(candidate.id for candidate in feasible)),
        rejected=tuple(sorted((*incomplete, *rejected))),
        confidence_level=next(iter(confidence_levels)) if len(confidence_levels) == 1 else None,
        reason="selected using lower quality and upper risk/cost/latency confidence bounds",
    )
