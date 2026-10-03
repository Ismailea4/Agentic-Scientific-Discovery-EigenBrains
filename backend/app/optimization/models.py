"""Performance and optimization records.

Metric fields stay optional on agent profiles because no benchmark exists
yet. Architecture candidates used for Pareto comparison carry the four
objective values explicitly, supplied by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .tail_risk import TailRiskEstimate


@dataclass(frozen=True)
class AgentMetrics:
    expected_quality: float | None = None
    cost: float | None = None
    latency: float | None = None
    failure_rate: float | None = None
    tail_risk: TailRiskEstimate | None = None
    quality_variance: float | None = None
    sample_size: int | None = None
    provenance: str | None = None
    required_capabilities: tuple[str, ...] = ()
    provider: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class AgentProfile:
    name: str
    metrics: AgentMetrics = field(default_factory=AgentMetrics)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArchitectureMetrics:
    """Objective values for one architecture. Higher quality is better.
    Lower cost, latency, and risk are better.
    """

    quality: float
    cost: float
    latency: float
    risk: float
    failure_rate: float | None = None
    tail_risk: TailRiskEstimate | None = None
    quality_variance: float | None = None


@dataclass(frozen=True)
class ArchitectureCandidate:
    id: str
    name: str
    metrics: ArchitectureMetrics
    agents: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    privacy_class: str | None = None
    provider: str | None = None
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OptimizationWeights:
    """Weights for `quality_weight*quality - lambda_risk*risk - eta_cost*cost - rho_latency*latency`.

    Defaults are neutral: quality counts, and the three penalties are zero.
    They are not a Fast / Balanced / Maximum Reliability preset. Negative
    weights are rejected so a penalty cannot be turned into a reward.
    """

    quality_weight: float = 1.0
    lambda_risk: float = 0.0
    eta_cost: float = 0.0
    rho_latency: float = 0.0

    def validate(self) -> None:
        for name in ("quality_weight", "lambda_risk", "eta_cost", "rho_latency"):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"weight '{name}' must be >= 0")


@dataclass(frozen=True)
class OptimizationConstraints:
    """Hard filters applied before any utility comparison.

    `available_capabilities=None` means the caller did not supply a capability
    context, so capability coverage is not checked. An empty set means the
    caller did supply one and nothing is granted. `accepted_privacy_classes`
    works the same way. Denied capabilities are always excluded. None of
    these checks can be bypassed by raising a weight.
    """

    min_quality: float | None = None
    max_cost: float | None = None
    max_latency: float | None = None
    max_risk: float | None = None
    max_failure_rate: float | None = None
    available_capabilities: frozenset[str] | None = None
    denied_capabilities: frozenset[str] = field(default_factory=frozenset)
    accepted_privacy_classes: frozenset[str] | None = None


@dataclass(frozen=True)
class OptimizationResult:
    selected_id: str | None
    utility: float | None
    feasible_ids: tuple[str, ...]
    frontier_ids: tuple[str, ...]
    dominated_ids: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_id": self.selected_id,
            "utility": self.utility,
            "feasible_ids": list(self.feasible_ids),
            "frontier_ids": list(self.frontier_ids),
            "dominated_ids": list(self.dominated_ids),
            "rejected": [
                {"id": identifier, "reason": why} for identifier, why in self.rejected
            ],
            "reasons": list(self.reasons),
        }
