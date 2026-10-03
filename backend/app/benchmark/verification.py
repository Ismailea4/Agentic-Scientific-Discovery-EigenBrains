"""Explicit verification policies whose thresholds must come from tuning data."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from enum import Enum
from statistics import fmean
from typing import Any, Sequence

from .models import BenchmarkRun
from .observations import execution_observations


class VerificationPolicy(str, Enum):
    NEVER = "never_verify"
    ALWAYS = "always_verify"
    ON_DISAGREEMENT = "verify_on_disagreement"
    ON_DIFFICULTY = "verify_on_difficulty"
    ON_HIGH_RISK = "verify_on_high_risk"


def should_verify(
    policy: VerificationPolicy,
    *,
    disagreement: float | None,
    disagreement_threshold: float | None,
    difficulty: str,
    difficult_levels: frozenset[str],
    risk_level: str,
    high_risk_levels: frozenset[str],
) -> bool:
    if policy is VerificationPolicy.NEVER:
        return False
    if policy is VerificationPolicy.ALWAYS:
        return True
    if policy is VerificationPolicy.ON_DISAGREEMENT:
        if disagreement_threshold is None:
            raise ValueError("a tuning-derived disagreement threshold is required")
        return disagreement is not None and disagreement >= disagreement_threshold
    if policy is VerificationPolicy.ON_DIFFICULTY:
        return difficulty in difficult_levels
    return risk_level in high_risk_levels


@dataclass(frozen=True)
class VerificationPolicyResult:
    policy: str
    sample_size: int
    quality: float | None
    cost_usd: float | None
    latency_ms: float
    severe_failure_rate: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_verification_policies(
    runs: Sequence[BenchmarkRun],
    *,
    severe_failure_threshold: float,
) -> list[VerificationPolicyResult]:
    observations = execution_observations(runs, severe_failure_threshold=severe_failure_threshold)
    policy_by_architecture: dict[str, str] = {}
    for run in runs:
        policy = run.metadata.get("verification_policy")
        if policy:
            policy_by_architecture[run.architecture_id] = str(policy)
    grouped = defaultdict(list)
    for row in observations:
        grouped[policy_by_architecture.get(row.architecture_id, "unspecified")].append(row)
    results: list[VerificationPolicyResult] = []
    for policy, rows in sorted(grouped.items()):
        quality = [float(row.quality) for row in rows if row.quality is not None]
        costs = [row.cost_usd for row in rows]
        results.append(
            VerificationPolicyResult(
                policy=policy,
                sample_size=len(rows),
                quality=fmean(quality) if quality else None,
                cost_usd=(None if any(value is None for value in costs) else fmean(float(value) for value in costs)),
                latency_ms=fmean(row.latency_ms for row in rows),
                severe_failure_rate=sum(row.severe_failure for row in rows) / len(rows),
            )
        )
    return results
