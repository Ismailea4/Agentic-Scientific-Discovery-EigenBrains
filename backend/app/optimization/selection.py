"""Feasibility filter, then Pareto, then deterministic utility selection.

Security and numeric limits remove candidates before utility is computed.
A higher utility never readmits a candidate that failed a hard constraint.
"""

from __future__ import annotations

from collections.abc import Sequence

from .models import (
    ArchitectureCandidate,
    OptimizationConstraints,
    OptimizationResult,
    OptimizationWeights,
)
from ..core.logging import log_event
from .pareto import pareto_frontier
from .utility import weighted_utility


def _violations(
    candidate: ArchitectureCandidate, constraints: OptimizationConstraints
) -> list[str]:
    metrics = candidate.metrics
    reasons: list[str] = []
    if constraints.min_quality is not None and metrics.quality < constraints.min_quality:
        reasons.append("quality below minimum")
    if constraints.max_cost is not None and metrics.cost > constraints.max_cost:
        reasons.append("cost above maximum")
    if constraints.max_latency is not None and metrics.latency > constraints.max_latency:
        reasons.append("latency above maximum")
    if constraints.max_risk is not None and metrics.risk > constraints.max_risk:
        reasons.append("risk above maximum")
    if constraints.max_failure_rate is not None:
        if metrics.failure_rate is None:
            reasons.append("failure rate is unknown")
        elif metrics.failure_rate > constraints.max_failure_rate:
            reasons.append("failure rate above maximum")

    if constraints.available_capabilities is not None:
        for capability in candidate.required_capabilities:
            if capability not in constraints.available_capabilities:
                reasons.append(f"missing capability '{capability}'")
    for capability in candidate.required_capabilities:
        if capability in constraints.denied_capabilities:
            reasons.append(f"denied capability '{capability}'")
    if constraints.accepted_privacy_classes is not None:
        if candidate.privacy_class not in constraints.accepted_privacy_classes:
            reasons.append("privacy class is not accepted")
    return reasons


def _selection_key(
    candidate: ArchitectureCandidate, weights: OptimizationWeights
) -> tuple[float, float, float, float, float, str]:
    """Lower sorts first. Utility and quality are negated so higher wins."""

    score = weighted_utility(candidate.metrics, weights)
    metrics = candidate.metrics
    return (
        -score,
        -metrics.quality,
        metrics.cost,
        metrics.latency,
        metrics.risk,
        candidate.id,
    )


def select_best(
    candidates: Sequence[ArchitectureCandidate],
    weights: OptimizationWeights | None = None,
    constraints: OptimizationConstraints | None = None,
) -> OptimizationResult:
    """Select one feasible non-dominated architecture.

    Ties break by higher quality, then lower cost, latency, and risk, then
    identifier. The result lists every rejection reason so the choice can be
    audited. An empty feasible set selects nothing.
    """

    chosen_weights = weights or OptimizationWeights()
    chosen_weights.validate()
    chosen_constraints = constraints or OptimizationConstraints()

    identifiers = [candidate.id for candidate in candidates]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("architecture ids must be unique")

    rejected: list[tuple[str, str]] = []
    feasible: list[ArchitectureCandidate] = []
    for candidate in candidates:
        violations = _violations(candidate, chosen_constraints)
        if violations:
            rejected.append((candidate.id, "; ".join(violations)))
        else:
            feasible.append(candidate)

    classified = pareto_frontier(feasible)
    frontier_ids = set(classified.frontier)
    frontier = [candidate for candidate in feasible if candidate.id in frontier_ids]

    reasons: list[str] = []
    selected_id: str | None = None
    selected_utility: float | None = None
    best: ArchitectureCandidate | None = None
    if not frontier:
        reasons.append("no architecture satisfied the hard constraints")
    else:
        best = sorted(frontier, key=lambda candidate: _selection_key(candidate, chosen_weights))[0]
        selected_id = best.id
        selected_utility = weighted_utility(best.metrics, chosen_weights)
        reasons.append(
            f"selected '{best.id}' from the feasible non-dominated set"
        )

    log_event("optimizer.started", candidate_count=len(candidates))
    for candidate_id, reason in rejected:
        log_event(
            "optimizer.candidate_evaluated",
            candidate_id=candidate_id,
            pareto_state="infeasible",
            rejected_reason=reason,
        )
    for candidate_id in classified.dominated:
        log_event(
            "optimizer.candidate_evaluated",
            candidate_id=candidate_id,
            pareto_state="dominated",
        )
    for candidate_id in classified.frontier:
        log_event(
            "optimizer.candidate_evaluated",
            candidate_id=candidate_id,
            pareto_state="non_dominated",
        )
    log_event(
        "optimizer.selected",
        selected_candidate=selected_id,
        quality_score=None if best is None else best.metrics.quality,
        risk_score=None if best is None else best.metrics.risk,
    )

    return OptimizationResult(
        selected_id=selected_id,
        utility=selected_utility,
        feasible_ids=tuple(sorted(candidate.id for candidate in feasible)),
        frontier_ids=classified.frontier,
        dominated_ids=classified.dominated,
        rejected=tuple(sorted(rejected)),
        reasons=tuple(reasons),
    )


# Backwards-compatible alias for the pre-rename name.
select_architecture = select_best
