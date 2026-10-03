"""Reconstruct reproducible architecture executions from raw call rows."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from .models import BenchmarkRun, SystemOutcome


@dataclass(frozen=True)
class ExecutionObservation:
    observation_id: str
    architecture_id: str
    case_id: str
    repeat: int
    task_type: str
    risk_level: str
    split: str
    quality: float | None
    success: bool
    severe_failure: bool
    abstained: bool
    malformed_output: bool
    answered: bool
    latency_ms: float
    cost_usd: float | None


def execution_observations(
    runs: Sequence[BenchmarkRun],
    *,
    severe_failure_threshold: float,
) -> list[ExecutionObservation]:
    if not 0 <= severe_failure_threshold <= 1:
        raise ValueError("severe_failure_threshold must be in [0, 1]")
    grouped: dict[tuple[str, str, int], list[BenchmarkRun]] = defaultdict(list)
    for run in runs:
        grouped[(run.architecture_id, run.benchmark_case_id, run.repeat)].append(run)
    observations: list[ExecutionObservation] = []
    for (architecture_id, case_id, repeat), rows in sorted(grouped.items()):
        finals = [row for row in rows if row.metadata.get("final_output") is True]
        final = finals[-1] if finals else rows[-1]
        successful_costs = [row.estimated_cost_usd for row in rows if row.success]
        cost = (
            None
            if any(value is None for value in successful_costs)
            else sum(float(value) for value in successful_costs)
        )
        answered = final.outcome is SystemOutcome.ANSWER and not final.abstained
        failed = (
            any(not row.success for row in rows)
            or final.passed is False
            or final.malformed_output
            or bool(final.constraint_violations)
            or final.outcome not in {SystemOutcome.ANSWER, SystemOutcome.VERIFY}
        )
        severe = failed and (
            final.score is None or float(final.score) <= severe_failure_threshold
        )
        observations.append(
            ExecutionObservation(
                observation_id=f"{case_id}#repeat-{repeat}",
                architecture_id=architecture_id,
                case_id=case_id,
                repeat=repeat,
                task_type=final.task_type,
                risk_level=str(final.metadata.get("risk_level", "unknown")),
                split=str(final.metadata.get("split", "unknown")),
                quality=None if final.score is None else float(final.score),
                success=not failed,
                severe_failure=severe,
                abstained=final.abstained,
                malformed_output=final.malformed_output,
                answered=answered,
                latency_ms=sum(row.latency_ms for row in rows),
                cost_usd=cost,
            )
        )
    return observations
