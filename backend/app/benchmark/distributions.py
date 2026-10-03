"""Distribution summaries by architecture, task, risk level, and split."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from math import sqrt
from statistics import fmean, median, pvariance
from typing import Any, Sequence

from .models import BenchmarkRun
from .observations import ExecutionObservation, execution_observations


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("quantile requires observations")
    ordered = sorted(float(value) for value in values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * probability)))
    return ordered[index]


@dataclass(frozen=True)
class ArchitectureDistribution:
    architecture_id: str
    task_type: str
    risk_level: str
    split: str
    sample_size: int
    quality_mean: float | None
    quality_median: float | None
    quality_variance: float | None
    quality_standard_error: float | None
    success_probability: float
    severe_failure_probability: float
    abstention_probability: float
    malformed_output_probability: float
    latency_mean_ms: float
    latency_median_ms: float
    latency_p90_ms: float
    latency_p95_ms: float
    cost_mean_usd: float | None
    cost_median_usd: float | None
    cost_p90_usd: float | None
    coverage: float
    quality_conditional_on_answering: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_observations(
    observations: Sequence[ExecutionObservation],
    *,
    task_specific: bool,
) -> list[ArchitectureDistribution]:
    grouped: dict[tuple[str, str, str, str], list[ExecutionObservation]] = defaultdict(list)
    for row in observations:
        key = (
            row.architecture_id,
            row.task_type if task_specific else "*",
            row.risk_level if task_specific else "*",
            row.split,
        )
        grouped[key].append(row)
    output: list[ArchitectureDistribution] = []
    for (architecture_id, task_type, risk_level, split), rows in sorted(grouped.items()):
        quality = [float(row.quality) for row in rows if row.quality is not None]
        answered_quality = [
            float(row.quality) for row in rows if row.answered and row.quality is not None
        ]
        costs = [row.cost_usd for row in rows]
        known_cost = not any(value is None for value in costs)
        variance = pvariance(quality) if len(quality) > 1 else (0.0 if quality else None)
        output.append(
            ArchitectureDistribution(
                architecture_id=architecture_id,
                task_type=task_type,
                risk_level=risk_level,
                split=split,
                sample_size=len(rows),
                quality_mean=fmean(quality) if quality else None,
                quality_median=median(quality) if quality else None,
                quality_variance=variance,
                quality_standard_error=(sqrt(variance / len(quality)) if variance is not None and quality else None),
                success_probability=sum(row.success for row in rows) / len(rows),
                severe_failure_probability=sum(row.severe_failure for row in rows) / len(rows),
                abstention_probability=sum(row.abstained for row in rows) / len(rows),
                malformed_output_probability=sum(row.malformed_output for row in rows) / len(rows),
                latency_mean_ms=fmean(row.latency_ms for row in rows),
                latency_median_ms=median(row.latency_ms for row in rows),
                latency_p90_ms=_quantile([row.latency_ms for row in rows], 0.90),
                latency_p95_ms=_quantile([row.latency_ms for row in rows], 0.95),
                cost_mean_usd=(fmean(float(value) for value in costs) if known_cost else None),
                cost_median_usd=(median(float(value) for value in costs) if known_cost else None),
                cost_p90_usd=(_quantile([float(value) for value in costs], 0.90) if known_cost else None),
                coverage=sum(row.answered for row in rows) / len(rows),
                quality_conditional_on_answering=(fmean(answered_quality) if answered_quality else None),
            )
        )
    return output


def summarize_runs(
    runs: Sequence[BenchmarkRun],
    *,
    severe_failure_threshold: float,
    task_specific: bool,
) -> list[ArchitectureDistribution]:
    return summarize_observations(
        execution_observations(runs, severe_failure_threshold=severe_failure_threshold),
        task_specific=task_specific,
    )
