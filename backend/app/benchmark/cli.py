"""Offline CLI for aggregating previously recorded benchmark calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .artifacts import write_benchmark_artifacts
from .analysis import model_error_vectors
from .metrics import aggregate_architectures
from .models import BenchmarkRun, SystemOutcome
from .templates import architecture_templates
from ..optimization.covariance import analyze_error_vectors


def _load_runs(path: Path) -> list[BenchmarkRun]:
    runs: list[BenchmarkRun] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload: dict[str, Any] = json.loads(line)
        try:
            payload["outcome"] = SystemOutcome(payload.get("outcome", "ANSWER"))
            runs.append(BenchmarkRun(**payload))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid benchmark run at line {line_number}") from exc
    return runs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate recorded benchmark JSONL; this command never calls a model provider."
    )
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--split", action="append", required=True)
    parser.add_argument("--methodology", required=True)
    parser.add_argument("--lower-percentile", type=float, required=True)
    parser.add_argument("--severe-failure-threshold", type=float, required=True)
    parser.add_argument("--failure-threshold", type=float, required=True)
    args = parser.parse_args()

    runs = _load_runs(args.runs)
    results = aggregate_architectures(
        runs,
        architecture_templates(),
        lower_percentile=args.lower_percentile,
        severe_failure_threshold=args.severe_failure_threshold,
    )
    error_vectors = model_error_vectors(runs)
    correlation = (
        analyze_error_vectors(error_vectors, failure_threshold=args.failure_threshold)
        if len(error_vectors) >= 2
        else None
    )
    paths = write_benchmark_artifacts(
        args.output,
        runs=runs,
        architecture_results=results,
        correlation=correlation,
        experiment_metadata={
            "dataset": args.dataset,
            "splits": args.split,
            "methodology": args.methodology,
        },
        report_dir=args.report_dir,
    )
    print(f"wrote {len(paths)} scrubbed artifacts to {args.output.resolve()}")


if __name__ == "__main__":
    main()
