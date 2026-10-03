"""Evidence-filtered dynamic architecture selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..benchmark.models import ArchitectureBenchmarkResult, Difficulty, RiskLevel, SystemOutcome
from .models import OptimizationConstraints, OptimizationResult, OptimizationWeights
from .selection import select_best


@dataclass(frozen=True)
class RoutingRequest:
    task_type: str
    difficulty: Difficulty | str
    risk_level: RiskLevel | str
    capabilities: frozenset[str]
    budget: float | None
    latency_limit: float | None
    accepted_privacy_classes: frozenset[str] | None = None
    denied_capabilities: frozenset[str] = frozenset()
    available_architecture_ids: frozenset[str] | None = None
    max_risk: float | None = None
    require_verification: bool = False


@dataclass(frozen=True)
class RoutingDecision:
    architecture_id: str | None
    outcome: SystemOutcome
    optimization: OptimizationResult | None
    evidence_ids: tuple[str, ...]
    unavailable_ids: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        payload["optimization"] = self.optimization.to_dict() if self.optimization else None
        return payload


def _matches_evidence(result: ArchitectureBenchmarkResult, request: RoutingRequest) -> bool:
    if result.task_types and request.task_type not in result.task_types:
        return False
    difficulties = result.metadata.get("difficulty_levels")
    if difficulties and str(getattr(request.difficulty, "value", request.difficulty)) not in difficulties:
        return False
    risk_levels = result.metadata.get("risk_levels")
    if risk_levels and str(getattr(request.risk_level, "value", request.risk_level)) not in risk_levels:
        return False
    return True


def select_architecture_for_task(
    request: RoutingRequest,
    measured: list[ArchitectureBenchmarkResult],
    *,
    weights: OptimizationWeights,
) -> RoutingDecision:
    """Select only from measured, task-compatible, available architectures."""

    evidence = [result for result in measured if _matches_evidence(result, request)]
    if not evidence:
        return RoutingDecision(
            architecture_id=None,
            outcome=SystemOutcome.OUT_OF_DISTRIBUTION,
            optimization=None,
            evidence_ids=(),
            unavailable_ids=(),
            reason="no benchmark evidence matches the requested task context",
        )

    available = request.available_architecture_ids
    unavailable_ids = tuple(
        sorted(
            result.architecture_id
            for result in evidence
            if available is not None and result.architecture_id not in available
        )
    )
    usable = [
        result
        for result in evidence
        if available is None or result.architecture_id in available
    ]
    if not usable:
        return RoutingDecision(
            architecture_id=None,
            outcome=SystemOutcome.NO_CALL,
            optimization=None,
            evidence_ids=tuple(sorted(result.architecture_id for result in evidence)),
            unavailable_ids=unavailable_ids,
            reason="all evidence-backed architectures are unavailable",
        )

    candidates = []
    unknown_cost_ids: list[str] = []
    for result in usable:
        try:
            candidates.append(result.to_candidate())
        except ValueError:
            unknown_cost_ids.append(result.architecture_id)
    if not candidates:
        return RoutingDecision(
            architecture_id=None,
            outcome=SystemOutcome.INFEASIBLE,
            optimization=None,
            evidence_ids=tuple(sorted(result.architecture_id for result in evidence)),
            unavailable_ids=tuple(sorted((*unavailable_ids, *unknown_cost_ids))),
            reason="no architecture has complete objective measurements",
        )

    optimization = select_best(
        candidates,
        weights=weights,
        constraints=OptimizationConstraints(
            max_cost=request.budget,
            max_latency=request.latency_limit,
            max_risk=request.max_risk,
            available_capabilities=request.capabilities,
            denied_capabilities=request.denied_capabilities,
            accepted_privacy_classes=request.accepted_privacy_classes,
        ),
    )
    if optimization.selected_id is None:
        return RoutingDecision(
            architecture_id=None,
            outcome=SystemOutcome.INFEASIBLE,
            optimization=optimization,
            evidence_ids=tuple(sorted(result.architecture_id for result in evidence)),
            unavailable_ids=unavailable_ids,
            reason="no measured architecture satisfies the hard constraints",
        )
    return RoutingDecision(
        architecture_id=optimization.selected_id,
        outcome=(SystemOutcome.VERIFY if request.require_verification else SystemOutcome.ANSWER),
        optimization=optimization,
        evidence_ids=tuple(sorted(result.architecture_id for result in evidence)),
        unavailable_ids=unavailable_ids,
        reason="selected from benchmark-compatible feasible architectures",
    )
