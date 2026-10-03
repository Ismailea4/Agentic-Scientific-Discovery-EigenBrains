"""Deterministic bootstrap intervals and paired binary comparison."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import asdict, dataclass
from statistics import fmean
from typing import Any, Callable, Sequence

from .models import BenchmarkRun, SystemOutcome


@dataclass(frozen=True)
class ConfidenceInterval:
    estimate: float
    lower: float
    upper: float
    confidence_level: float
    method: str
    resamples: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def bootstrap_confidence_interval(
    values: Sequence[float],
    *,
    statistic: Callable[[Sequence[float]], float] = fmean,
    confidence_level: float = 0.95,
    resamples: int = 2000,
    seed: int = 0,
) -> ConfidenceInterval:
    if not values:
        raise ValueError("bootstrap requires observations")
    if not 0 < confidence_level < 1 or resamples < 1:
        raise ValueError("invalid bootstrap configuration")
    rng = random.Random(seed)
    population = tuple(float(value) for value in values)
    estimates = sorted(
        statistic([population[rng.randrange(len(population))] for _ in population])
        for _ in range(resamples)
    )
    alpha = (1.0 - confidence_level) / 2.0
    lower = estimates[min(resamples - 1, math.floor(alpha * resamples))]
    upper = estimates[min(resamples - 1, math.ceil((1.0 - alpha) * resamples) - 1)]
    return ConfidenceInterval(
        estimate=statistic(population),
        lower=lower,
        upper=upper,
        confidence_level=confidence_level,
        method="percentile_bootstrap",
        resamples=resamples,
    )


def paired_bootstrap_difference(
    left: Sequence[float],
    right: Sequence[float],
    *,
    confidence_level: float = 0.95,
    resamples: int = 2000,
    seed: int = 0,
) -> ConfidenceInterval:
    if len(left) != len(right) or not left:
        raise ValueError("paired bootstrap inputs must be non-empty and aligned")
    differences = [float(a) - float(b) for a, b in zip(left, right, strict=True)]
    result = bootstrap_confidence_interval(
        differences,
        confidence_level=confidence_level,
        resamples=resamples,
        seed=seed,
    )
    return ConfidenceInterval(**{**result.to_dict(), "method": "paired_percentile_bootstrap"})


@dataclass(frozen=True)
class McNemarResult:
    left_only_correct: int
    right_only_correct: int
    p_value: float
    method: str = "exact_two_sided_binomial"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def mcnemar_exact(left: Sequence[bool], right: Sequence[bool]) -> McNemarResult:
    if len(left) != len(right) or not left:
        raise ValueError("McNemar inputs must be non-empty and aligned")
    left_only = sum(a and not b for a, b in zip(left, right, strict=True))
    right_only = sum(b and not a for a, b in zip(left, right, strict=True))
    discordant = left_only + right_only
    if discordant == 0:
        p_value = 1.0
    else:
        extreme = min(left_only, right_only)
        tail = sum(math.comb(discordant, k) for k in range(extreme + 1)) / (2**discordant)
        p_value = min(1.0, 2.0 * tail)
    return McNemarResult(left_only, right_only, p_value)


def architecture_confidence_intervals(
    runs: Sequence[BenchmarkRun],
    *,
    confidence_level: float = 0.95,
    resamples: int = 2000,
    seed: int = 0,
) -> dict[str, dict[str, dict[str, Any] | None]]:
    """Intervals for execution quality, failure rate, cost, and latency."""

    executions: dict[tuple[str, str, int], list[BenchmarkRun]] = defaultdict(list)
    for run in runs:
        executions[(run.architecture_id, run.benchmark_case_id, run.repeat)].append(run)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (architecture_id, _, _), rows in executions.items():
        final = next((row for row in reversed(rows) if row.metadata.get("final_output") is True), rows[-1])
        costs = [row.estimated_cost_usd for row in rows if row.success]
        grouped[architecture_id].append(
            {
                "quality": final.score,
                "failure": float(
                    any(not row.success for row in rows)
                    or final.passed is False
                    or final.malformed_output
                    or bool(final.constraint_violations)
                    or final.outcome not in {SystemOutcome.ANSWER, SystemOutcome.VERIFY}
                ),
                "cost": None if any(value is None for value in costs) else sum(float(value) for value in costs),
                "latency": sum(row.latency_ms for row in rows),
            }
        )
    output: dict[str, dict[str, dict[str, Any] | None]] = {}
    for architecture_id, rows in sorted(grouped.items()):
        quality = [float(row["quality"]) for row in rows if row["quality"] is not None]
        costs = [row["cost"] for row in rows]
        output[architecture_id] = {
            "quality": (
                bootstrap_confidence_interval(
                    quality,
                    confidence_level=confidence_level,
                    resamples=resamples,
                    seed=seed,
                ).to_dict()
                if quality else None
            ),
            "failure_rate": bootstrap_confidence_interval(
                [float(row["failure"]) for row in rows],
                confidence_level=confidence_level,
                resamples=resamples,
                seed=seed + 1,
            ).to_dict(),
            "cost": (
                None if any(value is None for value in costs) else bootstrap_confidence_interval(
                    [float(value) for value in costs],
                    confidence_level=confidence_level,
                    resamples=resamples,
                    seed=seed + 2,
                ).to_dict()
            ),
            "latency": bootstrap_confidence_interval(
                [float(row["latency"]) for row in rows],
                confidence_level=confidence_level,
                resamples=resamples,
                seed=seed + 3,
            ).to_dict(),
        }
    return output
