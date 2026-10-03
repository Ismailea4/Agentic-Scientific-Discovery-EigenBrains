"""Confidence-bound racing decisions under explicit sample and budget limits."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from .bounds import ArchitectureBounds, robust_frontier, robustly_dominates


@dataclass(frozen=True)
class RacingDecision:
    eliminated_ids: tuple[str, ...]
    allocate_more_ids: tuple[str, ...]
    reasons: tuple[tuple[str, str], ...]
    stop: bool
    stop_reason: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = [{"architecture_id": key, "reason": value} for key, value in self.reasons]
        return payload


def confidence_bound_race(
    bounds: Sequence[ArchitectureBounds],
    *,
    sample_counts: Mapping[str, int],
    minimum_sample: int,
    confidence_width_target: float,
    calls_remaining: int,
    tail_stability: Mapping[str, bool] | None = None,
) -> RacingDecision:
    if minimum_sample < 1 or confidence_width_target <= 0 or calls_remaining < 0:
        raise ValueError("invalid racing configuration")
    by_id = {item.architecture_id: item for item in bounds}
    if set(sample_counts) != set(by_id):
        raise ValueError("sample_counts must cover every candidate exactly")
    reasons: list[tuple[str, str]] = []
    under_sampled = sorted(
        identifier for identifier, count in sample_counts.items() if count < minimum_sample
    )
    if under_sampled:
        for identifier in under_sampled:
            reasons.append((identifier, "minimum sample not reached"))
        return RacingDecision((), tuple(under_sampled), tuple(reasons), calls_remaining == 0, "budget exhausted" if calls_remaining == 0 else "collect minimum samples")

    eliminated = sorted(
        candidate.architecture_id
        for candidate in bounds
        if any(
            other.architecture_id != candidate.architecture_id
            and robustly_dominates(other, candidate)
            for other in bounds
        )
    )
    frontier = robust_frontier(bounds)
    allocate: list[str] = []
    for identifier in frontier.frontier_ids:
        item = by_id[identifier]
        quality_width = float("inf") if item.quality is None else item.quality.upper - item.quality.lower
        tail_uncertain = tail_stability is not None and not tail_stability.get(identifier, False)
        if quality_width > confidence_width_target or identifier in frontier.uncertain_ids or tail_uncertain:
            allocate.append(identifier)
            reason_parts = []
            if quality_width > confidence_width_target:
                reason_parts.append("quality interval above target")
            if identifier in frontier.uncertain_ids:
                reason_parts.append("frontier intervals overlap")
            if tail_uncertain:
                reason_parts.append("tail risk unstable")
            reasons.append((identifier, "; ".join(reason_parts)))
    for identifier in eliminated:
        reasons.append((identifier, "robustly dominated after minimum sample"))
    if calls_remaining == 0:
        return RacingDecision(tuple(eliminated), (), tuple(sorted(reasons)), True, "call/spend budget reached")
    if not allocate:
        return RacingDecision(tuple(eliminated), (), tuple(sorted(reasons)), True, "confidence target reached")
    return RacingDecision(tuple(eliminated), tuple(sorted(allocate)), tuple(sorted(reasons)), False, "allocate to unresolved candidates")
