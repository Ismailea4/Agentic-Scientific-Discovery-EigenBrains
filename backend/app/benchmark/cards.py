"""Machine- and human-readable architecture baseline cards."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from .bounds import ArchitectureBounds
from .distributions import ArchitectureDistribution
from .downside import DownsideRisk
from .marginal import MarginalAgentValue
from .priors import ArchitecturePrior


@dataclass(frozen=True)
class ArchitectureCard:
    architecture_id: str
    sample_size: int
    mean_quality: float | None
    quality_confidence_interval: dict[str, Any] | None
    cost_per_request: float | None
    cost_confidence_interval: dict[str, Any] | None
    latency_p50_ms: float
    latency_p95_ms: float
    severe_failure_rate: float
    severe_failure_confidence_interval: dict[str, Any]
    cvar90_loss: float | None
    downside_semivariance: float | None
    best_task_types: tuple[str, ...]
    weak_task_types: tuple[str, ...]
    primary_failure_modes: tuple[str, ...]
    error_correlations: tuple[dict[str, Any], ...]
    pareto_status: str
    robust_pareto_status: str
    marginal_agent_values: tuple[dict[str, Any], ...]
    bayesian_priors: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_architecture_cards(
    global_statistics: Sequence[ArchitectureDistribution],
    task_statistics: Sequence[ArchitectureDistribution],
    bounds: Sequence[ArchitectureBounds],
    downside: Mapping[str, DownsideRisk],
    *,
    empirical_frontier_ids: frozenset[str],
    robust_frontier_ids: frozenset[str],
    failure_modes: Mapping[str, Sequence[str]] | None = None,
    marginal_values: Sequence[MarginalAgentValue] = (),
    priors: Sequence[ArchitecturePrior] = (),
    correlation_rows: Sequence[Mapping[str, Any]] = (),
) -> list[ArchitectureCard]:
    bounds_by_id = {item.architecture_id: item for item in bounds}
    marginal_by_id: dict[str, list[MarginalAgentValue]] = {}
    prior_by_id: dict[str, list[ArchitecturePrior]] = {}
    for value in marginal_values:
        marginal_by_id.setdefault(value.architecture_id, []).append(value)
    for prior in priors:
        prior_by_id.setdefault(prior.architecture_id, []).append(prior)
    task_by_id: dict[str, list[ArchitectureDistribution]] = {}
    for row in task_statistics:
        task_by_id.setdefault(row.architecture_id, []).append(row)
    cards: list[ArchitectureCard] = []
    for row in global_statistics:
        bound = bounds_by_id[row.architecture_id]
        tasks = [item for item in task_by_id.get(row.architecture_id, []) if item.quality_mean is not None]
        ranked = sorted(tasks, key=lambda item: (-float(item.quality_mean), item.task_type))
        cards.append(
            ArchitectureCard(
                architecture_id=row.architecture_id,
                sample_size=row.sample_size,
                mean_quality=row.quality_mean,
                quality_confidence_interval=bound.quality.to_dict() if bound.quality else None,
                cost_per_request=row.cost_mean_usd,
                cost_confidence_interval=bound.cost.to_dict() if bound.cost else None,
                latency_p50_ms=row.latency_median_ms,
                latency_p95_ms=row.latency_p95_ms,
                severe_failure_rate=row.severe_failure_probability,
                severe_failure_confidence_interval=bound.severe_failure.to_dict(),
                cvar90_loss=(downside[row.architecture_id].cvar_loss.get("0.90") if row.architecture_id in downside else None),
                downside_semivariance=(downside[row.architecture_id].downside_semivariance if row.architecture_id in downside else None),
                best_task_types=tuple(item.task_type for item in ranked[:3]),
                weak_task_types=tuple(item.task_type for item in ranked[-3:]),
                primary_failure_modes=tuple((failure_modes or {}).get(row.architecture_id, ())),
                error_correlations=tuple(
                    dict(item)
                    for item in correlation_rows
                    if str(item.get("left", "")).endswith(f"@{row.architecture_id}")
                    or str(item.get("right", "")).endswith(f"@{row.architecture_id}")
                ),
                pareto_status=("efficient" if row.architecture_id in empirical_frontier_ids else "dominated"),
                robust_pareto_status=(
                    "robust_frontier" if row.architecture_id in robust_frontier_ids else "robustly_dominated"
                ),
                marginal_agent_values=tuple(
                    value.to_dict() for value in marginal_by_id.get(row.architecture_id, [])
                ),
                bayesian_priors=tuple(
                    prior.to_dict() for prior in prior_by_id.get(row.architecture_id, [])
                ),
            )
        )
    return cards


def architecture_cards_markdown(cards: Sequence[ArchitectureCard]) -> str:
    lines = ["# Architecture Baseline Cards", ""]
    for card in cards:
        interval = card.quality_confidence_interval
        quality_ci = (
            "unavailable"
            if interval is None
            else f"[{interval['lower']:.4f}, {interval['upper']:.4f}] at {interval['confidence_level']:.0%}"
        )
        lines.extend(
            [
                f"## Architecture {card.architecture_id}",
                "",
                f"- Mean quality: {card.mean_quality if card.mean_quality is not None else 'unknown'}",
                f"- Quality interval: {quality_ci}",
                f"- Cost/request: {card.cost_per_request if card.cost_per_request is not None else 'unknown'}",
                f"- Latency p50 / p95: {card.latency_p50_ms:.2f} / {card.latency_p95_ms:.2f} ms",
                f"- Severe failure rate: {card.severe_failure_rate:.4f}",
                f"- CVaR90 loss: {card.cvar90_loss if card.cvar90_loss is not None else 'unstable/unavailable'}",
                f"- Empirical Pareto status: {card.pareto_status}",
                f"- Robust Pareto status: {card.robust_pareto_status}",
                f"- Best measured task types: {', '.join(card.best_task_types) or 'unresolved'}",
                f"- Weak measured task types: {', '.join(card.weak_task_types) or 'unresolved'}",
                f"- Primary failure modes: {', '.join(card.primary_failure_modes) or 'none classified'}",
                f"- Correlation comparisons: {len(card.error_correlations)}",
                f"- Marginal component evaluations: {len(card.marginal_agent_values)}",
                "",
            ]
        )
    return "\n".join(lines)
