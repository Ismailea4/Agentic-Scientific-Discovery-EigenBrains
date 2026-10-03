"""Explicit failure categorization; no content-based guessing."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Sequence

from .models import BenchmarkRun, SystemOutcome


class FailureCategory(str, Enum):
    REASONING = "reasoning"
    EXTRACTION = "extraction"
    HALLUCINATION = "hallucination"
    FORMAT = "format"
    EVIDENCE = "evidence"
    TOOL_USE = "tool-use"
    TIMEOUT = "timeout"
    PROVIDER = "provider"
    OVER_REFUSAL = "over-refusal"
    UNDER_REFUSAL = "under-refusal"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FailureRecord:
    case_id: str
    architecture_id: str
    provider: str
    model: str
    category: FailureCategory
    error_type: str | None
    outcome: str
    score: float | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["category"] = self.category.value
        return payload


def _category(run: BenchmarkRun) -> FailureCategory:
    declared = run.metadata.get("failure_category")
    if declared is not None:
        try:
            return FailureCategory(str(declared))
        except ValueError:
            return FailureCategory.UNKNOWN
    if run.malformed_output:
        return FailureCategory.FORMAT
    if run.error_type and "timeout" in run.error_type.casefold():
        return FailureCategory.TIMEOUT
    if not run.success:
        return FailureCategory.PROVIDER
    if run.abstained and run.passed is False:
        return FailureCategory.OVER_REFUSAL
    if run.outcome is SystemOutcome.ANSWER and run.metadata.get("should_abstain") is True:
        return FailureCategory.UNDER_REFUSAL
    return FailureCategory.UNKNOWN


def analyze_failures(runs: Sequence[BenchmarkRun]) -> tuple[list[FailureRecord], dict[str, int]]:
    failed = [
        run for run in runs
        if run.metadata.get("final_output") is True
        and (not run.success or run.passed is False or run.abstained or run.malformed_output)
    ]
    records = [
        FailureRecord(
            case_id=run.benchmark_case_id,
            architecture_id=run.architecture_id,
            provider=run.provider,
            model=run.model,
            category=_category(run),
            error_type=run.error_type,
            outcome=run.outcome.value,
            score=run.score,
        )
        for run in failed
    ]
    counts = Counter(record.category.value for record in records)
    return records, dict(sorted(counts.items()))
