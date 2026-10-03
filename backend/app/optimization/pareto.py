"""Pareto dominance for architecture objectives.

A candidate dominates another when it is no worse on quality, cost, latency,
and risk, and strictly better on at least one. Higher quality is better.
Lower cost, latency, and risk are better. Equal candidates do not dominate
each other.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..core.logging import log_event
from .models import ArchitectureCandidate


@dataclass(frozen=True)
class ParetoResult:
    frontier: tuple[str, ...]
    dominated: tuple[str, ...]


def _ensure_unique(candidates: Sequence[ArchitectureCandidate]) -> None:
    identifiers = [candidate.id for candidate in candidates]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("architecture ids must be unique")


def dominates(better: ArchitectureCandidate, worse: ArchitectureCandidate) -> bool:
    left = better.metrics
    right = worse.metrics
    not_worse = (
        left.quality >= right.quality
        and left.cost <= right.cost
        and left.latency <= right.latency
        and left.risk <= right.risk
    )
    strictly_better = (
        left.quality > right.quality
        or left.cost < right.cost
        or left.latency < right.latency
        or left.risk < right.risk
    )
    return not_worse and strictly_better


def pareto_frontier(candidates: Sequence[ArchitectureCandidate]) -> ParetoResult:
    """Return sorted ids of non-dominated and dominated candidates."""

    _ensure_unique(candidates)
    frontier: list[str] = []
    dominated: list[str] = []
    for candidate in candidates:
        beaten = any(
            other.id != candidate.id and dominates(other, candidate)
            for other in candidates
        )
        if beaten:
            dominated.append(candidate.id)
        else:
            frontier.append(candidate.id)
    return ParetoResult(frontier=tuple(sorted(frontier)), dominated=tuple(sorted(dominated)))


def log_pareto_result(result: ParetoResult) -> None:
    """Log a classification. This does not choose an architecture."""

    log_event(
        "optimizer.started",
        candidate_count=len(result.frontier) + len(result.dominated),
    )
    for identifier in result.frontier:
        log_event(
            "optimizer.candidate_evaluated",
            candidate_id=identifier,
            pareto_state="non_dominated",
        )
    for identifier in result.dominated:
        log_event(
            "optimizer.candidate_evaluated",
            candidate_id=identifier,
            pareto_state="dominated",
        )
