"""Uncertainty intervals and conservative architecture bounds."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from math import sqrt
from statistics import NormalDist, fmean, median
import random
from typing import Any, Sequence

from .models import BenchmarkRun
from .observations import ExecutionObservation, execution_observations
from .statistics import ConfidenceInterval, bootstrap_confidence_interval


def wilson_interval(successes: int, total: int, *, confidence_level: float = 0.95) -> ConfidenceInterval:
    if total < 1 or not 0 <= successes <= total:
        raise ValueError("Wilson interval requires 0 <= successes <= total and total >= 1")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be in (0, 1)")
    z = NormalDist().inv_cdf(0.5 + confidence_level / 2.0)
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    radius = z * sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return ConfidenceInterval(
        estimate=proportion,
        lower=max(0.0, center - radius),
        upper=min(1.0, center + radius),
        confidence_level=confidence_level,
        method="wilson",
        resamples=0,
    )


@dataclass(frozen=True)
class ArchitectureBounds:
    architecture_id: str
    sample_size: int
    quality: ConfidenceInterval | None
    failure: ConfidenceInterval
    severe_failure: ConfidenceInterval
    cost: ConfidenceInterval | None
    latency: ConfidenceInterval
    quality_median: ConfidenceInterval | None = None
    cost_median: ConfidenceInterval | None = None
    latency_median: ConfidenceInterval | None = None
    task_type: str = "*"
    risk_level: str = "*"
    split: str = "*"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_architecture_bounds(
    runs: Sequence[BenchmarkRun],
    *,
    severe_failure_threshold: float,
    confidence_level: float = 0.95,
    resamples: int = 2000,
    seed: int = 0,
) -> list[ArchitectureBounds]:
    observations = execution_observations(
        runs, severe_failure_threshold=severe_failure_threshold
    )
    grouped: dict[str, list[ExecutionObservation]] = defaultdict(list)
    for row in observations:
        grouped[row.architecture_id].append(row)
    output: list[ArchitectureBounds] = []
    for offset, (architecture_id, rows) in enumerate(sorted(grouped.items())):
        qualities = [float(row.quality) for row in rows if row.quality is not None]
        costs = [row.cost_usd for row in rows]
        output.append(
            ArchitectureBounds(
                architecture_id=architecture_id,
                sample_size=len(rows),
                quality=(
                    bootstrap_confidence_interval(
                        qualities,
                        confidence_level=confidence_level,
                        resamples=resamples,
                        seed=seed + offset * 10,
                    ) if qualities else None
                ),
                failure=wilson_interval(
                    sum(not row.success for row in rows), len(rows), confidence_level=confidence_level
                ),
                severe_failure=wilson_interval(
                    sum(row.severe_failure for row in rows), len(rows), confidence_level=confidence_level
                ),
                cost=(
                    None if any(value is None for value in costs) else bootstrap_confidence_interval(
                        [float(value) for value in costs],
                        confidence_level=confidence_level,
                        resamples=resamples,
                        seed=seed + offset * 10 + 1,
                    )
                ),
                latency=bootstrap_confidence_interval(
                    [row.latency_ms for row in rows],
                    confidence_level=confidence_level,
                    resamples=resamples,
                    seed=seed + offset * 10 + 2,
                ),
                quality_median=(
                    bootstrap_confidence_interval(
                        qualities,
                        statistic=median,
                        confidence_level=confidence_level,
                        resamples=resamples,
                        seed=seed + offset * 10 + 3,
                    ) if qualities else None
                ),
                cost_median=(
                    None if any(value is None for value in costs) else bootstrap_confidence_interval(
                        [float(value) for value in costs],
                        statistic=median,
                        confidence_level=confidence_level,
                        resamples=resamples,
                        seed=seed + offset * 10 + 4,
                    )
                ),
                latency_median=bootstrap_confidence_interval(
                    [row.latency_ms for row in rows],
                    statistic=median,
                    confidence_level=confidence_level,
                    resamples=resamples,
                    seed=seed + offset * 10 + 5,
                ),
            )
        )
    return output


def estimate_task_specific_bounds(
    runs: Sequence[BenchmarkRun],
    *,
    severe_failure_threshold: float,
    confidence_level: float = 0.95,
    resamples: int = 2000,
    seed: int = 0,
) -> list[ArchitectureBounds]:
    grouped: dict[tuple[str, str, str], list[BenchmarkRun]] = defaultdict(list)
    for run in runs:
        grouped[
            (
                run.task_type,
                str(run.metadata.get("risk_level", "unknown")),
                str(run.metadata.get("split", "unknown")),
            )
        ].append(run)
    output: list[ArchitectureBounds] = []
    for offset, ((task_type, risk_level, split), rows) in enumerate(sorted(grouped.items())):
        estimates = estimate_architecture_bounds(
            rows,
            severe_failure_threshold=severe_failure_threshold,
            confidence_level=confidence_level,
            resamples=resamples,
            seed=seed + offset * 1000,
        )
        output.extend(
            replace(item, task_type=task_type, risk_level=risk_level, split=split)
            for item in estimates
        )
    return output


def robustly_dominates(left: ArchitectureBounds, right: ArchitectureBounds) -> bool:
    if left.quality is None or right.quality is None or left.cost is None or right.cost is None:
        return False
    comparisons = (
        left.quality.lower >= right.quality.upper,
        left.cost.upper <= right.cost.lower,
        left.latency.upper <= right.latency.lower,
        left.severe_failure.upper <= right.severe_failure.lower,
    )
    strict = (
        left.quality.lower > right.quality.upper
        or left.cost.upper < right.cost.lower
        or left.latency.upper < right.latency.lower
        or left.severe_failure.upper < right.severe_failure.lower
    )
    return all(comparisons) and strict


@dataclass(frozen=True)
class RobustFrontier:
    frontier_ids: tuple[str, ...]
    dominated_ids: tuple[str, ...]
    uncertain_ids: tuple[str, ...]
    probability_of_dominance: dict[str, float | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def robust_frontier(
    bounds: Sequence[ArchitectureBounds],
    *,
    probability_of_dominance: dict[str, float | None] | None = None,
) -> RobustFrontier:
    identifiers = [item.architecture_id for item in bounds]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("architecture bound ids must be unique")
    dominated = {
        candidate.architecture_id
        for candidate in bounds
        if any(
            other.architecture_id != candidate.architecture_id
            and robustly_dominates(other, candidate)
            for other in bounds
        )
    }
    frontier = set(identifiers) - dominated
    uncertain = {
        item.architecture_id
        for item in bounds
        if item.architecture_id in frontier
        and any(
            other.architecture_id != item.architecture_id
            and not robustly_dominates(item, other)
            and not robustly_dominates(other, item)
            for other in bounds
        )
    }
    return RobustFrontier(
        tuple(sorted(frontier)),
        tuple(sorted(dominated)),
        tuple(sorted(uncertain)),
        dict(probability_of_dominance or {}),
    )


def bootstrap_dominance_probabilities(
    runs: Sequence[BenchmarkRun],
    *,
    severe_failure_threshold: float,
    resamples: int = 2000,
    seed: int = 0,
) -> dict[str, float | None]:
    observations = execution_observations(runs, severe_failure_threshold=severe_failure_threshold)
    by_architecture: dict[str, dict[str, ExecutionObservation]] = defaultdict(dict)
    for row in observations:
        by_architecture[row.architecture_id][row.observation_id] = row
    rng = random.Random(seed)
    output: dict[str, float | None] = {}
    identifiers = sorted(by_architecture)
    for left_id in identifiers:
        for right_id in identifiers:
            if left_id == right_id:
                continue
            left = by_architecture[left_id]
            right = by_architecture[right_id]
            paired_ids = sorted(set(left) & set(right))
            key = f"{left_id}>{right_id}"
            if set(left) != set(right) or not paired_ids or any(
                left[item].quality is None
                or right[item].quality is None
                or left[item].cost_usd is None
                or right[item].cost_usd is None
                for item in paired_ids
            ):
                output[key] = None
                continue
            dominance_count = 0
            for _ in range(resamples):
                sample_ids = [paired_ids[rng.randrange(len(paired_ids))] for _ in paired_ids]
                left_quality = fmean(float(left[item].quality) for item in sample_ids)
                right_quality = fmean(float(right[item].quality) for item in sample_ids)
                left_cost = fmean(float(left[item].cost_usd) for item in sample_ids)
                right_cost = fmean(float(right[item].cost_usd) for item in sample_ids)
                left_latency = fmean(left[item].latency_ms for item in sample_ids)
                right_latency = fmean(right[item].latency_ms for item in sample_ids)
                left_risk = fmean(float(left[item].severe_failure) for item in sample_ids)
                right_risk = fmean(float(right[item].severe_failure) for item in sample_ids)
                weak = (
                    left_quality >= right_quality
                    and left_cost <= right_cost
                    and left_latency <= right_latency
                    and left_risk <= right_risk
                )
                strict = (
                    left_quality > right_quality
                    or left_cost < right_cost
                    or left_latency < right_latency
                    or left_risk < right_risk
                )
                dominance_count += weak and strict
            output[key] = dominance_count / resamples
    return output
