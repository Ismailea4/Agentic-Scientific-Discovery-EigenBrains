"""Minimal evaluation framework.

Runs an iterable of `EvalCase`s through a caller-supplied (possibly async)
function, optionally scores each output via a caller-supplied scorer, and can
persist results as JSONL and CSV. No built-in scoring — the scaffold never
fabricates quality numbers.
"""

from __future__ import annotations

import asyncio
import csv
import inspect
import json
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class EvalCase:
    case_id: str
    input: Any
    expected: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    case_id: str
    input: Any
    expected: Any
    actual: Any
    score: float | None = None
    passed: bool | None = None
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# A scorer returns either a bare score or a (score, passed) tuple.
Scorer = Callable[
    [EvalCase, Any],
    "float | tuple[float | None, bool | None] | Awaitable[float | tuple[float | None, bool | None]]",
]

_CSV_FIELDS = [
    "case_id",
    "input",
    "expected",
    "actual",
    "score",
    "passed",
    "latency_ms",
    "metadata",
    "timestamp",
]


class EvalRecorder:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str, suffix: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        return self.output_dir / f"{safe}.{suffix}"

    def write_jsonl(self, results: Iterable[EvalResult], name: str) -> Path:
        path = self._path(name, "jsonl")
        with path.open("w", encoding="utf-8") as fh:
            for result in results:
                fh.write(json.dumps(result.to_dict(), default=str) + "\n")
        return path

    def write_csv(self, results: Iterable[EvalResult], name: str) -> Path:
        path = self._path(name, "csv")
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS)
            writer.writeheader()
            for result in results:
                row = result.to_dict()
                row["input"] = json.dumps(row["input"], default=str)
                row["expected"] = json.dumps(row["expected"], default=str)
                row["actual"] = json.dumps(row["actual"], default=str)
                row["metadata"] = json.dumps(row["metadata"], default=str)
                writer.writerow(row)
        return path


async def run_evaluation(
    cases: Iterable[EvalCase],
    fn: Callable[[Any], Any],
    scorer: Scorer | None = None,
) -> list[EvalResult]:
    """Run `fn` over every case, timing each call and scoring if a scorer is given."""
    results: list[EvalResult] = []
    for case in cases:
        started = time.perf_counter()
        actual = fn(case.input)
        if inspect.isawaitable(actual):
            actual = await actual
        latency_ms = (time.perf_counter() - started) * 1000.0

        score: float | None = None
        passed: bool | None = None
        if scorer is not None:
            outcome = scorer(case, actual)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            if isinstance(outcome, tuple):
                score, passed = outcome
            else:
                score = outcome

        results.append(
            EvalResult(
                case_id=case.case_id,
                input=case.input,
                expected=case.expected,
                actual=actual,
                score=score,
                passed=passed,
                latency_ms=latency_ms,
                metadata=dict(case.metadata),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )
    return results
