"""Weak, task-specific priors and sufficient statistics for challenge updates."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from statistics import fmean, pvariance
from typing import Any, Sequence

from .models import BenchmarkRun
from .observations import ExecutionObservation, execution_observations


@dataclass(frozen=True)
class BetaPrior:
    alpha: float
    beta: float
    observed_successes: int
    observed_failures: int
    effective_prior_strength: float


@dataclass(frozen=True)
class ContinuousSufficientStatistics:
    n: int
    mean: float | None
    variance: float | None
    raw_bounded_observations: tuple[float, ...]


@dataclass(frozen=True)
class LogSufficientStatistics:
    n: int
    sum_log_x: float
    sum_log_x_squared: float


@dataclass(frozen=True)
class ArchitecturePrior:
    architecture_id: str
    scope: str
    task_type: str
    risk_level: str
    success: BetaPrior
    severe_failure: BetaPrior
    quality: ContinuousSufficientStatistics
    latency_log: LogSufficientStatistics
    cost_log: LogSufficientStatistics | None
    source_benchmark_version: str
    benchmark_date: str
    model_identifiers: tuple[str, ...]
    prompt_config_hashes: tuple[str, ...]
    observation_count: int
    prior_construction_method: str
    architecture_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BinaryEvidencePrior:
    """Weak, rapidly overridable priors for distinct operational quantities."""

    entity_kind: str
    entity_id: str
    scope: str
    task_type: str
    correctness_given_provider_success: BetaPrior
    severe_failure_given_provider_success: BetaPrior
    provider_availability: BetaPrior
    verification_rescue: BetaPrior | None
    prior_strength: float
    source_benchmark_version: str
    scoring_config_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _beta_prior(events: int, total: int, prior_strength: float) -> BetaPrior:
    probability = events / total if total else 0.5
    return BetaPrior(
        alpha=1.0 + probability * prior_strength,
        beta=1.0 + (1.0 - probability) * prior_strength,
        observed_successes=events,
        observed_failures=total - events,
        effective_prior_strength=prior_strength,
    )


def _continuous(values: list[float]) -> ContinuousSufficientStatistics:
    return ContinuousSufficientStatistics(
        n=len(values),
        mean=fmean(values) if values else None,
        variance=pvariance(values) if len(values) > 1 else (0.0 if values else None),
        raw_bounded_observations=tuple(values),
    )


def _log_stats(values: list[float]) -> LogSufficientStatistics:
    logs = [math.log(value) for value in values if value > 0]
    return LogSufficientStatistics(
        n=len(logs),
        sum_log_x=sum(logs),
        sum_log_x_squared=sum(value * value for value in logs),
    )


def construct_architecture_priors(
    runs: Sequence[BenchmarkRun],
    *,
    source_benchmark_version: str,
    benchmark_date: str,
    prior_strength: float,
    maximum_prior_strength: float,
    severe_failure_threshold: float,
    architecture_version: str = "A0-A6-v0",
) -> list[ArchitecturePrior]:
    if prior_strength < 0 or maximum_prior_strength < 0:
        raise ValueError("prior strengths must be >= 0")
    if prior_strength > maximum_prior_strength:
        raise ValueError("prior_strength exceeds the configured maximum")
    observations = execution_observations(
        runs, severe_failure_threshold=severe_failure_threshold
    )
    run_models: dict[str, set[str]] = defaultdict(set)
    run_hashes: dict[str, set[str]] = defaultdict(set)
    for run in runs:
        run_models[run.architecture_id].add(f"{run.provider}/{run.model}")
        if run.prompt_config_hash:
            run_hashes[run.architecture_id].add(run.prompt_config_hash)
    grouped: dict[tuple[str, str, str, str], list[ExecutionObservation]] = defaultdict(list)
    for row in observations:
        grouped[(row.architecture_id, "global", "*", "*")].append(row)
        grouped[(row.architecture_id, "task_risk", row.task_type, row.risk_level)].append(row)
    priors: list[ArchitecturePrior] = []
    for (architecture_id, scope, task_type, risk_level), rows in sorted(grouped.items()):
        quality = [float(row.quality) for row in rows if row.quality is not None]
        costs = [float(row.cost_usd) for row in rows if row.cost_usd is not None]
        priors.append(
            ArchitecturePrior(
                architecture_id=architecture_id,
                scope=scope,
                task_type=task_type,
                risk_level=risk_level,
                success=_beta_prior(sum(row.success for row in rows), len(rows), prior_strength),
                severe_failure=_beta_prior(sum(row.severe_failure for row in rows), len(rows), prior_strength),
                quality=_continuous(quality),
                latency_log=_log_stats([row.latency_ms for row in rows]),
                cost_log=(_log_stats(costs) if len(costs) == len(rows) else None),
                source_benchmark_version=source_benchmark_version,
                benchmark_date=benchmark_date,
                model_identifiers=tuple(sorted(run_models[architecture_id])),
                prompt_config_hashes=tuple(sorted(run_hashes[architecture_id])),
                observation_count=len(rows),
                prior_construction_method="empirical mean with bounded pseudo-observation strength",
                architecture_version=architecture_version,
            )
        )
    return priors


def update_beta_prior(prior: BetaPrior, *, successes: int, failures: int) -> BetaPrior:
    if successes < 0 or failures < 0:
        raise ValueError("challenge counts must be >= 0")
    return BetaPrior(
        alpha=prior.alpha + successes,
        beta=prior.beta + failures,
        observed_successes=prior.observed_successes + successes,
        observed_failures=prior.observed_failures + failures,
        effective_prior_strength=prior.effective_prior_strength,
    )


def construct_binary_evidence_priors(
    runs: Sequence[BenchmarkRun],
    *,
    source_benchmark_version: str,
    scoring_config_hash: str,
    prior_strength: float = 4.0,
    maximum_prior_strength: float = 5.0,
    severe_failure_threshold: float = 0.2,
) -> list[BinaryEvidencePrior]:
    """Create separate model/architecture/task priors without reliability mixing."""
    if not 0 <= severe_failure_threshold <= 1:
        raise ValueError("severe_failure_threshold must be in [0, 1]")
    if prior_strength < 0 or maximum_prior_strength < 0:
        raise ValueError("prior strengths must be >= 0")
    if prior_strength > maximum_prior_strength:
        raise ValueError("prior_strength exceeds the configured maximum")
    finals = [run for run in runs if run.metadata.get("final_output") is True]
    grouped: dict[tuple[str, str, str, str], list[BenchmarkRun]] = defaultdict(list)
    for run in finals:
        entities = (
            ("model", f"{run.provider}/{run.model}"),
            ("architecture", run.architecture_id),
        )
        for entity_kind, entity_id in entities:
            grouped[(entity_kind, entity_id, "global", "*")].append(run)
            grouped[(entity_kind, entity_id, "task_family", run.task_type)].append(run)
    output: list[BinaryEvidencePrior] = []
    for (entity_kind, entity_id, scope, task_type), rows in sorted(grouped.items()):
        provider_successes = [row for row in rows if row.success]
        correct = sum(row.passed is True for row in provider_successes)
        severe = sum(
            row.malformed_output
            or bool(row.constraint_violations)
            or row.score is None
            or float(row.score or 0.0) <= severe_failure_threshold
            for row in provider_successes
        )
        rescue_rows = [
            row for row in rows
            if row.metadata.get("verification_opportunity") is True
        ]
        rescued = sum(
            row.metadata.get("verification_rescued") is True for row in rescue_rows
        )
        output.append(
            BinaryEvidencePrior(
                entity_kind=entity_kind,
                entity_id=entity_id,
                scope=scope,
                task_type=task_type,
                correctness_given_provider_success=_beta_prior(
                    correct, len(provider_successes), prior_strength
                ),
                severe_failure_given_provider_success=_beta_prior(
                    severe, len(provider_successes), prior_strength
                ),
                provider_availability=_beta_prior(
                    len(provider_successes), len(rows), prior_strength
                ),
                verification_rescue=(
                    _beta_prior(rescued, len(rescue_rows), prior_strength)
                    if rescue_rows else None
                ),
                prior_strength=prior_strength,
                source_benchmark_version=source_benchmark_version,
                scoring_config_hash=scoring_config_hash,
            )
        )
    return output
