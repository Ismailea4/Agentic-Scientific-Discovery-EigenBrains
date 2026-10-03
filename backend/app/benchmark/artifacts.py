"""Write scrubbed benchmark evidence using the project's normalized records."""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..core.redaction import is_secret_key, redact
from ..optimization.covariance import ErrorCorrelationAnalysis
from ..optimization.pareto import pareto_frontier
from .analysis import aggregate_models
from .baselines import identify_baselines
from .calibration import CalibrationResult, calibration_metrics
from .failure_analysis import analyze_failures
from .models import AblationResult, ArchitectureBenchmarkResult, BenchmarkRun, ModelBenchmarkResult
from .statistics import architecture_confidence_intervals


class SecretScrubber:
    """Remove secret fields, known credential patterns, and exact secret values."""

    def __init__(self, secret_values: Iterable[str] = ()) -> None:
        self._secret_values = tuple(
            sorted(
                {value for value in secret_values if isinstance(value, str) and len(value) >= 6},
                key=len,
                reverse=True,
            )
        )

    @classmethod
    def from_environment(cls) -> "SecretScrubber":
        return cls(value for name, value in os.environ.items() if is_secret_key(name) and value)

    def clean(self, value: Any) -> Any:
        if is_dataclass(value):
            value = asdict(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Mapping):
            cleaned_mapping: dict[str, Any] = {}
            for key, item in value.items():
                raw_key = str(key)
                cleaned_key = self.clean(raw_key)
                cleaned_mapping[str(cleaned_key)] = (
                    "[redacted]" if is_secret_key(raw_key) else self.clean(item)
                )
            return cleaned_mapping
        if isinstance(value, (list, tuple, set, frozenset)):
            return [self.clean(item) for item in value]
        cleaned = redact(value)
        if isinstance(cleaned, str):
            for secret in self._secret_values:
                cleaned = cleaned.replace(secret, "[redacted]")
        return cleaned


def _write_json(path: Path, value: Any, scrubber: SecretScrubber) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(scrubber.clean(value), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Iterable[Any], scrubber: SecretScrubber) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(scrubber.clean(row), sort_keys=True, ensure_ascii=False) + "\n")


