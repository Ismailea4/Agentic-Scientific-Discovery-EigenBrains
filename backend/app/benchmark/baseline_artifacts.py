"""Architecture Baseline v0 artifact and report generator."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..optimization.covariance import (
    ErrorCorrelationAnalysis,
    analyze_error_vectors,
    bootstrap_pairwise_metrics,
    diagonal_shrinkage_covariance,
)
from ..optimization.pareto import pareto_frontier
from .analysis import aggregate_model_reliability, aggregate_models, model_error_vectors
from .artifacts import SecretScrubber, _write_csv, _write_json, _write_jsonl
from .bounds import (
    ArchitectureBounds,
    bootstrap_dominance_probabilities,
    estimate_architecture_bounds,
    estimate_task_specific_bounds,
    robust_frontier,
)
from .cards import architecture_cards_markdown, build_architecture_cards
from .distributions import ArchitectureDistribution, summarize_runs
from .downside import DownsideRisk, empirical_downside_risk
from .failure_analysis import analyze_failures
from .marginal import MarginalAgentValue
from .models import AblationResult, ArchitectureBenchmarkResult, BenchmarkRun
from .observations import execution_observations
from .priors import (
    ArchitecturePrior,
    construct_architecture_priors,
    construct_binary_evidence_priors,
)
from .selective_replay import summarize_escalation_economics
from .pair_selection import compare_pair_selection_strategies


def _flatten_bounds(bounds: Sequence[ArchitectureBounds]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in bounds:
        row: dict[str, Any] = {
            "architecture_id": item.architecture_id,
            "task_type": item.task_type,
            "risk_level": item.risk_level,
            "split": item.split,
            "sample_size": item.sample_size,
            "confidence_level": item.latency.confidence_level,
        }
        for name in ("quality", "failure", "severe_failure", "cost", "latency"):
            interval = getattr(item, name)
            row[f"{name}_mean"] = None if interval is None else interval.estimate
            row[f"{name}_lcb"] = None if interval is None else interval.lower
            row[f"{name}_ucb"] = None if interval is None else interval.upper
            row[f"{name}_method"] = None if interval is None else interval.method
        for name in ("quality_median", "cost_median", "latency_median"):
            interval = getattr(item, name)
            row[f"{name}_estimate"] = None if interval is None else interval.estimate
            row[f"{name}_lcb"] = None if interval is None else interval.lower
            row[f"{name}_ucb"] = None if interval is None else interval.upper
        rows.append(row)
    return rows


def _downside_by_architecture(
    runs: Sequence[BenchmarkRun],
    *,
    severe_failure_threshold: float,
    confidence_level: float,
    resamples: int,
    seed: int,
) -> dict[str, DownsideRisk]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in execution_observations(runs, severe_failure_threshold=severe_failure_threshold):
        if row.quality is not None:
            grouped[row.architecture_id].append(float(row.quality))
    return {
        identifier: empirical_downside_risk(
            values,
            severe_failure_threshold=severe_failure_threshold,
            confidence_level=confidence_level,
            resamples=resamples,
            seed=seed + offset,
        )
        for offset, (identifier, values) in enumerate(sorted(grouped.items()))
    }


def _baseline_matrix(
    statistics: Sequence[ArchitectureDistribution],
    bounds: Sequence[ArchitectureBounds],
    downside: Mapping[str, DownsideRisk],
    empirical_ids: frozenset[str],
    robust_ids: frozenset[str],
) -> list[dict[str, Any]]:
    bounds_by_id = {item.architecture_id: item for item in bounds}
    rows: list[dict[str, Any]] = []
    for item in statistics:
        bound = bounds_by_id[item.architecture_id]
        tail = downside.get(item.architecture_id)
        rows.append(
            {
                **item.to_dict(),
                "quality_lcb": bound.quality.lower if bound.quality else None,
                "quality_ucb": bound.quality.upper if bound.quality else None,
                "cost_lcb": bound.cost.lower if bound.cost else None,
                "cost_ucb": bound.cost.upper if bound.cost else None,
                "latency_lcb": bound.latency.lower,
                "latency_ucb": bound.latency.upper,
                "failure_lcb": bound.failure.lower,
                "failure_ucb": bound.failure.upper,
                "severe_failure_lcb": bound.severe_failure.lower,
                "severe_failure_ucb": bound.severe_failure.upper,
                "cvar90_loss": tail.cvar_loss.get("0.90") if tail else None,
                "downside_semivariance": tail.downside_semivariance if tail else None,
                "pareto": item.architecture_id in empirical_ids,
                "robust_pareto": item.architecture_id in robust_ids,
            }
        )
    return rows


def _report(
    *,
    metadata: Mapping[str, Any],
    run_count: int,
    model_count: int,
    architecture_count: int,
    empirical_ids: Sequence[str],
    robust_ids: Sequence[str],
    uncertain_ids: Sequence[str],
    marginal_values: Sequence[MarginalAgentValue],
    stress_tests: Sequence[Mapping[str, Any]],
    routing_scenarios: Sequence[Mapping[str, Any]],
    priors: Sequence[ArchitecturePrior],
    pair_strategies: Sequence[Mapping[str, Any]],
    cards_markdown: str,
) -> str:
    justified = sorted(value.component for value in marginal_values if value.verdict == "JUSTIFIED BY BASELINE")
    unjustified = sorted(value.component for value in marginal_values if value.verdict != "JUSTIFIED BY BASELINE")
    return "\n".join(
        [
            "# Architecture Baseline v0",
            "",
            "This report is a prior over architecture behavior, not evidence about the future challenge.",
            "",
            "## Provenance",
            "",
            f"- Benchmark version: {metadata['benchmark_version']}",
            f"- Benchmark date: {metadata['benchmark_date']}",
            f"- Split: {metadata['split']}",
            f"- Confidence level: {float(metadata['confidence_level']):.0%}",
            f"- Raw execution observations: {run_count}",
            f"- Models observed: {model_count}",
            f"- Architectures observed: {architecture_count}",
            "",
            "## Efficient sets",
            "",
            f"- Empirical frontier: {', '.join(empirical_ids) or 'none'}",
            f"- Robust frontier: {', '.join(robust_ids) or 'none'}",
            f"- Statistically unresolved candidates: {', '.join(uncertain_ids) or 'none'}",
            "",
            "A point-estimate difference is not described as significant unless its paired/bounded evidence supports it.",
            "",
            "## Marginal agent economics",
            "",
            f"- Components justified by measured baseline: {', '.join(justified) or 'none measured'}",
            f"- Components not justified by measured baseline: {', '.join(unjustified) or 'none measured'}",
            "",
            "## Diversification diagnostics",
            "",
            f"- Pair-selection strategies compared: {len(pair_strategies)}",
            "- Joint-failure figures are complementarity diagnostics, not synthesized architecture scores.",
            "",
            "## Conditional verification and stress",
            "",
            f"- Routing scenarios recorded: {len(routing_scenarios)}",
            f"- Stress scenarios recorded: {len(stress_tests)}",
            "",
            "## Bayesian-update-ready priors",
            "",
            f"- Prior records exported: {len(priors)}",
            f"- Effective generic prior strength: {metadata['prior_strength']}",
            "- Challenge-specific evidence is expected to dominate these deliberately weak priors quickly.",
            "",
            "## Limitations",
            "",
            "- Conclusions are conditional on the measured cases, models, prompts, and runtime conditions.",
            "- CVaR entries with insufficient tail observations are explicitly labeled unstable.",
            "- Fractional allocation weights represent routing probabilities, never partially executed agents.",
            "- Security, privacy, and capability constraints remain hard constraints outside every utility tradeoff.",
            "",
            cards_markdown,
        ]
    ) + "\n"


def write_prechallenge_baseline_v0(
    benchmark_root: str | Path,
    *,
    runs: Sequence[BenchmarkRun],
    architecture_results: Sequence[ArchitectureBenchmarkResult],
    experiment_metadata: Mapping[str, Any],
    ablations: Sequence[AblationResult] = (),
    marginal_values: Sequence[MarginalAgentValue] = (),
    stress_tests: Sequence[Mapping[str, Any]] = (),
    routing_scenarios: Sequence[Mapping[str, Any]] = (),
    correlation: ErrorCorrelationAnalysis | None = None,
    scrubber: SecretScrubber | None = None,
) -> dict[str, Path]:
    """Generate v0 artifacts only from non-empty, single-split raw evidence."""

    if not runs or not architecture_results:
        raise ValueError("baseline v0 requires raw runs and measured architecture results")
    required = {
        "benchmark_version", "benchmark_date", "split", "confidence_level",
        "bootstrap_resamples", "seed", "severe_failure_threshold", "failure_threshold",
        "prior_strength", "maximum_prior_strength",
        "scoring_config_hash",
        "covariance_shrinkage_intensity",
    }
    missing = sorted(required - set(experiment_metadata))
    if missing:
        raise ValueError(f"missing baseline metadata: {', '.join(missing)}")
    represented_splits = {str(run.metadata.get("split", "unknown")) for run in runs}
    if represented_splits != {str(experiment_metadata["split"])}:
        raise ValueError("baseline artifact generation cannot silently mix benchmark splits")

    root = Path(benchmark_root).resolve()
    output = root / "artifacts" / "baseline_v0"
    reports = root / "reports"
    output.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    safe = scrubber or SecretScrubber.from_environment()
    confidence = float(experiment_metadata["confidence_level"])
    resamples = int(experiment_metadata["bootstrap_resamples"])
    seed = int(experiment_metadata["seed"])
    severe_threshold = float(experiment_metadata["severe_failure_threshold"])

    models = aggregate_models(runs, severe_failure_threshold=severe_threshold)
    reliability = aggregate_model_reliability(
        runs, severe_failure_threshold=severe_threshold
    )
    global_stats = summarize_runs(
        runs, severe_failure_threshold=severe_threshold, task_specific=False
    )
    task_stats = summarize_runs(
        runs, severe_failure_threshold=severe_threshold, task_specific=True
    )
    bounds = estimate_architecture_bounds(
        runs,
        severe_failure_threshold=severe_threshold,
        confidence_level=confidence,
        resamples=resamples,
        seed=seed,
    )
    task_bounds = estimate_task_specific_bounds(
        runs,
        severe_failure_threshold=severe_threshold,
        confidence_level=confidence,
        resamples=resamples,
        seed=seed,
    )
    dominance = bootstrap_dominance_probabilities(
        runs,
        severe_failure_threshold=severe_threshold,
        resamples=resamples,
        seed=seed,
    )
    robust = robust_frontier(bounds, probability_of_dominance=dominance)
    candidates = [result.to_candidate() for result in architecture_results if result.cost is not None]
    empirical = pareto_frontier(candidates)
    downside = _downside_by_architecture(
        runs,
        severe_failure_threshold=severe_threshold,
        confidence_level=confidence,
        resamples=resamples,
        seed=seed,
    )
    priors = construct_architecture_priors(
        runs,
        source_benchmark_version=str(experiment_metadata["benchmark_version"]),
        benchmark_date=str(experiment_metadata["benchmark_date"]),
        prior_strength=float(experiment_metadata["prior_strength"]),
        maximum_prior_strength=float(experiment_metadata["maximum_prior_strength"]),
        severe_failure_threshold=severe_threshold,
    )
    binary_priors = construct_binary_evidence_priors(
        runs,
        source_benchmark_version=str(experiment_metadata["benchmark_version"]),
        scoring_config_hash=str(experiment_metadata["scoring_config_hash"]),
        prior_strength=float(experiment_metadata["prior_strength"]),
        maximum_prior_strength=float(experiment_metadata["maximum_prior_strength"]),
        severe_failure_threshold=severe_threshold,
    )
    architecture_ids = {run.architecture_id for run in runs}
    escalation_economics = (
        summarize_escalation_economics(
            runs, severe_failure_threshold=severe_threshold
        )
        if {"S0", "S1", "S2", "S3", "S4"}.issubset(architecture_ids)
        else []
    )
    if correlation is None:
        vectors = model_error_vectors(runs)
        correlation = (
            analyze_error_vectors(
                vectors, failure_threshold=float(experiment_metadata["failure_threshold"])
            ) if len(vectors) >= 2 else None
        )
    else:
        vectors = model_error_vectors(runs)
    pairwise_uncertainty = (
        bootstrap_pairwise_metrics(
            vectors,
            failure_threshold=float(experiment_metadata["failure_threshold"]),
            confidence_level=confidence,
            resamples=resamples,
            seed=seed,
        )
        if correlation is not None and len(vectors) >= 2 else []
    )
    shrunk_covariance = (
        diagonal_shrinkage_covariance(
            correlation,
            intensity=float(experiment_metadata["covariance_shrinkage_intensity"]),
        )
        if correlation is not None else None
    )
    pair_strategies = []
    if (
        correlation is not None
        and len(vectors) >= 2
        and set(correlation.labels) == set(vectors)
    ):
        mean_quality = {
            label: 1.0 - sum(values.values()) / len(values)
            for label, values in vectors.items()
        }
        pair_strategies = [
            item.to_dict()
            for item in compare_pair_selection_strategies(
                correlation,
                vectors,
                mean_quality,
                failure_threshold=float(experiment_metadata["failure_threshold"]),
                correlation_penalty=float(experiment_metadata.get("correlation_penalty", 1.0)),
                seed=seed,
            )
        ]
    failure_records, _ = analyze_failures(runs)
    failure_modes: dict[str, list[str]] = defaultdict(list)
    for record in failure_records:
        if record.category.value not in failure_modes[record.architecture_id]:
            failure_modes[record.architecture_id].append(record.category.value)
    cards = build_architecture_cards(
        global_stats,
        task_stats,
        bounds,
        downside,
        empirical_frontier_ids=frozenset(empirical.frontier),
        robust_frontier_ids=frozenset(robust.frontier_ids),
        failure_modes=failure_modes,
        marginal_values=marginal_values,
        priors=priors,
        correlation_rows=correlation.to_rows() if correlation else (),
    )
    matrix = _baseline_matrix(
        global_stats,
        bounds,
        downside,
        frozenset(empirical.frontier),
        frozenset(robust.frontier_ids),
    )

    filenames = (
        "raw_runs.jsonl", "model_statistics.csv", "model_reliability.csv", "architecture_statistics.csv",
        "architecture_task_statistics.csv", "confidence_bounds.csv", "covariance.csv",
        "pairwise_uncertainty.json", "shrinkage_covariance.json",
        "failure_overlap.csv", "ablations.csv", "marginal_agent_value.csv", "escalation_economics.csv",
        "empirical_frontier.json", "robust_frontier.json", "tail_risk.csv",
        "stress_tests.csv", "routing_scenarios.csv", "priors.json", "binary_priors.json", "architecture_cards.json",
    )
    paths = {name: output / name for name in filenames}
    paths["PRECHALLENGE_BASELINE_V0.md"] = reports / "PRECHALLENGE_BASELINE_V0.md"
    _write_jsonl(paths["raw_runs.jsonl"], (run.to_dict() for run in runs), safe)
    _write_csv(paths["model_statistics.csv"], (item.to_dict() for item in models), tuple(models[0].to_dict()) if models else (), safe)
    _write_csv(
        paths["model_reliability.csv"],
        (item.to_dict() for item in reliability),
        tuple(reliability[0].to_dict()) if reliability else (),
        safe,
    )
    _write_csv(paths["architecture_statistics.csv"], matrix, tuple(matrix[0]) if matrix else (), safe)
    task_rows = [item.to_dict() for item in task_stats]
    _write_csv(paths["architecture_task_statistics.csv"], task_rows, tuple(task_rows[0]) if task_rows else (), safe)
    bound_rows = [
        {"scope": "global", **row} for row in _flatten_bounds(bounds)
    ] + [
        {"scope": "task_risk", **row} for row in _flatten_bounds(task_bounds)
    ]
    _write_csv(paths["confidence_bounds.csv"], bound_rows, tuple(bound_rows[0]) if bound_rows else (), safe)
    correlation_rows = correlation.to_rows() if correlation else []
    _write_csv(paths["covariance.csv"], correlation_rows, tuple(correlation_rows[0]) if correlation_rows else ("left", "right"), safe)
    _write_json(
        paths["pairwise_uncertainty.json"],
        [item.to_dict() for item in pairwise_uncertainty],
        safe,
    )
    _write_json(
        paths["shrinkage_covariance.json"],
        {
            "labels": list(shrunk_covariance.labels) if shrunk_covariance else [],
            "matrix": shrunk_covariance.matrix if shrunk_covariance else [],
            "correlations": shrunk_covariance.correlations if shrunk_covariance else [],
            "intensity": float(experiment_metadata["covariance_shrinkage_intensity"]),
            "target": "diagonal empirical covariance",
            "empirical_matrix_remains_authoritative": True,
        },
        safe,
    )
    _write_csv(
        paths["failure_overlap.csv"],
        correlation_rows,
        ("left", "right", "failure_overlap", "jaccard_similarity", "conditional_failure", "disagreement_rate", "sample_size"),
        safe,
    )
    _write_csv(paths["ablations.csv"], (item.to_dict() for item in ablations), tuple(ablations[0].to_dict()) if ablations else ("architecture_id", "variant_id"), safe)
    _write_csv(paths["marginal_agent_value.csv"], (item.to_dict() for item in marginal_values), tuple(marginal_values[0].to_dict()) if marginal_values else ("architecture_id", "component"), safe)
    _write_csv(
        paths["escalation_economics.csv"],
        (item.to_dict() for item in escalation_economics),
        tuple(escalation_economics[0].to_dict()) if escalation_economics else ("policy_id",),
        safe,
    )
    _write_json(
        paths["empirical_frontier.json"],
        {"frontier_ids": list(empirical.frontier), "dominated_ids": list(empirical.dominated)},
        safe,
    )
    _write_json(
        paths["robust_frontier.json"],
        {**robust.to_dict(), "pair_selection_diagnostics": pair_strategies},
        safe,
    )
    tail_rows = [{"architecture_id": identifier, **risk.to_dict()} for identifier, risk in sorted(downside.items())]
    _write_csv(paths["tail_risk.csv"], tail_rows, tuple(tail_rows[0]) if tail_rows else ("architecture_id",), safe)
    _write_csv(paths["stress_tests.csv"], stress_tests, tuple(stress_tests[0]) if stress_tests else ("scenario",), safe)
    _write_csv(paths["routing_scenarios.csv"], routing_scenarios, tuple(routing_scenarios[0]) if routing_scenarios else ("scenario",), safe)
    _write_json(paths["priors.json"], [item.to_dict() for item in priors], safe)
    _write_json(paths["binary_priors.json"], [item.to_dict() for item in binary_priors], safe)
    _write_json(paths["architecture_cards.json"], [item.to_dict() for item in cards], safe)
    cards_markdown = architecture_cards_markdown(cards)
    paths["PRECHALLENGE_BASELINE_V0.md"].write_text(
        str(
            safe.clean(
                _report(
                    metadata=experiment_metadata,
                    run_count=len(runs),
                    model_count=len(models),
                    architecture_count=len(global_stats),
                    empirical_ids=empirical.frontier,
                    robust_ids=robust.frontier_ids,
                    uncertain_ids=robust.uncertain_ids,
                    marginal_values=marginal_values,
                    stress_tests=stress_tests,
                    routing_scenarios=routing_scenarios,
                    priors=priors,
                    pair_strategies=pair_strategies,
                    cards_markdown=cards_markdown,
                )
            )
        ),
        encoding="utf-8",
    )
    return paths
