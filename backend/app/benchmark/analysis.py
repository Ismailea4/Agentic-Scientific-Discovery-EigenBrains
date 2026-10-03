"""Model-level summaries computed from normalized benchmark call records."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from math import sqrt
from statistics import fmean, median, pvariance

from .models import BenchmarkRun, ModelBenchmarkResult


@dataclass(frozen=True)
class ModelReliabilityBreakdown:
    """Model quality conditional on transport success plus deployable risk."""

    provider: str
    model: str
    total_calls: int
    provider_successes: int
    provider_failures: int
    provider_success_probability: float
    scored_provider_successes: int
    correct_given_provider_success: float | None
    severe_failure_given_provider_success: float | None
    latency_mean_ms_given_provider_success: float | None
    latency_median_ms_given_provider_success: float | None
    latency_p90_ms_given_provider_success: float | None
    latency_p95_ms_given_provider_success: float | None
    operational_correct_probability: float
    operational_severe_failure_probability: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def aggregate_model_reliability(
    runs: Sequence[BenchmarkRun],
    *,
    severe_failure_threshold: float = 0.2,
) -> list[ModelReliabilityBreakdown]:
    """Do not count transport failures as mistakes in conditional intelligence."""
    if not 0 <= severe_failure_threshold <= 1:
        raise ValueError("severe_failure_threshold must be in [0, 1]")
    grouped: dict[tuple[str, str], list[BenchmarkRun]] = defaultdict(list)
    for run in runs:
        if run.metadata.get("final_output") is True:
            grouped[(run.provider, run.model)].append(run)
    output: list[ModelReliabilityBreakdown] = []
    for (provider, model), rows in sorted(grouped.items()):
        successful = [row for row in rows if row.success]
        scored_successful = [row for row in successful if row.score is not None]
        latencies = [row.latency_ms for row in successful]
        conditional_severe = [
            row.malformed_output
            or bool(row.constraint_violations)
            or float(row.score) <= severe_failure_threshold
            for row in scored_successful
        ]
        operational_severe = [
            (not row.success)
            or row.malformed_output
            or bool(row.constraint_violations)
            or row.score is None
            or float(row.score or 0.0) <= severe_failure_threshold
            for row in rows
        ]
        output.append(
            ModelReliabilityBreakdown(
                provider=provider,
                model=model,
                total_calls=len(rows),
                provider_successes=len(successful),
                provider_failures=len(rows) - len(successful),
                provider_success_probability=len(successful) / len(rows),
                scored_provider_successes=len(scored_successful),
                correct_given_provider_success=(
                    sum(row.passed is True for row in scored_successful) / len(scored_successful)
                    if scored_successful else None
                ),
                severe_failure_given_provider_success=(
                    sum(conditional_severe) / len(conditional_severe)
                    if conditional_severe else None
                ),
                latency_mean_ms_given_provider_success=(fmean(latencies) if latencies else None),
                latency_median_ms_given_provider_success=(median(latencies) if latencies else None),
                latency_p90_ms_given_provider_success=(
                    _percentile(latencies, 0.90) if latencies else None
                ),
                latency_p95_ms_given_provider_success=(
                    _percentile(latencies, 0.95) if latencies else None
                ),
                operational_correct_probability=sum(row.passed is True for row in rows) / len(rows),
                operational_severe_failure_probability=sum(operational_severe) / len(rows),
            )
        )
    return output


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    index = round((len(ordered) - 1) * probability)
    return ordered[index]


def aggregate_models(
    runs: Sequence[BenchmarkRun],
    *,
    severe_failure_threshold: float = 0.2,
) -> list[ModelBenchmarkResult]:
    """Summarize final model outputs; unknown price remains unknown."""

    if not 0 <= severe_failure_threshold <= 1:
        raise ValueError("severe_failure_threshold must be in [0, 1]")

    grouped: dict[tuple[str, str], list[BenchmarkRun]] = defaultdict(list)
    for run in runs:
        if run.metadata.get("final_output") is True:
            grouped[(run.provider, run.model)].append(run)

    results: list[ModelBenchmarkResult] = []
    for (provider, model), rows in sorted(grouped.items()):
        scores = [float(row.score) for row in rows if row.score is not None]
        if not scores:
            continue
        costs = [row.estimated_cost_usd for row in rows]
        disagreement_values = [row.disagreement for row in rows if row.disagreement is not None]
        violations = sum(bool(row.constraint_violations) for row in rows)
        answered_scores = [
            float(row.score)
            for row in rows
            if row.outcome.value == "ANSWER" and not row.abstained and row.score is not None
        ]
        variance = pvariance(scores) if len(scores) > 1 else 0.0
        known_cost = not any(value is None for value in costs)
        results.append(
            ModelBenchmarkResult(
                provider=provider,
                model=model,
                correctness=sum(row.passed is True for row in rows) / len(rows),
                rubric_score=fmean(scores),
                latency_mean_ms=fmean(row.latency_ms for row in rows),
                latency_p95_ms=_percentile([row.latency_ms for row in rows], 0.95),
                input_tokens=sum(row.input_tokens for row in rows),
                output_tokens=sum(row.output_tokens for row in rows),
                estimated_cost_usd=(
                    None if any(value is None for value in costs) else sum(float(value) for value in costs)
                ),
                failure_rate=sum(not row.success for row in rows) / len(rows),
                malformed_output_rate=sum(row.malformed_output for row in rows) / len(rows),
                abstention_rate=sum(row.abstained for row in rows) / len(rows),
                constraint_violation_rate=violations / len(rows),
                output_disagreement=(fmean(disagreement_values) if disagreement_values else None),
                quality_variance=variance,
                sample_size=len(rows),
                quality_median=median(scores),
                quality_standard_error=sqrt(variance / len(scores)),
                success_probability=sum(row.success and row.passed is not False for row in rows) / len(rows),
                severe_failure_probability=sum(
                    (not row.success)
                    or (row.score is not None and float(row.score) <= severe_failure_threshold)
                    for row in rows
                ) / len(rows),
                latency_median_ms=median(row.latency_ms for row in rows),
                latency_p90_ms=_percentile([row.latency_ms for row in rows], 0.90),
                cost_median_usd=(median(float(value) for value in costs) if known_cost else None),
                cost_p90_usd=(_percentile([float(value) for value in costs], 0.90) if known_cost else None),
                coverage=sum(row.outcome.value == "ANSWER" and not row.abstained for row in rows) / len(rows),
                quality_conditional_on_answering=(fmean(answered_scores) if answered_scores else None),
                metadata={
                    "task_types": sorted({row.task_type for row in rows}),
                    "splits": sorted({str(row.metadata.get("split", "unknown")) for row in rows}),
                },
            )
        )
    return results


def model_error_vectors(runs: Sequence[BenchmarkRun]) -> dict[str, dict[str, float]]:
    """Build aligned per-model error vectors from scored final-output runs."""

    vectors: dict[str, dict[str, float]] = defaultdict(dict)
    for run in runs:
        if run.metadata.get("final_output") is not True or run.score is None:
            continue
        label = f"{run.provider}/{run.model}@{run.architecture_id}"
        observation = f"{run.benchmark_case_id}#repeat-{run.repeat}"
        if observation in vectors[label]:
            raise ValueError(f"duplicate scored observation for {label}: {observation}")
        vectors[label][observation] = 1.0 - float(run.score)
    if len(vectors) > 1:
        coverage = {label: frozenset(values) for label, values in vectors.items()}
        expected = next(iter(coverage.values()))
        if any(case_ids != expected for case_ids in coverage.values()):
            raise ValueError("model complementarity requires identical case/repeat coverage")
    return dict(vectors)
