"""Typed, serializable records for benchmark cases, runs, and aggregates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from ..ai.types import TaskType
from ..optimization.models import ArchitectureCandidate, ArchitectureMetrics
from ..optimization.tail_risk import TailRiskEstimate


class BenchmarkSplit(str, Enum):
    DEV = "dev"
    DEVELOPMENT = "dev"
    TUNING = "tuning"
    HELD_OUT = "held_out"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SystemOutcome(str, Enum):
    ANSWER = "ANSWER"
    VERIFY = "VERIFY"
    NEEDS_VERIFICATION = "VERIFY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    OUT_OF_DISTRIBUTION = "OUT_OF_DISTRIBUTION"
    INFEASIBLE = "INFEASIBLE"
    NO_CALL = "NO_CALL"


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    task_type: TaskType | str
    input: Any
    expected_answer: Any = None
    evaluator: str | None = None
    difficulty: Difficulty | str = Difficulty.MEDIUM
    risk_level: RiskLevel | str = RiskLevel.LOW
    required_capabilities: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    split: BenchmarkSplit | str = BenchmarkSplit.DEVELOPMENT

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("benchmark case id must not be empty")
        if self.expected_answer is None and self.evaluator is None:
            raise ValueError("a benchmark case requires expected_answer or evaluator")
        split = str(getattr(self.split, "value", self.split))
        if split not in {item.value for item in BenchmarkSplit}:
            raise ValueError(f"unknown benchmark split '{split}'")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("task_type", "difficulty", "risk_level", "split"):
            value = payload[key]
            if isinstance(value, Enum):
                payload[key] = value.value
        return payload


@dataclass(frozen=True)
class ArchitectureNode:
    id: str
    role: str
    optional: bool = False


@dataclass(frozen=True)
class ArchitectureTemplate:
    id: str
    name: str
    nodes: tuple[ArchitectureNode, ...]
    edges: tuple[tuple[str, str], ...]
    required_capabilities: tuple[str, ...] = ()
    privacy_class: str | None = None
    baseline_kind: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        identifiers = [node.id for node in self.nodes]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"architecture '{self.id}' has duplicate node ids")
        known = set(identifiers)
        for source, target in self.edges:
            if source not in known or target not in known:
                raise ValueError(f"architecture '{self.id}' has an edge to an unknown node")

    @property
    def roles(self) -> tuple[str, ...]:
        return tuple(node.role for node in self.nodes)

    def without_roles(self, roles: set[str], *, suffix: str) -> "ArchitectureTemplate":
        kept = tuple(node for node in self.nodes if node.role not in roles)
        kept_ids = {node.id for node in kept}
        return ArchitectureTemplate(
            id=f"{self.id}-{suffix}",
            name=f"{self.name} ({suffix.replace('_', ' ')})",
            nodes=kept,
            edges=tuple(
                (source, target)
                for source, target in self.edges
                if source in kept_ids and target in kept_ids
            ),
            required_capabilities=self.required_capabilities,
            privacy_class=self.privacy_class,
            baseline_kind=self.baseline_kind,
            metadata={**self.metadata, "ablation_of": self.id, "removed_roles": sorted(roles)},
        )


@dataclass(frozen=True)
class BenchmarkRun:
    benchmark_case_id: str
    task_type: str
    architecture_id: str
    agent_role: str
    provider: str
    model: str
    output: Any
    success: bool
    error_type: str | None
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float | None
    score: float | None
    passed: bool | None
    disagreement: float | None = None
    fallback: bool = False
    outcome: SystemOutcome = SystemOutcome.ANSWER
    repeat: int = 0
    seed: int | None = None
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    malformed_output: bool = False
    abstained: bool = False
    constraint_violations: tuple[str, ...] = ()
    confidence: float | None = None
    model_configuration: dict[str, Any] = field(default_factory=dict)
    prompt_config_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        return payload


@dataclass(frozen=True)
class ModelBenchmarkResult:
    provider: str
    model: str
    correctness: float
    rubric_score: float
    latency_mean_ms: float
    latency_p95_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float | None
    failure_rate: float
    malformed_output_rate: float
    abstention_rate: float
    constraint_violation_rate: float
    output_disagreement: float | None
    quality_variance: float
    sample_size: int
    quality_median: float | None
    quality_standard_error: float | None
    success_probability: float
    severe_failure_probability: float
    latency_median_ms: float
    latency_p90_ms: float
    cost_median_usd: float | None
    cost_p90_usd: float | None
    coverage: float
    quality_conditional_on_answering: float | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArchitectureBenchmarkResult:
    architecture_id: str
    architecture_name: str
    expected_quality: float
    cost: float | None
    latency: float
    failure_rate: float
    risk: float
    quality_variance: float
    sample_size: int
    tail_risk: TailRiskEstimate
    required_capabilities: tuple[str, ...] = ()
    privacy_class: str | None = None
    task_types: tuple[str, ...] = ()
    source: str = "benchmark"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_candidate(self) -> ArchitectureCandidate:
        if self.cost is None:
            raise ValueError(
                f"architecture '{self.architecture_id}' has unknown cost and cannot enter cost-aware optimization"
            )
        return ArchitectureCandidate(
            id=self.architecture_id,
            name=self.architecture_name,
            metrics=ArchitectureMetrics(
                quality=self.expected_quality,
                cost=self.cost,
                latency=self.latency,
                risk=self.risk,
                failure_rate=self.failure_rate,
                tail_risk=self.tail_risk,
                quality_variance=self.quality_variance,
            ),
            agents=tuple(self.metadata.get("agents", ())),
            required_capabilities=self.required_capabilities,
            privacy_class=self.privacy_class,
            metadata={
                **self.metadata,
                "source": self.source,
                "sample_size": self.sample_size,
                "task_types": list(self.task_types),
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AblationResult:
    architecture_id: str
    variant_id: str
    removed_roles: tuple[str, ...]
    quality_delta: float
    cost_delta: float | None
    latency_delta: float
    failure_rate_delta: float
    component_necessary: bool | None
    evidence_note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
