"""Paired marginal economics for agents and architecture components."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import fmean
from typing import Any, Sequence

from .observations import ExecutionObservation
from .statistics import ConfidenceInterval, mcnemar_exact, paired_bootstrap_difference


@dataclass(frozen=True)
class MarginalAgentValue:
    architecture_id: str
    ablation_id: str
    component: str
    paired_sample_size: int
    quality_delta: float
    quality_delta_interval: ConfidenceInterval
    cost_delta_usd: float | None
    latency_delta_ms: float
    tail_risk_delta: float
    severe_failure_delta: float
    severe_failure_p_value: float
    marginal_quality_per_dollar: float | None
    marginal_quality_per_second: float | None
    marginal_tail_risk_reduction_per_dollar: float | None
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def marginal_agent_value(
    full: Sequence[ExecutionObservation],
    ablated: Sequence[ExecutionObservation],
    *,
    architecture_id: str,
    ablation_id: str,
    component: str,
    confidence_level: float = 0.95,
    resamples: int = 2000,
    seed: int = 0,
) -> MarginalAgentValue:
    full_by_id = {row.observation_id: row for row in full}
    ablated_by_id = {row.observation_id: row for row in ablated}
    paired_ids = sorted(set(full_by_id) & set(ablated_by_id))
    if not paired_ids or set(full_by_id) != set(ablated_by_id):
        raise ValueError("marginal analysis requires identical paired observations")
    full_quality = [full_by_id[key].quality for key in paired_ids]
    ablated_quality = [ablated_by_id[key].quality for key in paired_ids]
    if any(value is None for value in (*full_quality, *ablated_quality)):
        raise ValueError("paired marginal quality observations must be complete")
    quality_interval = paired_bootstrap_difference(
        [float(value) for value in full_quality],
        [float(value) for value in ablated_quality],
        confidence_level=confidence_level,
        resamples=resamples,
        seed=seed,
    )
    full_cost = [full_by_id[key].cost_usd for key in paired_ids]
    ablated_cost = [ablated_by_id[key].cost_usd for key in paired_ids]
    cost_delta = (
        None if any(value is None for value in (*full_cost, *ablated_cost))
        else fmean(float(value) for value in full_cost) - fmean(float(value) for value in ablated_cost)
    )
    latency_delta = fmean(full_by_id[key].latency_ms for key in paired_ids) - fmean(
        ablated_by_id[key].latency_ms for key in paired_ids
    )
    severe_delta = fmean(float(full_by_id[key].severe_failure) for key in paired_ids) - fmean(
        float(ablated_by_id[key].severe_failure) for key in paired_ids
    )
    def worst_decile_loss(rows: dict[str, ExecutionObservation]) -> float:
        losses = sorted(
            (1.0 - float(rows[key].quality) for key in paired_ids),
            reverse=True,
        )
        return fmean(losses[: max(1, round(len(losses) * 0.1))])

    full_tail = worst_decile_loss(full_by_id)
    ablated_tail = worst_decile_loss(ablated_by_id)
    tail_delta = full_tail - ablated_tail
    severe_test = mcnemar_exact(
        [not full_by_id[key].severe_failure for key in paired_ids],
        [not ablated_by_id[key].severe_failure for key in paired_ids],
    )
    meaningful = quality_interval.lower > 0 or (
        severe_delta < 0 and severe_test.p_value <= 1.0 - confidence_level
    )
    verdict = "JUSTIFIED BY BASELINE" if meaningful else "NOT JUSTIFIED BY BASELINE"
    return MarginalAgentValue(
        architecture_id=architecture_id,
        ablation_id=ablation_id,
        component=component,
        paired_sample_size=len(paired_ids),
        quality_delta=quality_interval.estimate,
        quality_delta_interval=quality_interval,
        cost_delta_usd=cost_delta,
        latency_delta_ms=latency_delta,
        tail_risk_delta=tail_delta,
        severe_failure_delta=severe_delta,
        severe_failure_p_value=severe_test.p_value,
        marginal_quality_per_dollar=(
            quality_interval.estimate / cost_delta if cost_delta is not None and cost_delta > 0 else None
        ),
        marginal_quality_per_second=(
            quality_interval.estimate / (latency_delta / 1000.0) if latency_delta > 0 else None
        ),
        marginal_tail_risk_reduction_per_dollar=(
            -tail_delta / cost_delta if cost_delta is not None and cost_delta > 0 else None
        ),
        verdict=verdict,
    )