def _write_csv(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    fieldnames: Sequence[str],
    scrubber: SecretScrubber,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            cleaned = scrubber.clean(row)
            writer.writerow(
                {
                    key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
                    for key, value in cleaned.items()
                }
            )


def _architecture_rows(results: Sequence[ArchitectureBenchmarkResult]) -> list[dict[str, Any]]:
    return [
        {
            "architecture_id": result.architecture_id,
            "architecture_name": result.architecture_name,
            "expected_quality": result.expected_quality,
            "cost_usd": result.cost,
            "latency_ms": result.latency,
            "failure_rate": result.failure_rate,
            "risk": result.risk,
            "quality_variance": result.quality_variance,
            "sample_size": result.sample_size,
            "task_types": list(result.task_types),
            "source": result.source,
        }
        for result in results
    ]


def _tail_rows(results: Sequence[ArchitectureBenchmarkResult]) -> list[dict[str, Any]]:
    return [
        {
            "architecture_id": result.architecture_id,
            "sample_size": result.tail_risk.sample_size,
            "alpha": result.tail_risk.alpha,
            "worst_case_score": result.tail_risk.worst_case_score,
            "lower_percentile_score": result.tail_risk.lower_percentile_score,
            "severe_failure_rate": result.tail_risk.severe_failure_rate,
            "cvar_score": result.tail_risk.cvar_score,
            "downside_risk": result.tail_risk.score,
        }
        for result in results
    ]


def _markdown_report(
    results: Sequence[ArchitectureBenchmarkResult],
    models: Sequence[ModelBenchmarkResult],
    runs: Sequence[BenchmarkRun],
    frontier_ids: Sequence[str],
    metadata: Mapping[str, Any],
    failure_counts: Mapping[str, int],
) -> str:
    dataset = metadata.get("dataset", "unspecified")
    splits = metadata.get("splits", sorted({str(run.metadata.get("split", "unknown")) for run in runs}))
    lines = [
        "# EigenBrains benchmark report",
        "",
        "Status: BENCHMARK evidence from recorded executions; never SAMPLE or LIVE telemetry.",
        "",
        "## Dataset and methodology",
        "",
        f"- Dataset: {dataset}",
        f"- Splits represented: {', '.join(splits) if isinstance(splits, list) else splits}",
        f"- Recorded calls: {len(runs)}",
        f"- Measured models: {len(models)}",
        f"- Measured architectures: {len(results)}",
        f"- Methodology: {metadata.get('methodology', 'normalized repeated measurements')}",
        "",
        "## Models",
        "",
        "| Provider/model | Correctness | Score | Cost (USD) | Mean latency (ms) | Failures | n |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in models:
        cost = "unknown" if result.estimated_cost_usd is None else f"{result.estimated_cost_usd:.8f}"
        lines.append(
            f"| {result.provider}/{result.model} | {result.correctness:.4f} | {result.rubric_score:.4f} | "
            f"{cost} | {result.latency_mean_ms:.2f} | {result.failure_rate:.4f} | {result.sample_size} |"
        )
    lines.extend(
        [
            "",
            "## Architecture performance and Pareto frontier",
            "",
            f"Non-dominated architectures with known cost: {', '.join(frontier_ids) or 'none'}.",
            "",
            "| Architecture | Quality | Cost (USD) | Latency (ms) | Failure rate | Risk | n |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for result in results:
        cost = "unknown" if result.cost is None else f"{result.cost:.8f}"
        lines.append(
            f"| {result.architecture_id} | {result.expected_quality:.4f} | {cost} | "
            f"{result.latency:.2f} | {result.failure_rate:.4f} | {result.risk:.4f} | {result.sample_size} |"
        )
    lines.extend(
        [
            "",
            "## Correlation, ablations, tail risk, calibration, and failures",
            "",
            "Detailed machine-readable tables accompany this report. Findings are reported only when measured.",
            f"Failure categories: {json.dumps(dict(failure_counts), sort_keys=True)}.",
            "",
            "## Limitations",
            "",
            "- Results apply only to the recorded dataset, split, models, prompts, prices, and runtime conditions.",
            "- Correlation is descriptive and does not establish causal independence.",
            "- Small samples can make intervals, calibration, variance, and lower-tail estimates unstable.",
            "- Held-out results must not be used to choose weights or thresholds.",
            "- Generic prior results do not establish performance on the eventual challenge.",
        ]
    )
    unknown = [result.architecture_id for result in results if result.cost is None]
    if unknown:
        lines.append(
            "- Excluded from cost-aware Pareto analysis because price was unknown: "
            + ", ".join(sorted(unknown))
            + "."
        )
    return "\n".join(lines) + "\n"


def write_benchmark_artifacts(
    output_dir: str | Path,
    *,
    runs: Sequence[BenchmarkRun],
    architecture_results: Sequence[ArchitectureBenchmarkResult],
    model_results: Sequence[ModelBenchmarkResult] | None = None,
    ablations: Sequence[AblationResult] = (),
    correlation: ErrorCorrelationAnalysis | None = None,
    calibration: CalibrationResult | None = None,
    experiment_metadata: Mapping[str, Any] | None = None,
    report_dir: str | Path | None = None,
    scrubber: SecretScrubber | None = None,
) -> dict[str, Path]:
    """Write the complete evidence bundle without inventing absent measurements."""

    if not runs or not architecture_results:
        raise ValueError("artifact generation requires measured runs and architecture results")
    destination = Path(output_dir).resolve()
    reports = Path(report_dir).resolve() if report_dir is not None else destination.parent / "reports"
    destination.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    safe = scrubber or SecretScrubber.from_environment()
    models = list(model_results) if model_results is not None else aggregate_models(runs)
    calibration_result = calibration or calibration_metrics(runs)
    failure_records, failure_counts = analyze_failures(runs)
    known_cost = [result.to_candidate() for result in architecture_results if result.cost is not None]
    frontier = pareto_frontier(known_cost)
    frontier_results = [
        result.to_dict() for result in architecture_results if result.architecture_id in frontier.frontier
    ]
    metadata = dict(experiment_metadata or {})
    statistics_config = metadata.get("statistics", {})
    confidence_intervals = architecture_confidence_intervals(
        runs,
        confidence_level=float(statistics_config.get("confidence_level", 0.95)),
        resamples=int(statistics_config.get("bootstrap_resamples", 2000)),
        seed=int(statistics_config.get("seed", 0)),
    )
    summary = {
        "evidence_state": "BENCHMARK",
        "dataset": metadata.get("dataset"),
        "splits": metadata.get("splits", sorted({str(run.metadata.get("split", "unknown")) for run in runs})),
        "methodology": metadata.get("methodology"),
        "baselines": identify_baselines(architecture_results),
        "recorded_calls": len(runs),
        "measured_models": len(models),
        "measured_architectures": len(architecture_results),
        "pareto_frontier_ids": list(frontier.frontier),
        "excluded_unknown_cost_ids": sorted(
            result.architecture_id for result in architecture_results if result.cost is None
        ),
        "failure_case_count": len(failure_records),
        "failure_categories": failure_counts,
        "architecture_results": [result.to_dict() for result in architecture_results],
        "model_results": [result.to_dict() for result in models],
        "confidence_intervals": confidence_intervals,
    }
    paths = {
        name: destination / name
        for name in (
            "runs.jsonl",
            "model_summary.csv",
            "architecture_summary.csv",
            "ablation_results.csv",
            "error_correlation.csv",
            "failure_overlap.csv",
            "pareto_frontier.json",
            "calibration.json",
            "tail_risk.csv",
            "failure_cases.json",
            "benchmark_summary.json",
        )
    }
    paths["BENCHMARK_REPORT.md"] = reports / "BENCHMARK_REPORT.md"
    _write_jsonl(paths["runs.jsonl"], (run.to_dict() for run in runs), safe)
    _write_csv(
        paths["model_summary.csv"],
        (result.to_dict() for result in models),
        (
            "provider", "model", "correctness", "rubric_score", "latency_mean_ms", "latency_p95_ms",
            "input_tokens", "output_tokens", "estimated_cost_usd", "failure_rate",
            "malformed_output_rate", "abstention_rate", "constraint_violation_rate",
            "output_disagreement", "quality_variance", "sample_size", "metadata",
        ),
        safe,
    )
    _write_csv(
        paths["architecture_summary.csv"],
        _architecture_rows(architecture_results),
        (
            "architecture_id", "architecture_name", "expected_quality", "cost_usd", "latency_ms",
            "failure_rate", "risk", "quality_variance", "sample_size", "task_types", "source",
        ),
        safe,
    )
    _write_csv(
        paths["ablation_results.csv"],
        (result.to_dict() for result in ablations),
        (
            "architecture_id", "variant_id", "removed_roles", "quality_delta", "cost_delta",
            "latency_delta", "failure_rate_delta", "component_necessary", "evidence_note",
        ),
        safe,
    )
    correlation_rows = correlation.to_rows() if correlation else []
    _write_csv(
        paths["error_correlation.csv"],
        correlation_rows,
        (
            "left", "right", "covariance", "correlation", "failure_overlap",
            "disagreement_rate", "jaccard_similarity", "conditional_failure", "sample_size",
        ),
        safe,
    )
    _write_csv(
        paths["failure_overlap.csv"],
        correlation_rows,
        (
            "left", "right", "failure_overlap", "jaccard_similarity",
            "conditional_failure", "disagreement_rate", "sample_size",
        ),
        safe,
    )
    _write_json(paths["pareto_frontier.json"], frontier_results, safe)
    _write_json(paths["calibration.json"], calibration_result.to_dict(), safe)
    _write_csv(
        paths["tail_risk.csv"],
        _tail_rows(architecture_results),
        (
            "architecture_id", "sample_size", "alpha", "worst_case_score", "lower_percentile_score",
            "severe_failure_rate", "cvar_score", "downside_risk",
        ),
        safe,
    )
    _write_json(
        paths["failure_cases.json"],
        {"counts": failure_counts, "failures": [record.to_dict() for record in failure_records]},
        safe,
    )
    _write_json(paths["benchmark_summary.json"], summary, safe)
    paths["BENCHMARK_REPORT.md"].write_text(
        str(safe.clean(_markdown_report(architecture_results, models, runs, frontier.frontier, metadata, failure_counts))),
        encoding="utf-8",
    )
    return paths
