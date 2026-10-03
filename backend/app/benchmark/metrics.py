"""Aggregate measured runs without inventing missing scores or prices."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from statistics import fmean, pvariance

from ..optimization.tail_risk import empirical_tail_risk
from .models import ArchitectureBenchmarkResult, ArchitectureTemplate, BenchmarkRun, SystemOutcome


def aggregate_architectures(
    runs: Iterable[BenchmarkRun],
    templates: Sequence[ArchitectureTemplate],
    *,
    lower_percentile: float,
    severe_failure_threshold: float,
) -> list[ArchitectureBenchmarkResult]:
    """Aggregate calls into architecture-level execution metrics.

    Calls sharing architecture, case, and repeat form one execution. Latency and
    cost are summed. The row marked ``metadata.final_output`` supplies the score;
    absent that marker, the final call in the execution is used. If any successful
    call has unknown price, the architecture cost remains unknown rather than zero.
    """

    template_by_id = {template.id: template for template in templates}
    grouped: dict[tuple[str, str, int], list[BenchmarkRun]] = defaultdict(list)
    for run in runs:
        grouped[(run.architecture_id, run.benchmark_case_id, run.repeat)].append(run)

    executions: dict[str, list[dict[str, object]]] = defaultdict(list)
    for (architecture_id, case_id, repeat), rows in grouped.items():
        final_rows = [row for row in rows if row.metadata.get("final_output") is True]
        final = final_rows[-1] if final_rows else rows[-1]
        known_cost = all(not row.success or row.estimated_cost_usd is not None for row in rows)
        total_cost = (
            sum(float(row.estimated_cost_usd or 0.0) for row in rows if row.success)
            if known_cost
            else None
        )
        executions[architecture_id].append(
            {
                "case_id": case_id,
                "repeat": repeat,
                "score": final.score,
                "cost": total_cost,
                "latency": sum(row.latency_ms for row in rows),
                "failed": any(not row.success for row in rows)
                or final.passed is False
                or final.malformed_output
                or bool(final.constraint_violations)
                or final.outcome not in {SystemOutcome.ANSWER, SystemOutcome.VERIFY},
                "task_type": final.task_type,
                "difficulty": final.metadata.get("difficulty"),
                "risk_level": final.metadata.get("risk_level"),
            }
        )

    results: list[ArchitectureBenchmarkResult] = []
    for architecture_id in sorted(executions):
        rows = executions[architecture_id]
        scores = [float(row["score"]) for row in rows if row["score"] is not None]
        if not scores:
            continue
        tail = empirical_tail_risk(
            scores,
            lower_percentile=lower_percentile,
            severe_failure_threshold=severe_failure_threshold,
        )
        costs = [row["cost"] for row in rows]
        average_cost = None if any(value is None for value in costs) else fmean(float(value) for value in costs)
        failures = sum(bool(row["failed"]) for row in rows) / len(rows)
        lower_score = tail.lower_percentile_score if tail.lower_percentile_score is not None else min(scores)
        risk = max(1.0 - lower_score, tail.severe_failure_rate or 0.0, failures)
        template = template_by_id.get(architecture_id)
        results.append(
            ArchitectureBenchmarkResult(
                architecture_id=architecture_id,
                architecture_name=template.name if template else architecture_id,
                expected_quality=fmean(scores),
                cost=average_cost,
                latency=fmean(float(row["latency"]) for row in rows),
                failure_rate=failures,
                risk=risk,
                quality_variance=pvariance(scores) if len(scores) > 1 else 0.0,
                sample_size=len(rows),
                tail_risk=tail,
                required_capabilities=template.required_capabilities if template else (),
                privacy_class=template.privacy_class if template else None,
                task_types=tuple(sorted({str(row["task_type"]) for row in rows})),
                metadata={
                    "agents": list(template.roles) if template else [],
                    "difficulty_levels": sorted(
                        {str(row["difficulty"]) for row in rows if row["difficulty"] is not None}
                    ),
                    "risk_levels": sorted(
                        {str(row["risk_level"]) for row in rows if row["risk_level"] is not None}
                    ),
                },
            )
        )
    return results
