"""Risk-adjusted and incremental architecture diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RiskAdjustedDiagnostics:
    architecture_id: str
    baseline_id: str
    quality_gain: float
    incremental_cost_usd: float
    incremental_latency_seconds: float
    severe_failures_avoided: float
    sharpe_inspired_gain: float | None
    quality_gain_per_incremental_dollar: float | None
    quality_gain_per_incremental_second: float | None
    severe_failures_avoided_per_incremental_dollar: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def risk_adjusted_diagnostics(
    *,
    architecture_id: str,
    baseline_id: str,
    quality: float,
    baseline_quality: float,
    cost: float,
    baseline_cost: float,
    latency_ms: float,
    baseline_latency_ms: float,
    severe_failure_rate: float,
    baseline_severe_failure_rate: float,
    downside_deviation: float,
) -> RiskAdjustedDiagnostics:
    quality_gain = quality - baseline_quality
    incremental_cost = cost - baseline_cost
    incremental_seconds = (latency_ms - baseline_latency_ms) / 1000.0
    failures_avoided = baseline_severe_failure_rate - severe_failure_rate
    return RiskAdjustedDiagnostics(
        architecture_id=architecture_id,
        baseline_id=baseline_id,
        quality_gain=quality_gain,
        incremental_cost_usd=incremental_cost,
        incremental_latency_seconds=incremental_seconds,
        severe_failures_avoided=failures_avoided,
        sharpe_inspired_gain=(quality_gain / downside_deviation if downside_deviation > 0 else None),
        quality_gain_per_incremental_dollar=(quality_gain / incremental_cost if incremental_cost > 0 else None),
        quality_gain_per_incremental_second=(quality_gain / incremental_seconds if incremental_seconds > 0 else None),
        severe_failures_avoided_per_incremental_dollar=(
            failures_avoided / incremental_cost if incremental_cost > 0 else None
        ),
    )
