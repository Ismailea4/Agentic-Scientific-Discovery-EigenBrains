"""Calibration and abstention metrics for measured final outputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

from .models import BenchmarkRun, SystemOutcome


@dataclass(frozen=True)
class ReliabilityBin:
    lower: float
    upper: float
    count: int
    mean_confidence: float | None
    accuracy: float | None


@dataclass(frozen=True)
class CalibrationResult:
    bins: tuple[ReliabilityBin, ...]
    expected_calibration_error: float | None
    brier_score: float | None
    overconfidence: float | None
    underconfidence: float | None
    sample_size: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AbstentionMetrics:
    coverage: float
    error_among_answered: float | None
    abstention_rate: float
    verification_rate: float
    sample_size: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calibration_metrics(runs: Sequence[BenchmarkRun], *, bin_count: int = 10) -> CalibrationResult:
    if bin_count < 1:
        raise ValueError("bin_count must be >= 1")
    measured = [run for run in runs if run.confidence is not None and run.passed is not None]
    if any(not 0 <= float(run.confidence) <= 1 for run in measured):
        raise ValueError("confidence values must be in [0, 1]")
    bins: list[ReliabilityBin] = []
    weighted_gap = 0.0
    for index in range(bin_count):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        rows = [
            run for run in measured
            if float(run.confidence) >= lower
            and (float(run.confidence) < upper or index == bin_count - 1)
        ]
        confidence = sum(float(run.confidence) for run in rows) / len(rows) if rows else None
        accuracy = sum(run.passed is True for run in rows) / len(rows) if rows else None
        if rows and confidence is not None and accuracy is not None:
            weighted_gap += len(rows) * abs(confidence - accuracy)
        bins.append(ReliabilityBin(lower, upper, len(rows), confidence, accuracy))
    if not measured:
        return CalibrationResult(tuple(bins), None, None, None, None, 0)
    brier = sum((float(run.confidence) - float(run.passed is True)) ** 2 for run in measured) / len(measured)
    gaps = [float(run.confidence) - float(run.passed is True) for run in measured]
    return CalibrationResult(
        bins=tuple(bins),
        expected_calibration_error=weighted_gap / len(measured),
        brier_score=brier,
        overconfidence=sum(max(gap, 0.0) for gap in gaps) / len(gaps),
        underconfidence=sum(max(-gap, 0.0) for gap in gaps) / len(gaps),
        sample_size=len(measured),
    )


def abstention_metrics(runs: Sequence[BenchmarkRun]) -> AbstentionMetrics:
    final = [run for run in runs if run.metadata.get("final_output") is True]
    if not final:
        raise ValueError("abstention metrics require final-output runs")
    answered = [run for run in final if run.outcome is SystemOutcome.ANSWER and not run.abstained]
    abstained = [
        run for run in final
        if run.abstained
        or run.outcome in {
            SystemOutcome.INSUFFICIENT_EVIDENCE,
            SystemOutcome.OUT_OF_DISTRIBUTION,
            SystemOutcome.INFEASIBLE,
            SystemOutcome.NO_CALL,
        }
    ]
    verification = [run for run in final if run.outcome is SystemOutcome.VERIFY]
    answered_errors = sum(run.passed is False for run in answered)
    return AbstentionMetrics(
        coverage=len(answered) / len(final),
        error_among_answered=(answered_errors / len(answered) if answered else None),
        abstention_rate=len(abstained) / len(final),
        verification_rate=len(verification) / len(final),
        sample_size=len(final),
    )
