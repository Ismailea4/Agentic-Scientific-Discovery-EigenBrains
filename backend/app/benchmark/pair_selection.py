"""Compare score-only and covariance-aware model pair selection."""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Any, Mapping

from ..optimization.covariance import ErrorCorrelationAnalysis, select_complementary_pair


@dataclass(frozen=True)
class PairStrategyResult:
    strategy: str
    pair: tuple[str, ...]
    mean_individual_quality: float
    joint_failure_rate: float
    correlation: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_pair_selection_strategies(
    analysis: ErrorCorrelationAnalysis,
    error_vectors: Mapping[str, Mapping[str, float]],
    mean_quality: Mapping[str, float],
    *,
    failure_threshold: float,
    correlation_penalty: float,
    seed: int = 0,
) -> list[PairStrategyResult]:
    if set(error_vectors) != set(analysis.labels) or set(mean_quality) != set(analysis.labels):
        raise ValueError("pair strategy inputs must cover the correlation labels exactly")
    ranked = sorted(analysis.labels, key=lambda label: (-mean_quality[label], label))
    pairs = list(combinations(analysis.labels, 2))
    if not pairs:
        raise ValueError("at least two models are required")
    pair_correlations = sorted(
        (
            float(analysis.pair_metrics(left, right)["correlation"] or 0.0),
            (left, right),
        )
        for left, right in pairs
    )
    diverse_pool = [pair for _, pair in pair_correlations[: max(1, len(pair_correlations) // 2)]]
    strategies = {
        "top_two_models": tuple(ranked[:2]),
        "random_diverse_pair": random.Random(seed).choice(diverse_pool),
        "covariance_aware_pair": select_complementary_pair(
            analysis, mean_quality, correlation_penalty=correlation_penalty
        ),
    }
    results: list[PairStrategyResult] = []
    for strategy, pair in strategies.items():
        left, right = pair
        case_ids = sorted(error_vectors[left])
        joint_failure = sum(
            error_vectors[left][case_id] >= failure_threshold
            and error_vectors[right][case_id] >= failure_threshold
            for case_id in case_ids
        ) / len(case_ids)
        results.append(
            PairStrategyResult(
                strategy=strategy,
                pair=tuple(pair),
                mean_individual_quality=(mean_quality[left] + mean_quality[right]) / 2.0,
                joint_failure_rate=joint_failure,
                correlation=analysis.pair_metrics(left, right)["correlation"],
            )
        )
    top = ranked[0]
    top_failures = sum(
        error >= failure_threshold for error in error_vectors[top].values()
    ) / len(error_vectors[top])
    results.append(
        PairStrategyResult(
            strategy="top_model_only",
            pair=(top,),
            mean_individual_quality=mean_quality[top],
            joint_failure_rate=top_failures,
            correlation=None,
        )
    )
    return sorted(results, key=lambda item: item.strategy)
