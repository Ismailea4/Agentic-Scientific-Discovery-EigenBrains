"""Storage for a caller-supplied error covariance matrix.

The matrix is not estimated here. Constructing one requires every value.
There is no helper that fills zeros or an identity, because that would
invent an independence assumption.

CVaR / tail-risk hooks are intentionally left as optional fields on
`AgentMetrics` / `TailRiskEstimate` until real benchmark data exists; this
module fabricates neither correlations nor tail statistics.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from collections.abc import Mapping
from itertools import combinations
import random
from typing import Any


@dataclass(frozen=True)
class ErrorCovarianceMatrix:
    """A symmetric covariance matrix aligned to `labels`.

    `correlations` is an optional caller-supplied pairwise correlation
    matrix with the same shape and symmetry requirements.
    """

    labels: tuple[str, ...]
    matrix: tuple[tuple[float, ...], ...]
    correlations: tuple[tuple[float, ...], ...] | None = None

    def __post_init__(self) -> None:
        self._check_square("covariance matrix", self.matrix)
        if self.correlations is not None:
            self._check_square("correlation matrix", self.correlations)

    def _check_square(self, what: str, matrix: tuple[tuple[float, ...], ...]) -> None:
        size = len(self.labels)
        if len(set(self.labels)) != size:
            raise ValueError("covariance labels must be unique")
        if len(matrix) != size or any(len(row) != size for row in matrix):
            raise ValueError(f"{what} must be square and aligned to labels")
        for row in range(size):
            for column in range(row + 1, size):
                if matrix[row][column] != matrix[column][row]:
                    raise ValueError(f"{what} must be symmetric")

    def pair(self, left: str, right: str) -> float:
        return self.matrix[self.labels.index(left)][self.labels.index(right)]


# Backwards-compatible alias for the pre-rename name.
ErrorCovariance = ErrorCovarianceMatrix


@dataclass(frozen=True)
class ErrorCorrelationAnalysis:
    labels: tuple[str, ...]
    case_ids: tuple[str, ...]
    covariance: tuple[tuple[float, ...], ...]
    correlation: tuple[tuple[float | None, ...], ...]
    failure_overlap: tuple[tuple[float, ...], ...]
    disagreement_rate: tuple[tuple[float, ...], ...]
    jaccard_similarity: tuple[tuple[float, ...], ...]
    conditional_failure: tuple[tuple[float | None, ...], ...]
    failure_threshold: float

    def pair_metrics(self, left: str, right: str) -> dict[str, float | None]:
        row = self.labels.index(left)
        column = self.labels.index(right)
        return {
            "covariance": self.covariance[row][column],
            "correlation": self.correlation[row][column],
            "failure_overlap": self.failure_overlap[row][column],
            "disagreement_rate": self.disagreement_rate[row][column],
            "jaccard_similarity": self.jaccard_similarity[row][column],
            "conditional_failure": self.conditional_failure[row][column],
        }

    def to_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row, left in enumerate(self.labels):
            for column, right in enumerate(self.labels):
                rows.append(
                    {
                        "left": left,
                        "right": right,
                        "covariance": self.covariance[row][column],
                        "correlation": self.correlation[row][column],
                        "failure_overlap": self.failure_overlap[row][column],
                        "disagreement_rate": self.disagreement_rate[row][column],
                        "jaccard_similarity": self.jaccard_similarity[row][column],
                        "conditional_failure": self.conditional_failure[row][column],
                        "sample_size": len(self.case_ids),
                    }
                )
        return rows


@dataclass(frozen=True)
class MetricInterval:
    estimate: float | None
    lower: float | None
    upper: float | None
    confidence_level: float
    valid_resamples: int


@dataclass(frozen=True)
class PairwiseMetricUncertainty:
    left: str
    right: str
    sample_size: int
    metrics: dict[str, MetricInterval]

    def to_dict(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "right": self.right,
            "sample_size": self.sample_size,
            "metrics": {
                name: {
                    "estimate": interval.estimate,
                    "lower": interval.lower,
                    "upper": interval.upper,
                    "confidence_level": interval.confidence_level,
                    "valid_resamples": interval.valid_resamples,
                }
                for name, interval in self.metrics.items()
            },
        }


def diagonal_shrinkage_covariance(
    analysis: ErrorCorrelationAnalysis,
    *,
    intensity: float,
) -> ErrorCovarianceMatrix:
    """Shrink off-diagonal empirical covariance toward an independence target."""
    if not 0 <= intensity <= 1:
        raise ValueError("shrinkage intensity must be in [0, 1]")
    matrix = tuple(
        tuple(
            value if row == column else (1.0 - intensity) * value
            for column, value in enumerate(values)
        )
        for row, values in enumerate(analysis.covariance)
    )
    correlations = tuple(
        tuple(
            (1.0 if row == column and value is not None else value)
            if row == column
            else (None if value is None else (1.0 - intensity) * value)
            for column, value in enumerate(values)
        )
        for row, values in enumerate(analysis.correlation)
    )
    return ErrorCovarianceMatrix(analysis.labels, matrix, correlations)


def _binary_correlation(left: list[bool], right: list[bool]) -> float | None:
    left_values = [float(value) for value in left]
    right_values = [float(value) for value in right]
    left_mean = sum(left_values) / len(left_values)
    right_mean = sum(right_values) / len(right_values)
    covariance = sum(
        (a - left_mean) * (b - right_mean)
        for a, b in zip(left_values, right_values, strict=True)
    ) / len(left_values)
    left_variance = sum((value - left_mean) ** 2 for value in left_values) / len(left_values)
    right_variance = sum((value - right_mean) ** 2 for value in right_values) / len(right_values)
    denominator = sqrt(left_variance * right_variance)
    return covariance / denominator if denominator else None


def _paired_metrics(
    left: list[float], right: list[float], *, failure_threshold: float
) -> dict[str, float | None]:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    covariance = sum(
        (a - left_mean) * (b - right_mean)
        for a, b in zip(left, right, strict=True)
    ) / len(left)
    left_variance = sum((value - left_mean) ** 2 for value in left) / len(left)
    right_variance = sum((value - right_mean) ** 2 for value in right) / len(right)
    denominator = sqrt(left_variance * right_variance)
    correlation = covariance / denominator if denominator else None
    left_failed = [value >= failure_threshold for value in left]
    right_failed = [value >= failure_threshold for value in right]
    intersection = sum(a and b for a, b in zip(left_failed, right_failed, strict=True))
    union = sum(a or b for a, b in zip(left_failed, right_failed, strict=True))
    left_failure_count = sum(left_failed)
    conditional_failure = intersection / left_failure_count if left_failure_count else None
    return {
        "covariance": covariance,
        "correlation": correlation,
        "phi": _binary_correlation(left_failed, right_failed),
        "jaccard_failure_similarity": intersection / union if union else 1.0,
        "disagreement_rate": sum(
            a != b for a, b in zip(left_failed, right_failed, strict=True)
        ) / len(left),
        "p_right_fails_given_left_fails": conditional_failure,
        "p_right_succeeds_given_left_fails": (
            None if conditional_failure is None else 1.0 - conditional_failure
        ),
    }


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def bootstrap_pairwise_metrics(
    error_vectors: Mapping[str, Mapping[str, float]],
    *,
    failure_threshold: float,
    confidence_level: float = 0.95,
    resamples: int = 2000,
    seed: int = 0,
) -> list[PairwiseMetricUncertainty]:
    """Paired case bootstrap for diversification quantities, including Phi."""
    if resamples < 1:
        raise ValueError("resamples must be >= 1")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be in (0, 1)")
    analysis = analyze_error_vectors(error_vectors, failure_threshold=failure_threshold)
    rng = random.Random(seed)
    alpha = (1.0 - confidence_level) / 2.0
    output: list[PairwiseMetricUncertainty] = []
    for left_label, right_label in combinations(analysis.labels, 2):
        left = [float(error_vectors[left_label][case_id]) for case_id in analysis.case_ids]
        right = [float(error_vectors[right_label][case_id]) for case_id in analysis.case_ids]
        estimates = _paired_metrics(left, right, failure_threshold=failure_threshold)
        samples: dict[str, list[float]] = {name: [] for name in estimates}
        for _ in range(resamples):
            indices = [rng.randrange(len(left)) for _ in left]
            measured = _paired_metrics(
                [left[index] for index in indices],
                [right[index] for index in indices],
                failure_threshold=failure_threshold,
            )
            for name, value in measured.items():
                if value is not None:
                    samples[name].append(float(value))
        intervals = {
            name: MetricInterval(
                estimate=None if estimate is None else float(estimate),
                lower=_percentile(values, alpha) if values else None,
                upper=_percentile(values, 1.0 - alpha) if values else None,
                confidence_level=confidence_level,
                valid_resamples=len(values),
            )
            for name, estimate in estimates.items()
            for values in [samples[name]]
        }
        output.append(
            PairwiseMetricUncertainty(
                left_label, right_label, len(analysis.case_ids), intervals
            )
        )
    return output


def analyze_error_vectors(
    error_vectors: Mapping[str, Mapping[str, float]],
    *,
    failure_threshold: float,
) -> ErrorCorrelationAnalysis:
    """Estimate pairwise covariance, correlation, overlap, and disagreement.

    Every configuration must contain the same case ids. Values are continuous
    errors in ``[0, 1]``; binary failures are values at or above the explicit
    ``failure_threshold``.
    """

    if not 0 <= failure_threshold <= 1:
        raise ValueError("failure_threshold must be in [0, 1]")
    if len(error_vectors) < 1:
        raise ValueError("at least one error vector is required")
    labels = tuple(sorted(error_vectors))
    case_ids = tuple(sorted(error_vectors[labels[0]]))
    if not case_ids:
        raise ValueError("error vectors must not be empty")
    expected = set(case_ids)
    vectors: list[list[float]] = []
    for label in labels:
        values = error_vectors[label]
        if set(values) != expected:
            raise ValueError("all error vectors must use the same case ids")
        vector = [float(values[case_id]) for case_id in case_ids]
        if any(value < 0 or value > 1 for value in vector):
            raise ValueError("error values must be in [0, 1]")
        vectors.append(vector)

    means = [sum(vector) / len(vector) for vector in vectors]
    covariance_rows: list[tuple[float, ...]] = []
    correlation_rows: list[tuple[float | None, ...]] = []
    overlap_rows: list[tuple[float, ...]] = []
    disagreement_rows: list[tuple[float, ...]] = []
    jaccard_rows: list[tuple[float, ...]] = []
    conditional_rows: list[tuple[float | None, ...]] = []
    for left_index, left in enumerate(vectors):
        cov_row: list[float] = []
        corr_row: list[float | None] = []
        overlap_row: list[float] = []
        disagreement_row: list[float] = []
        jaccard_row: list[float] = []
        conditional_row: list[float | None] = []
        left_variance = sum((value - means[left_index]) ** 2 for value in left) / len(left)
        for right_index, right in enumerate(vectors):
            right_variance = sum((value - means[right_index]) ** 2 for value in right) / len(right)
            covariance = sum(
                (left_value - means[left_index]) * (right_value - means[right_index])
                for left_value, right_value in zip(left, right, strict=True)
            ) / len(left)
            denominator = sqrt(left_variance * right_variance)
            correlation = covariance / denominator if denominator > 0 else None
            left_failed = [value >= failure_threshold for value in left]
            right_failed = [value >= failure_threshold for value in right]
            overlap = sum(a and b for a, b in zip(left_failed, right_failed, strict=True)) / len(left)
            disagreement = sum(a != b for a, b in zip(left_failed, right_failed, strict=True)) / len(left)
            intersection = sum(a and b for a, b in zip(left_failed, right_failed, strict=True))
            union = sum(a or b for a, b in zip(left_failed, right_failed, strict=True))
            jaccard = intersection / union if union else 1.0
            left_failure_count = sum(left_failed)
            conditional = intersection / left_failure_count if left_failure_count else None
            cov_row.append(covariance)
            corr_row.append(correlation)
            overlap_row.append(overlap)
            disagreement_row.append(disagreement)
            jaccard_row.append(jaccard)
            conditional_row.append(conditional)
        covariance_rows.append(tuple(cov_row))
        correlation_rows.append(tuple(corr_row))
        overlap_rows.append(tuple(overlap_row))
        disagreement_rows.append(tuple(disagreement_row))
        jaccard_rows.append(tuple(jaccard_row))
        conditional_rows.append(tuple(conditional_row))

    return ErrorCorrelationAnalysis(
        labels=labels,
        case_ids=case_ids,
        covariance=tuple(covariance_rows),
        correlation=tuple(correlation_rows),
        failure_overlap=tuple(overlap_rows),
        disagreement_rate=tuple(disagreement_rows),
        jaccard_similarity=tuple(jaccard_rows),
        conditional_failure=tuple(conditional_rows),
        failure_threshold=failure_threshold,
    )


def select_complementary_pair(
    analysis: ErrorCorrelationAnalysis,
    mean_quality: Mapping[str, float],
    *,
    correlation_penalty: float,
) -> tuple[str, str]:
    """Choose a two-model portfolio using explicit quality/diversity weight."""

    if correlation_penalty < 0:
        raise ValueError("correlation_penalty must be >= 0")
    ranked: list[tuple[float, str, str]] = []
    for left, right in combinations(analysis.labels, 2):
        if left not in mean_quality or right not in mean_quality:
            raise ValueError("mean_quality must cover every correlation label")
        correlation = analysis.pair_metrics(left, right)["correlation"]
        redundancy = max(float(correlation or 0.0), 0.0)
        utility = (float(mean_quality[left]) + float(mean_quality[right])) / 2.0
        utility -= correlation_penalty * redundancy
        ranked.append((-utility, left, right))
    if not ranked:
        raise ValueError("at least two configurations are required")
    _, left, right = min(ranked)
    return left, right
