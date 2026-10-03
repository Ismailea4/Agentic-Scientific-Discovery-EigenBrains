"""Offline empirical report for the bounded single-model pilot."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from statistics import fmean, median
from typing import Any, Mapping, Sequence

from ..optimization.covariance import analyze_error_vectors
from .artifacts import SecretScrubber, _write_json
from .bounds import wilson_interval
from .models import BenchmarkRun
from .statistics import bootstrap_confidence_interval, mcnemar_exact, paired_bootstrap_difference


# The preregistered evaluator remains authoritative. These narrow, case-specific
# aliases are reported only as a sensitivity audit after the pilot exposed that
# exact string matching treats accepted taxonomy synonyms and comma whitespace as
# incorrect. New aliases must be justified against the frozen case contract.
_SENSITIVITY_ACCEPTED_OUTPUTS = {
    "dev-critique-01": {"overgeneralization", "hasty generalization"},
    "dev-critique-02": {
        "causal_inference",
        "causal inference",
        "false cause",
        "correlation does not imply causation",
    },
    "dev-planning-01": {"pilot,projection,full"},
    "dev-planning-02": {"measure,compare,select"},
}


def _label(run: BenchmarkRun) -> str:
    return f"{run.provider}/{run.model}"


def _normalized_audit_output(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip().casefold()
    normalized = re.sub(r"\s*,\s*", ",", normalized)
    return normalized.rstrip(". !?;:")


def _sensitivity_pass(run: BenchmarkRun) -> bool:
    """Return the frozen result plus narrowly adjudicated formatting aliases."""
    if run.passed is True:
        return True
    if not run.success or run.malformed_output:
        return False
    accepted = _SENSITIVITY_ACCEPTED_OUTPUTS.get(run.benchmark_case_id)
    return bool(accepted and _normalized_audit_output(run.output) in accepted)


def _percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(rows)


def _validated_groups(runs: Sequence[BenchmarkRun]) -> dict[str, list[BenchmarkRun]]:
    grouped: dict[str, list[BenchmarkRun]] = defaultdict(list)
    for run in runs:
        grouped[_label(run)].append(run)
    if not grouped:
        raise ValueError("pilot report requires runs")
    expected: set[str] | None = None
    for label, rows in grouped.items():
        case_ids = {row.benchmark_case_id for row in rows}
        if len(case_ids) != len(rows):
            raise ValueError(f"pilot requires one observation per case for {label}")
        if expected is None:
            expected = case_ids
        elif case_ids != expected:
            raise ValueError("pilot models do not have identical paired case coverage")
    return dict(sorted(grouped.items()))


def build_pilot_report(
    runs: Sequence[BenchmarkRun],
    *,
    confidence_level: float = 0.95,
    resamples: int = 5000,
    seed: int = 0,
    severe_failure_threshold: float = 0.2,
    pilot_cost_ceiling_usd: float = 0.20,
    preflight_projected_cost_usd: float = 0.18763776,
) -> dict[str, Any]:
    groups = _validated_groups(runs)
    case_ids = sorted(next(iter(groups.values())), key=lambda row: row.benchmark_case_id)
    ordered_cases = [row.benchmark_case_id for row in case_ids]
    by_label_case = {
        label: {row.benchmark_case_id: row for row in rows}
        for label, rows in groups.items()
    }
    model_rows: list[dict[str, Any]] = []
    task_rows: list[dict[str, Any]] = []
    error_vectors: dict[str, dict[str, float]] = {}
    sensitivity_error_vectors: dict[str, dict[str, float]] = {}

    for offset, (label, rows) in enumerate(groups.items()):
        aligned = [by_label_case[label][case_id] for case_id in ordered_cases]
        qualities = [float(row.score or 0.0) for row in aligned]
        successful_qualities = [float(row.score or 0.0) for row in aligned if row.success]
        latencies = [row.latency_ms for row in aligned]
        passed = sum(row.passed is True for row in aligned)
        sensitivity_passed = sum(_sensitivity_pass(row) for row in aligned)
        severe = sum((not row.success) or float(row.score or 0.0) <= severe_failure_threshold for row in aligned)
        known_cost = sum(float(row.estimated_cost_usd or 0.0) for row in aligned)
        quality_ci = bootstrap_confidence_interval(
            qualities, confidence_level=confidence_level, resamples=resamples, seed=seed + offset
        )
        pass_ci = wilson_interval(passed, len(aligned), confidence_level=confidence_level)
        model_rows.append({
            "model": label,
            "cases": len(aligned),
            "provider_successes": sum(row.success for row in aligned),
            "provider_failures": sum(not row.success for row in aligned),
            "passed": passed,
            "sensitivity_passed": sensitivity_passed,
            "sensitivity_quality_mean": sensitivity_passed / len(aligned),
            "sensitivity_adjustments": sensitivity_passed - passed,
            "incorrect": len(aligned) - passed,
            "quality_mean": fmean(qualities),
            "quality_bootstrap_lower": quality_ci.lower,
            "quality_bootstrap_upper": quality_ci.upper,
            "pass_wilson_lower": pass_ci.lower,
            "pass_wilson_upper": pass_ci.upper,
            "coverage": sum(row.success for row in aligned) / len(aligned),
            "quality_given_provider_success": (
                fmean(successful_qualities) if successful_qualities else None
            ),
            "malformed_outputs": sum(row.malformed_output for row in aligned),
            "abstentions": sum(row.abstained for row in aligned),
            "severe_failures": severe,
            "latency_mean_ms": fmean(latencies),
            "latency_median_ms": median(latencies),
            "latency_p90_ms": _percentile(latencies, 0.90),
            "latency_p95_ms": _percentile(latencies, 0.95),
            "input_tokens": sum(row.input_tokens for row in aligned),
            "output_tokens": sum(row.output_tokens for row in aligned),
            "known_estimated_cost_usd": known_cost,
            "unknown_cost_calls": sum(row.estimated_cost_usd is None for row in aligned),
        })
        error_vectors[label] = {
            row.benchmark_case_id: 1.0 - float(row.score or 0.0) for row in aligned
        }
        sensitivity_error_vectors[label] = {
            row.benchmark_case_id: 0.0 if _sensitivity_pass(row) else 1.0 for row in aligned
        }
        task_groups: dict[str, list[BenchmarkRun]] = defaultdict(list)
        for row in aligned:
            task_groups[row.task_type].append(row)
        for task, task_group in sorted(task_groups.items()):
            task_rows.append({
                "model": label,
                "task_type": task,
                "cases": len(task_group),
                "provider_successes": sum(row.success for row in task_group),
                "passed": sum(row.passed is True for row in task_group),
                "sensitivity_passed": sum(_sensitivity_pass(row) for row in task_group),
                "quality_mean": fmean(float(row.score or 0.0) for row in task_group),
                "latency_mean_ms": fmean(row.latency_ms for row in task_group),
                "known_estimated_cost_usd": sum(
                    float(row.estimated_cost_usd or 0.0) for row in task_group
                ),
            })

    correlation = analyze_error_vectors(error_vectors, failure_threshold=0.5)
    pair_rows: list[dict[str, Any]] = []
    paired_comparisons: list[dict[str, Any]] = []
    for pair_offset, (left, right) in enumerate(combinations(correlation.labels, 2)):
        metrics_lr = correlation.pair_metrics(left, right)
        metrics_rl = correlation.pair_metrics(right, left)
        left_rows = [by_label_case[left][case_id] for case_id in ordered_cases]
        right_rows = [by_label_case[right][case_id] for case_id in ordered_cases]
        left_quality = [float(row.score or 0.0) for row in left_rows]
        right_quality = [float(row.score or 0.0) for row in right_rows]
        paired_ci = paired_bootstrap_difference(
            left_quality,
            right_quality,
            confidence_level=confidence_level,
            resamples=resamples,
            seed=seed + 100 + pair_offset,
        )
        mcnemar = mcnemar_exact(
            [row.passed is True for row in left_rows],
            [row.passed is True for row in right_rows],
        )
        left_failures = [row.passed is not True for row in left_rows]
        right_failures = [row.passed is not True for row in right_rows]
        pair_rows.append({
            "left": left,
            "right": right,
            "covariance": metrics_lr["covariance"],
            "correlation": metrics_lr["correlation"],
            "failure_overlap": metrics_lr["failure_overlap"],
            "disagreement_rate": metrics_lr["disagreement_rate"],
            "jaccard_failure_similarity": metrics_lr["jaccard_similarity"],
            "p_right_fails_given_left_fails": metrics_lr["conditional_failure"],
            "p_left_fails_given_right_fails": metrics_rl["conditional_failure"],
            "left_failures_rescued_by_right": sum(
                left_failed and not right_failed
                for left_failed, right_failed in zip(left_failures, right_failures, strict=True)
            ),
            "right_failures_rescued_by_left": sum(
                right_failed and not left_failed
                for left_failed, right_failed in zip(left_failures, right_failures, strict=True)
            ),
        })
        paired_comparisons.append({
            "left": left,
            "right": right,
            "quality_difference_left_minus_right": paired_ci.estimate,
            "bootstrap_lower": paired_ci.lower,
            "bootstrap_upper": paired_ci.upper,
            "mcnemar_left_only_correct": mcnemar.left_only_correct,
            "mcnemar_right_only_correct": mcnemar.right_only_correct,
            "mcnemar_p_value": mcnemar.p_value,
            "resolved_at_95_percent": (
                (paired_ci.lower > 0 or paired_ci.upper < 0) and mcnemar.p_value < 0.05
            ),
        })

    outcome_rows: list[dict[str, Any]] = []
    for case_id in ordered_cases:
        exemplar = next(iter(by_label_case.values()))[case_id]
        row: dict[str, Any] = {"case_id": case_id, "task_type": exemplar.task_type}
        for label in groups:
            item = by_label_case[label][case_id]
            row[label] = (
                "PROVIDER_FAILURE" if not item.success else
                "MALFORMED" if item.malformed_output else
                "PASS" if item.passed is True else "WRONG"
            )
            row[f"{label} sensitivity"] = (
                "PASS" if item.passed is True else
                "PASS_ALIAS" if _sensitivity_pass(item) else
                row[label]
            )
        outcome_rows.append(row)

    eligible = [row for row in model_rows if row["coverage"] == 1.0]
    best_quality = max(eligible, key=lambda row: (row["quality_mean"], -row["known_estimated_cost_usd"]))
    cheapest = min(eligible, key=lambda row: (row["known_estimated_cost_usd"], -row["quality_mean"]))
    fastest = min(eligible, key=lambda row: (row["latency_median_ms"], -row["quality_mean"]))
    eligible_labels = {row["model"] for row in eligible}
    eligible_pairs = [
        row for row in pair_rows if row["left"] in eligible_labels and row["right"] in eligible_labels
    ]
    complementary = min(
        eligible_pairs,
        key=lambda row: (
            row["failure_overlap"],
            row["correlation"] if row["correlation"] is not None else 1.0,
        ),
    )
    redundant = max(
        eligible_pairs,
        key=lambda row: (
            row["correlation"] if row["correlation"] is not None else -1.0,
            row["jaccard_failure_similarity"],
        ),
    )
    solver_label = best_quality["model"]
    verifier_options = [
        row for row in eligible_pairs if solver_label in {row["left"], row["right"]}
    ]
    verifier = max(
        verifier_options,
        key=lambda row: (
            row["left_failures_rescued_by_right"] if row["left"] == solver_label
            else row["right_failures_rescued_by_left"],
            -row["failure_overlap"],
        ),
    )
    verifier_label = verifier["right"] if verifier["left"] == solver_label else verifier["left"]
    structured_rows = [
        row for row in task_rows
        if row["task_type"] == "structured_extraction" and row["model"] in eligible_labels
    ]
    structured_best = max(
        (row["quality_mean"], row["provider_successes"]) for row in structured_rows
    )
    structured_candidates = [
        row["model"] for row in structured_rows
        if (row["quality_mean"], row["provider_successes"]) == structured_best
    ]

    sensitivity_correlation = analyze_error_vectors(
        sensitivity_error_vectors, failure_threshold=0.5
    )
    sensitivity_pair_rows: list[dict[str, Any]] = []
    for left, right in combinations(sensitivity_correlation.labels, 2):
        metrics_lr = sensitivity_correlation.pair_metrics(left, right)
        metrics_rl = sensitivity_correlation.pair_metrics(right, left)
        sensitivity_pair_rows.append({
            "left": left,
            "right": right,
            "covariance": metrics_lr["covariance"],
            "correlation": metrics_lr["correlation"],
            "failure_overlap": metrics_lr["failure_overlap"],
            "disagreement_rate": metrics_lr["disagreement_rate"],
            "jaccard_failure_similarity": metrics_lr["jaccard_similarity"],
            "p_right_fails_given_left_fails": metrics_lr["conditional_failure"],
            "p_left_fails_given_right_fails": metrics_rl["conditional_failure"],
        })
    sensitivity_best = max(
        eligible,
        key=lambda row: (
            row["sensitivity_quality_mean"],
            -row["known_estimated_cost_usd"],
        ),
    )
    sensitivity_eligible_pairs = [
        row for row in sensitivity_pair_rows
        if row["left"] in eligible_labels and row["right"] in eligible_labels
    ]
    sensitivity_complementary = min(
        sensitivity_eligible_pairs,
        key=lambda row: (
            row["failure_overlap"],
            row["correlation"] if row["correlation"] is not None else 1.0,
        ),
    )
    sensitivity_redundant = max(
        sensitivity_eligible_pairs,
        key=lambda row: (
            row["correlation"] if row["correlation"] is not None else -1.0,
            row["jaccard_failure_similarity"],
        ),
    )

    known_cost = sum(row["known_estimated_cost_usd"] for row in model_rows)
    unknown_cost_calls = sum(row["unknown_cost_calls"] for row in model_rows)
    max_call_cost = 0.004608  # Sonnet cap: 1024 input and 256 output tokens.
    next_stage = {
        "full_72_case_single_model": {"calls": 360, "dollar_ceiling": 0.56291328},
        "a0_to_a6_upper_bound": {"calls": 1368, "dollar_ceiling": 1368 * max_call_cost},
        "ablations_three_frontier_candidates_upper_bound": {
            "calls": 2592,
            "dollar_ceiling": 2592 * max_call_cost,
            "assumption": "three frontier candidates, four additional variants, at most three calls per case",
        },
        "conditional_verification_upper_bound": {
            "calls": 648,
            "dollar_ceiling": 648 * max_call_cost,
            "assumption": "five policies; conditional policies costed as if verification always fires",
        },
        "sequential_racing_two_extra_repeats_upper_bound": {
            "calls": 1296,
            "dollar_ceiling": 1296 * max_call_cost,
            "assumption": "three unresolved candidates, three calls per case, two extra repeats",
        },
    }

    return {
        "metadata": {
            "evidence_state": "PILOT",
            "cases": len(ordered_cases),
            "models": len(groups),
            "calls": len(runs),
            "confidence_level": confidence_level,
            "bootstrap_resamples": resamples,
            "seed": seed,
            "severe_failure_threshold": severe_failure_threshold,
            "known_estimated_cost_usd": known_cost,
            "unknown_cost_calls": unknown_cost_calls,
            "authorized_cost_ceiling_usd": pilot_cost_ceiling_usd,
            "preflight_projected_cost_usd": preflight_projected_cost_usd,
        },
        "model_statistics": model_rows,
        "task_statistics": task_rows,
        "outcome_matrix": outcome_rows,
        "pairwise_diagnostics": pair_rows,
        "paired_comparisons": paired_comparisons,
        "loss_matrix": {
            "labels": list(correlation.labels),
            "expected_loss": {
                label: fmean(error_vectors[label].values()) for label in correlation.labels
            },
            "loss_variance": {
                label: correlation.covariance[index][index]
                for index, label in enumerate(correlation.labels)
            },
            "covariance": correlation.covariance,
            "correlation": correlation.correlation,
        },
        "scoring_sensitivity": {
            "status": "post_hoc_audit_not_primary",
            "scope": (
                "Case-specific critique taxonomy synonyms and whitespace around "
                "planning-list commas only; provider failures and other wrong answers remain failures."
            ),
            "model_statistics": [
                {
                    "model": row["model"],
                    "primary_passed": row["passed"],
                    "sensitivity_passed": row["sensitivity_passed"],
                    "cases": row["cases"],
                    "adjustments": row["sensitivity_adjustments"],
                }
                for row in model_rows
            ],
            "pairwise_diagnostics": sensitivity_pair_rows,
            "loss_matrix": {
                "labels": list(sensitivity_correlation.labels),
                "expected_loss": {
                    label: fmean(sensitivity_error_vectors[label].values())
                    for label in sensitivity_correlation.labels
                },
                "loss_variance": {
                    label: sensitivity_correlation.covariance[index][index]
                    for index, label in enumerate(sensitivity_correlation.labels)
                },
                "covariance": sensitivity_correlation.covariance,
                "correlation": sensitivity_correlation.correlation,
            },
            "role_sensitivity": {
                "best_solver_candidate": sensitivity_best["model"],
                "most_complementary_pair": [
                    sensitivity_complementary["left"], sensitivity_complementary["right"]
                ],
                "most_redundant_pair": [
                    sensitivity_redundant["left"], sensitivity_redundant["right"]
                ],
            },
        },
        "role_candidates": {
            "best_solver_candidate": solver_label,
            "best_cheap_solver_candidate": cheapest["model"],
            "best_low_latency_candidate": fastest["model"],
            "best_verifier_candidate_for_best_solver": verifier_label,
            "critic_candidate": verifier_label,
            "most_complementary_pair": [complementary["left"], complementary["right"]],
            "most_redundant_pair": [redundant["left"], redundant["right"]],
            "strongest_structured_output_candidates": structured_candidates,
            "caveat": "Roles exclude partial-coverage models and remain pilot hypotheses.",
        },
        "next_stage_projection": next_stage,
    }


def write_pilot_report(root: str | Path, report: Mapping[str, Any]) -> dict[str, Path]:
    root_path = Path(root)
    artifact_dir = root_path / "artifacts" / "pilot_v0"
    report_dir = root_path / "reports"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    scrubber = SecretScrubber.from_environment()
    paths = {
        "pilot_summary.json": artifact_dir / "pilot_summary.json",
        "model_statistics.csv": artifact_dir / "model_statistics.csv",
        "task_statistics.csv": artifact_dir / "task_statistics.csv",
        "outcome_matrix.csv": artifact_dir / "outcome_matrix.csv",
        "pairwise_diagnostics.csv": artifact_dir / "pairwise_diagnostics.csv",
        "paired_comparisons.csv": artifact_dir / "paired_comparisons.csv",
        "loss_matrix.json": artifact_dir / "loss_matrix.json",
        "scoring_sensitivity.json": artifact_dir / "scoring_sensitivity.json",
        "next_stage_projection.json": artifact_dir / "next_stage_projection.json",
        "PILOT_REPORT.md": report_dir / "PILOT_REPORT.md",
    }
    _write_json(paths["pilot_summary.json"], report, scrubber)
    _write_csv(paths["model_statistics.csv"], report["model_statistics"])
    _write_csv(paths["task_statistics.csv"], report["task_statistics"])
    _write_csv(paths["outcome_matrix.csv"], report["outcome_matrix"])
    _write_csv(paths["pairwise_diagnostics.csv"], report["pairwise_diagnostics"])
    _write_csv(paths["paired_comparisons.csv"], report["paired_comparisons"])
    _write_json(paths["loss_matrix.json"], report["loss_matrix"], scrubber)
    _write_json(
        paths["scoring_sensitivity.json"], report["scoring_sensitivity"], scrubber
    )
    _write_json(paths["next_stage_projection.json"], report["next_stage_projection"], scrubber)

    stats = report["model_statistics"]
    roles = report["role_candidates"]
    metadata = report["metadata"]
    lines = [
        "# EigenBrains empirical pilot report",
        "",
        f"Evidence: 24 paired cases x 5 models = {metadata['calls']} calls.",
        f"Known token-estimated cost: ${metadata['known_estimated_cost_usd']:.8f}; "
        f"{metadata['unknown_cost_calls']} failed calls have unknown billing status. "
        f"The preflight worst-case projection was ${metadata['preflight_projected_cost_usd']:.8f} "
        f"under the authorized ${metadata['authorized_cost_ceiling_usd']:.2f} ceiling.",
        "",
        "## Protocol adherence",
        "",
        "- The same 24 development cases were run once per model in the same deterministic order.",
        "- Prompt, evaluator, temperature (0), output cap (256), and case ordering were unchanged across models.",
        "- Concurrency remained 1. No provider-compatibility exception changed the benchmark contract.",
        "- Direct OpenAI inference remained excluded after its discovery probe returned HTTP 429.",
        "",
        "## Per-model observations",
        "",
        "| Model | Pass | Coverage | Conditional quality | Median latency | Known cost |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(stats, key=lambda item: item["quality_mean"], reverse=True):
        conditional = row["quality_given_provider_success"]
        lines.append(
            f"| {row['model']} | {row['passed']}/{row['cases']} ({row['quality_mean']:.1%}) | "
            f"{row['coverage']:.1%} | "
            f"{'n/a' if conditional is None else f'{conditional:.1%}'} | "
            f"{row['latency_median_ms']:.1f} ms | ${row['known_estimated_cost_usd']:.8f} |"
        )
    lines.extend([
        "",
        "| Model | Success/failure | Malformed | Abstain | Severe | Mean / p90 / p95 latency | Tokens in/out | Unknown-cost calls |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in stats:
        lines.append(
            f"| {row['model']} | {row['provider_successes']}/{row['provider_failures']} | "
            f"{row['malformed_outputs']} | {row['abstentions']} | {row['severe_failures']} | "
            f"{row['latency_mean_ms']:.1f} / {row['latency_p90_ms']:.1f} / {row['latency_p95_ms']:.1f} ms | "
            f"{row['input_tokens']}/{row['output_tokens']} | {row['unknown_cost_calls']} |"
        )
    lines.extend([
        "",
        "| Model | Wilson 95% pass interval | Bootstrap 95% quality interval |",
        "|---|---:|---:|",
    ])
    for row in stats:
        lines.append(
            f"| {row['model']} | [{row['pass_wilson_lower']:.1%}, {row['pass_wilson_upper']:.1%}] | "
            f"[{row['quality_bootstrap_lower']:.1%}, {row['quality_bootstrap_upper']:.1%}] |"
        )
    lines.extend([
        "",
        "### Task-family exceptions",
        "",
        "Only families below perfect coverage/pass are listed; each family has two cases.",
        "",
        "| Model | Primary non-perfect families | Narrow-sensitivity non-perfect families |",
        "|---|---|---|",
    ])
    for model in (row["model"] for row in stats):
        model_tasks = [
            row for row in report["task_statistics"] if row["model"] == model
        ]
        primary = ", ".join(
            f"{row['task_type']} {row['passed']}/{row['cases']}"
            for row in model_tasks
            if row["passed"] < row["cases"]
        ) or "none"
        sensitivity = ", ".join(
            f"{row['task_type']} {row['sensitivity_passed']}/{row['cases']}"
            for row in model_tasks
            if row["sensitivity_passed"] < row["cases"]
        ) or "none"
        lines.append(f"| {model} | {primary} | {sensitivity} |")
    lines.extend([
        "",
        "Provider failures count as failed benchmark outcomes. Severe failure equals objective score <= 0.2 in this binary pilot. "
        "No abstention was inferred from free text; only explicit runner flags count.",
        "",
        "## Role hypotheses",
        "",
        f"- Solver: `{roles['best_solver_candidate']}`.",
        f"- Cheap solver: `{roles['best_cheap_solver_candidate']}`.",
        f"- Low-latency solver: `{roles['best_low_latency_candidate']}`.",
        f"- Verifier/critic candidate for the leading solver: `{roles['best_verifier_candidate_for_best_solver']}`.",
        f"- Most complementary full-coverage pair: `{' + '.join(roles['most_complementary_pair'])}`.",
        f"- Most redundant full-coverage pair: `{' + '.join(roles['most_redundant_pair'])}`.",
        f"- Structured-output: unresolved 2/2 tie among `{', '.join(roles['strongest_structured_output_candidates'])}`.",
        "",
        "These are pilot hypotheses, not architecture assignments. Pairwise confidence results and the loss covariance matrix are in the accompanying artifacts.",
        "",
        "## Scoring sensitivity audit",
        "",
        "The frozen primary evaluator used exact matching and remains the preregistered result. A post-hoc audit counts only case-specific critique taxonomy synonyms and whitespace around planning-list commas. It does not rescue provider failures, blank outputs, malformed outputs, or unapproved tool-name aliases.",
        "",
        "| Model | Primary | Narrow sensitivity | Adjustments |",
        "|---|---:|---:|---:|",
    ])
    for row in sorted(stats, key=lambda item: item["sensitivity_quality_mean"], reverse=True):
        lines.append(
            f"| {row['model']} | {row['passed']}/{row['cases']} | "
            f"{row['sensitivity_passed']}/{row['cases']} | "
            f"+{row['sensitivity_adjustments']} |"
        )
    sensitivity_roles = report["scoring_sensitivity"]["role_sensitivity"]
    lines.extend([
        "",
        f"Under this narrow audit, the solver candidate changes to `{sensitivity_roles['best_solver_candidate']}`. "
        "That ranking sensitivity is itself a pilot result: solver selection is unresolved until the evaluator contract is repaired and rerun on held-out cases.",
        "",
        f"The sensitivity-audit complementary pair is `{' + '.join(sensitivity_roles['most_complementary_pair'])}`; "
        f"the redundant pair is `{' + '.join(sensitivity_roles['most_redundant_pair'])}`.",
        "",
        "## Paired failure structure",
        "",
        "The table below is restricted to models with complete 24-case coverage. Conditional columns read P(right fails | left fails) and P(left fails | right fails).",
        "",
        "| Pair | Corr(loss) | Disagree | Jaccard failures | Conditional R/L | Rescues R/L |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    eligible_labels = {
        row["model"] for row in stats if row["coverage"] == 1.0
    }
    for row in report["pairwise_diagnostics"]:
        if row["left"] not in eligible_labels or row["right"] not in eligible_labels:
            continue
        correlation = row["correlation"]
        lines.append(
            f"| {row['left']} + {row['right']} | "
            f"{'n/a' if correlation is None else f'{correlation:.3f}'} | "
            f"{row['disagreement_rate']:.1%} | {row['jaccard_failure_similarity']:.3f} | "
            f"{row['p_right_fails_given_left_fails']:.1%}/{row['p_left_fails_given_right_fails']:.1%} | "
            f"{row['left_failures_rescued_by_right']}/{row['right_failures_rescued_by_left']} |"
        )
    lines.extend([
        "",
        "All three full-coverage pairwise quality comparisons remain unresolved at 95% confidence. The complete case matrix, task-family breakdown, paired confidence intervals, covariance matrix, and conditional-failure table are preserved as CSV/JSON artifacts.",
        "",
        "## Next-stage projections (not executed)",
        "",
        "| Stage | Calls | Conservative dollar ceiling |",
        "|---|---:|---:|",
    ])
    for stage, projection in report["next_stage_projection"].items():
        lines.append(
            f"| {stage} | {projection['calls']} | ${projection['dollar_ceiling']:.6f} |"
        )
    lines.extend([
        "",
        "## Reliability limitations",
        "",
        "- Anthropic Sonnet produced no successful calls in this pilot, despite the earlier Haiku probe succeeding.",
        "- Gemini completed 17/24 calls; its last seven calls failed at the provider boundary. Its all-case score and conditional-on-success score must not be conflated.",
        "- With only 24 cases and two observations per task type, task-specific rankings and tail claims remain weak.",
        "- Exact provider billing was not queried. The report preserves unknown cost for failed calls.",
        "",
        "## Stop condition",
        "",
        "No full baseline, multi-agent architecture, ablation, conditional-verification, or sequential-racing calls were launched.",
    ])
    paths["PILOT_REPORT.md"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths
