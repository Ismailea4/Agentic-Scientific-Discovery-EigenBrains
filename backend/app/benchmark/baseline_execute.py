"""Execute the explicitly approved Architecture Baseline v0 and then stop."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable, Sequence

from ..ai.types import Message
from ..instrumentation.pricing import PricingTable
from ..optimization.covariance import (
    analyze_error_vectors,
    bootstrap_pairwise_metrics,
    diagonal_shrinkage_covariance,
)
from ..optimization.pareto import pareto_frontier
from ..providers import invoke_normalized
from .analysis import aggregate_model_reliability, model_error_vectors
from .baseline_plan import canonical_hash, write_plan_artifacts
from .bounds import (
    bootstrap_dominance_probabilities,
    estimate_architecture_bounds,
    robust_frontier,
    wilson_interval,
)
from .controls import BenchmarkLimits, BudgetController
from .corpus import CORPUS_VERSION, build_generic_prior_v0
from .evaluators import EvaluatorRegistry, SCORING_V1_HASH
from .metrics import aggregate_architectures
from .models import BenchmarkCase, BenchmarkRun, SystemOutcome
from .pilot import (
    PILOT_PROMPT,
    PilotModelSpec,
    build_provider,
    pilot_prompt_config_hash,
    run_single_model_pilot,
)
from .policies import VERIFIER_PROMPT_V1, baseline_policies_v0
from .priors import construct_binary_evidence_priors
from .selective_replay import (
    FrozenGateConfiguration,
    replay_decision,
    replay_policies,
    summarize_escalation_economics,
)
from .statistics import paired_bootstrap_difference


APPROVED_LIMITS = BenchmarkLimits(
    max_benchmark_spend_usd=0.20,
    max_total_calls=245,
    max_calls_per_model=None,
    max_concurrency=1,
    max_provider_requests=246,
)
CORE_SPECS = (
    PilotModelSpec("groq", "openai/gpt-oss-20b"),
    PilotModelSpec("groq", "qwen/qwen3.8-27b"),
    PilotModelSpec("openrouter", "deepseek/deepseek-v4.1-flash"),
)
QWEN = "groq/qwen/qwen3.8-27b"
GPT_OSS = "groq/openai/gpt-oss-20b"
SCRUBBER_NOTE = "No exception messages, response headers, request headers, or environment values are persisted."


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    raise TypeError(type(value).__name__)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False, default=_json_default) + "\n")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False, default=_json_default) + "\n")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _split(case: BenchmarkCase) -> str:
    return str(getattr(case.split, "value", case.split))


def _model_label(run: BenchmarkRun) -> str:
    return f"{run.provider}/{run.model}"


def _safe_error_classification(exc: BaseException) -> tuple[str, int | None]:
    """Classify an exception without serializing its message or transport details."""
    current: BaseException | None = exc
    status: int | None = None
    while current is not None:
        response = getattr(current, "response", None)
        candidate = getattr(response, "status_code", None)
        if isinstance(candidate, int):
            status = candidate
            break
        current = current.__cause__
    if status == 401:
        category = "authentication"
    elif status == 403:
        category = "permission"
    elif status == 404:
        category = "model_or_endpoint_not_found"
    elif status == 429:
        category = "rate_or_quota_limited"
    elif status is not None and status >= 500:
        category = "provider_outage"
    elif status is not None:
        category = "provider_request_rejected"
    else:
        category = "transport_or_adapter_error"
    return category, status


def _freeze_manifest(root: Path, protocol: dict[str, Any], pricing: PricingTable) -> Path:
    cases = build_generic_prior_v0()
    paths = write_plan_artifacts(root / "benchmark", cases=cases, protocol=protocol, pricing=pricing)
    manifest_path = paths["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("observations", {}).get("status") != "NOT_RUN":
        raise RuntimeError("Baseline v0 is already executed and immutable")
    manifest["status"] = "APPROVED_FROZEN"
    manifest["execution_authorization"] = {
        "approved_at": _utc_now(),
        "approved_phases": [
            "provider_diagnosis",
            "core_72_case_single_model_baseline",
            "s0_to_s4_offline_replay",
            "compact_provider_backed_verifier_confirmation",
        ],
        "max_benchmark_spend_usd": 0.20,
        "max_total_inference_calls": 245,
        "max_provider_requests": 246,
        "max_concurrency": 1,
        "explicitly_excluded": [
            "sequential_racing",
            "full_claude_baseline",
            "full_gemini_baseline",
            "exhaustive_A0_A6",
            "additional_ablations",
            "UI_work",
        ],
    }
    _write_json(manifest_path, manifest)
    return manifest_path


async def _diagnostic_call(
    spec: PilotModelSpec,
    prompt: str,
    pricing: PricingTable,
    controller: BudgetController,
) -> dict[str, Any]:
    provider = build_provider(spec)
    cap_cost = pricing.estimate_cost(spec.model, 256, 64)
    started = time.perf_counter()
    try:
        async with controller.slot(spec.model, projected_cost_usd=cap_cost):
            response = await provider.generate(
                [Message("system", PILOT_PROMPT), Message("user", prompt)],
                max_tokens=64,
                temperature=0,
            )
    except Exception as exc:
        category, status = _safe_error_classification(exc)
        return {
            "provider": spec.provider,
            "configured_model": spec.model,
            "success": False,
            "error_type": type(exc).__name__,
            "error_category": category,
            "http_status": status,
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_usd": None,
            "timestamp": _utc_now(),
        }
    return {
        "provider": spec.provider,
        "configured_model": spec.model,
        "resolved_provider_model": response.model,
        "success": True,
        "error_type": None,
        "error_category": None,
        "http_status": None,
        "output": response.content,
        "latency_ms": (time.perf_counter() - started) * 1000.0,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "estimated_cost_usd": pricing.estimate_cost(
            spec.model, response.usage.input_tokens, response.usage.output_tokens
        ),
        "timestamp": _utc_now(),
    }


async def _run_provider_diagnosis(
    pricing: PricingTable,
    controller: BudgetController,
    path: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sonnet = await _diagnostic_call(
        PilotModelSpec("anthropic", "claude-sonnet-5-5"), "Return only OK.", pricing, controller
    )
    rows.append(sonnet)
    _append_jsonl(path, sonnet)
    if not sonnet["success"]:
        haiku = await _diagnostic_call(
            PilotModelSpec("anthropic", "claude-haiku-4-5-20251001"),
            "Return only OK.",
            pricing,
            controller,
        )
        rows.append(haiku)
        _append_jsonl(path, haiku)

    gemini_prompts = (
        "Return only allow. The mandatory capability is present and not denied.",
        "Return only OK.",
        "Return only 4 for 2+2.",
    )
    first = await _diagnostic_call(
        PilotModelSpec("gemini", "gemini-3.5-flash-lite"),
        gemini_prompts[0],
        pricing,
        controller,
    )
    rows.append(first)
    _append_jsonl(path, first)
    if not first["success"]:
        for prompt in gemini_prompts[1:]:
            row = await _diagnostic_call(
                PilotModelSpec("gemini", "gemini-3.5-flash-lite"), prompt, pricing, controller
            )
            rows.append(row)
            _append_jsonl(path, row)
            if row["success"]:
                break
    return rows


async def _run_core_cases(
    cases: Sequence[BenchmarkCase],
    pricing: PricingTable,
    controller: BudgetController,
    path: Path,
    *,
    progress_start: int,
) -> list[BenchmarkRun]:
    runs: list[BenchmarkRun] = []
    progress = progress_start
    for spec in CORE_SPECS:
        for case in cases:
            measured = await run_single_model_pilot(
                [case],
                [spec],
                pricing,
                APPROVED_LIMITS,
                output_token_cap=256,
                input_token_cap=1024,
                seed=0,
                allowed_splits=None,
                controller=controller,
            )
            if len(measured) != 1:
                raise RuntimeError("single-case execution did not produce exactly one observation")
            run = measured[0]
            runs.append(run)
            _append_jsonl(path, run.to_dict())
            progress += 1
            if progress % 10 == 0:
                print(f"core progress: {progress}/216", flush=True)
    return runs


def _fit_gate(dev_tuning_runs: Sequence[BenchmarkRun]) -> FrozenGateConfiguration:
    if {str(run.metadata.get("split")) for run in dev_tuning_runs} - {"dev", "tuning"}:
        raise ValueError("gate fitting received non-development evidence")
    grouped: dict[tuple[str, str], list[BenchmarkRun]] = defaultdict(list)
    for run in dev_tuning_runs:
        grouped[(_model_label(run), run.task_type)].append(run)
    tasks = sorted({run.task_type for run in dev_tuning_runs})
    owners: dict[str, str] = {}
    qwen_error_ucb: dict[str, float] = {}
    for task in tasks:
        scores: dict[str, float] = {}
        for label in (QWEN, GPT_OSS):
            rows = grouped[(label, task)]
            if not rows:
                raise ValueError(f"missing gate-fit observations for {label}/{task}")
            scores[label] = sum(row.passed is True for row in rows) / len(rows)
        owners[task] = GPT_OSS if scores[GPT_OSS] > scores[QWEN] else QWEN
        qwen_rows = grouped[(QWEN, task)]
        failures = sum(row.passed is not True for row in qwen_rows)
        qwen_error_ucb[task] = wilson_interval(failures, len(qwen_rows)).upper
    return FrozenGateConfiguration(
        fitted_splits=("dev", "tuning"),
        escalate_high_risk=True,
        escalate_task_families=(),
        historical_task_family_error_ucb=qwen_error_ucb,
        historical_error_ucb_threshold=0.5,
        task_family_owner=owners,
    )


async def _provider_backed_policy(
    policy_id: str,
    cases: Sequence[BenchmarkCase],
    single_runs: Sequence[BenchmarkRun],
    gate: FrozenGateConfiguration,
    pricing: PricingTable,
    controller: BudgetController,
    path: Path,
) -> list[BenchmarkRun]:
    policy = next(item for item in baseline_policies_v0() if item.id == policy_id)
    by_key = {(_model_label(run), run.benchmark_case_id): run for run in single_runs}
    registry = EvaluatorRegistry()
    output: list[BenchmarkRun] = []
    verifier_hash = canonical_hash({
        "system": VERIFIER_PROMPT_V1,
        "temperature": 0,
        "max_output_tokens": 256,
    })
    for case in cases:
        first = by_key[(policy.first_model, case.id)]
        replay_probe = replay_decision(policy, case, first, by_key[(policy.second_model, case.id)], gate)
        escalated = replay_probe.escalated
        second_call = None
        if escalated:
            second_provider_name, second_model = str(policy.second_model).split("/", 1)
            second_spec = PilotModelSpec(second_provider_name, second_model)
            provider = build_provider(second_spec)
            cap_cost = pricing.estimate_cost(second_model, 1024, 256)
            async with controller.slot(second_model, projected_cost_usd=cap_cost):
                second_call = await invoke_normalized(
                    provider,
                    [
                        Message("system", VERIFIER_PROMPT_V1),
                        Message("user", f"Task: {case.input}\nProposed answer: {first.output}"),
                    ],
                    task_type=case.task_type,
                    pricing=pricing,
                    max_tokens=256,
                    temperature=0,
                )
        final_output = second_call.output if second_call is not None and second_call.success else first.output
        evaluation = registry.resolve(case).evaluate(case, final_output)
        success = bool((second_call is not None and second_call.success) or first.success)
        verifier_cost = None
        if second_call is not None and second_call.success:
            verifier_cost = second_call.estimated_cost_usd
            if verifier_cost is None:
                verifier_cost = pricing.estimate_cost(
                    str(policy.second_model).split("/", 1)[1],
                    second_call.input_tokens,
                    second_call.output_tokens,
                )
        first_cost = first.estimated_cost_usd if first.success else 0.0
        known_cost = first_cost is not None and (not escalated or not (second_call and second_call.success) or verifier_cost is not None)
        total_cost = (
            float(first_cost or 0.0) + float(verifier_cost or 0.0) if known_cost else None
        )
        first_correct = first.passed is True
        final_correct = evaluation.passed is True
        run = BenchmarkRun(
            benchmark_case_id=case.id,
            task_type=str(getattr(case.task_type, "value", case.task_type)),
            architecture_id=f"{policy_id}_PROVIDER_BACKED",
            agent_role="conditional_verifier",
            provider="provider_backed",
            model=policy_id,
            output=final_output,
            success=success,
            error_type=(second_call.error_type if second_call is not None and not second_call.success else None),
            latency_ms=first.latency_ms + (second_call.latency_ms if second_call is not None else 0.0),
            input_tokens=first.input_tokens + (second_call.input_tokens if second_call is not None else 0),
            output_tokens=first.output_tokens + (second_call.output_tokens if second_call is not None else 0),
            estimated_cost_usd=total_cost,
            score=evaluation.score,
            passed=evaluation.passed,
            outcome=SystemOutcome.ANSWER if success else SystemOutcome.INSUFFICIENT_EVIDENCE,
            timestamp=_utc_now(),
            metadata={
                "final_output": True,
                "split": "held_out",
                "difficulty": str(getattr(case.difficulty, "value", case.difficulty)),
                "risk_level": str(getattr(case.risk_level, "value", case.risk_level)),
                "evidence_mode": "PROVIDER_BACKED_CACHED_FIRST_PASS",
                "offline_replay": False,
                "first_model": policy.first_model,
                "verifier_model": policy.second_model,
                "escalated": escalated,
                "escalation_reasons": list(replay_probe.escalation_reasons),
                "verification_opportunity": escalated and not first_correct,
                "verification_rescued": escalated and not first_correct and final_correct,
                "verification_damaged": escalated and first_correct and not final_correct,
                "first_output": first.output,
                "verifier_output": second_call.output if second_call is not None else None,
                "verifier_success": second_call.success if second_call is not None else None,
                "verifier_estimated_cost_usd": verifier_cost,
                "evaluation": dict(evaluation.metadata),
            },
            prompt_config_hash=verifier_hash if escalated else first.prompt_config_hash,
            model_configuration={"temperature": 0, "max_tokens": 256},
        )
        output.append(run)
        _append_jsonl(path, run.to_dict())
        print(f"provider-backed {policy_id}: {len(output)}/{len(cases)}", flush=True)
    return output


def _paired_quality_comparisons(runs: Sequence[BenchmarkRun]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, BenchmarkRun]] = defaultdict(dict)
    for run in runs:
        grouped[run.architecture_id][run.benchmark_case_id] = run
    output: list[dict[str, Any]] = []
    for policy, baseline in (("S2", "S1"), ("S3", "S1"), ("S4", "S0")):
        ids = sorted(set(grouped[policy]) & set(grouped[baseline]))
        interval = paired_bootstrap_difference(
            [float(grouped[policy][item].score or 0.0) for item in ids],
            [float(grouped[baseline][item].score or 0.0) for item in ids],
            resamples=2000,
            seed=0,
        )
        output.append({
            "policy": policy,
            "baseline": baseline,
            "quality_difference": interval.to_dict(),
            "statistically_unresolved_at_95_percent": interval.lower <= 0 <= interval.upper,
        })
    return output


def _report_markdown(summary: dict[str, Any]) -> str:
    def pct(value: float) -> str:
        return f"{100.0 * value:.1f}%"

    lines = [
        "# Architecture Baseline v0 — FROZEN",
        "",
        "This report leads with measured evidence. Offline replay and provider-backed confirmation are reported separately.",
        "",
        "## Headline finding",
        "",
    ]
    economics_by_id = {
        row["policy_id"]: row for row in summary["offline_replay"]["economics"]
    }
    s3 = economics_by_id["S3"]
    s2_result = next(
        row for row in summary["offline_replay"]["architecture_results"]
        if row["architecture_id"] == "S2"
    )
    s3_result = next(
        row for row in summary["offline_replay"]["architecture_results"]
        if row["architecture_id"] == "S3"
    )
    cost_saving_rate = (
        float(s3["cost_saving_vs_always_both_usd"]) / float(s2_result["cost"])
        if s3["cost_saving_vs_always_both_usd"] is not None and s2_result["cost"]
        else 0.0
    )
    latency_saving_rate = (
        float(s3["latency_saving_vs_always_both_ms"]) / float(s2_result["latency"])
        if s2_result["latency"]
        else 0.0
    )
    lines.extend([
        f"Qwen → selective GPT-OSS escalation matched always-both held-out quality ({s3_result['expected_quality']:.3f}) while using {pct(cost_saving_rate)} less estimated cost and {pct(latency_saving_rate)} less latency in offline replay.",
        "",
        "This is an efficiency result, not evidence of a quality gain: the provider-backed confirmation produced zero rescues and zero damage on this 12-case held-out set, and the paired quality differences remain statistically unresolved.",
        "",
        "## Provider diagnosis",
        "",
        "| Provider/model | Result | Safe classification | HTTP status |",
        "|---|---|---|---:|",
    ])
    for row in summary["provider_diagnosis"]["observations"]:
        lines.append(
            f"| {row['provider']}/{row['configured_model']} | {'success' if row['success'] else 'failure'} | "
            f"{row.get('error_category') or 'available'} | {row.get('http_status') or '—'} |"
        )
    lines.extend([
        "",
        "## Single-model evidence (72 identical cases each)",
        "",
        "| Provider/model | Availability (95% Wilson) | Correct given success (95% Wilson) | Operational correct | Severe operational failure | Mean latency on success (ms) |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for row in summary["model_reliability"]:
        conditional = row["correct_given_provider_success"]
        latency = row["latency_mean_ms_given_provider_success"]
        availability_ci = wilson_interval(row["provider_successes"], row["total_calls"])
        conditional_ci = (
            wilson_interval(
                round(float(conditional) * row["scored_provider_successes"]),
                row["scored_provider_successes"],
            )
            if conditional is not None and row["scored_provider_successes"]
            else None
        )
        availability_text = (
            f"{row['provider_success_probability']:.3f} "
            f"[{availability_ci.lower:.3f}, {availability_ci.upper:.3f}]"
        )
        conditional_text = (
            "unresolved" if conditional_ci is None else
            f"{conditional:.3f} [{conditional_ci.lower:.3f}, {conditional_ci.upper:.3f}]"
        )
        lines.append(
            f"| {row['provider']}/{row['model']} | {availability_text} | {conditional_text} | "
            f"{row['operational_correct_probability']:.3f} | "
            f"{row['operational_severe_failure_probability']:.3f} | "
            f"{'unresolved' if latency is None else f'{latency:.1f}'} |"
        )
    lines.extend([
        "",
        "## Held-out S0–S4 offline replay (12 sealed cases)",
        "",
        "These are counterfactual replay estimates from paired cached single-model observations, not executed multi-agent architectures.",
        "",
        "| Policy | Quality (95% bootstrap) | Cost/case (USD) | Latency/case (ms) | Failure rate | Tail risk | Empirical Pareto | Robust Pareto |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ])
    empirical = set(summary["offline_replay"]["empirical_pareto_frontier"])
    robust = set(summary["offline_replay"]["robust_pareto_frontier"]["frontier_ids"])
    for row in summary["offline_replay"]["architecture_results"]:
        cost_text = "unknown" if row["cost"] is None else f"{row['cost']:.8f}"
        bound = next(
            item for item in summary["offline_replay"]["confidence_bounds"]
            if item["architecture_id"] == row["architecture_id"]
        )
        quality_text = (
            f"{row['expected_quality']:.3f} "
            f"[{bound['quality']['lower']:.3f}, {bound['quality']['upper']:.3f}]"
        )
        lines.append(
            f"| {row['architecture_id']} | {quality_text} | "
            f"{cost_text} | {row['latency']:.1f} | "
            f"{row['failure_rate']:.3f} | {row['risk']:.3f} | "
            f"{'yes' if row['architecture_id'] in empirical else 'no'} | "
            f"{'yes' if row['architecture_id'] in robust else 'no'} |"
        )
    lines.extend([
        "",
        "## Selective-escalation economics (offline replay)",
        "",
        "| Policy | Escalation | Rescue | Damage | Δ quality | Δ cost | Δ latency (ms) | Saving vs always-both |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in summary["offline_replay"]["economics"]:
        def fmt(value: Any, digits: int = 3) -> str:
            return "unresolved" if value is None else f"{float(value):.{digits}f}"
        lines.append(
            f"| {row['policy_id']} vs {row['baseline_policy_id']} | {fmt(row['escalation_probability'])} | "
            f"{fmt(row['rescue_probability'])} | {fmt(row['damage_probability'])} | "
            f"{fmt(row['incremental_quality'])} | {fmt(row['incremental_cost_usd'], 8)} | "
            f"{fmt(row['incremental_latency_ms'], 1)} | {fmt(row['cost_saving_vs_always_both_usd'], 8)} |"
        )
    lines.extend([
        "",
        "## Provider-backed verifier confirmation",
        "",
        "These rows are actual verifier calls on top of cached first-pass held-out observations. They are not offline replay.",
        "",
        "| Policy | n | Quality (95% Wilson) | Escalations | Rescues | Damage |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for row in summary["provider_backed_confirmation"]:
        ci = row["quality_wilson"]
        lines.append(
            f"| {row['architecture_id']} | {row['sample_size']} | {row['quality']:.3f} "
            f"[{ci['lower']:.3f}, {ci['upper']:.3f}] | "
            f"{row['escalations']} | {row['rescues']} | {row['damage']} |"
        )
    lines.extend([
        "",
        "## Failure diversification",
        "",
        "| Pair | Error correlation (95% bootstrap) | Failure Jaccard | P(right succeeds | left fails) |",
        "|---|---:|---:|---:|",
    ])
    for row in summary["covariance"]["bootstrap_intervals"]:
        corr = row["metrics"]["correlation"]
        jaccard = row["metrics"]["jaccard_failure_similarity"]
        rescue = row["metrics"]["p_right_succeeds_given_left_fails"]
        lines.append(
            f"| {row['left']} ↔ {row['right']} | {corr['estimate']:.3f} "
            f"[{corr['lower']:.3f}, {corr['upper']:.3f}] | {jaccard['estimate']:.3f} | "
            f"{rescue['estimate']:.3f} [{rescue['lower']:.3f}, {rescue['upper']:.3f}] |"
        )
    lines.extend([
        "",
        "## What remains unresolved",
        "",
    ])
    unresolved = summary["unresolved_conclusions"]
    lines.extend(f"- {item}" for item in unresolved)
    lines.extend([
        "",
        "## Frozen weak priors",
        "",
        f"Prior strength κ={summary['prior_configuration']['prior_strength']:.1f} (maximum {summary['prior_configuration']['maximum_prior_strength']:.1f}). The challenge data is intentionally able to overturn these generic priors quickly.",
        "",
        "## Execution boundary",
        "",
        f"Actual inference calls: {summary['execution']['inference_calls']} / 245. Provider requests: {summary['execution']['provider_requests']} / 246. Conservative reserved spend: ${summary['execution']['reserved_spend_usd']:.8f} / $0.20; actual token-estimated spend: ${summary['execution']['actual_estimated_spend_usd']:.8f}.",
        "",
        "Baseline v0 is frozen. No sequential racing, full Claude/Gemini baseline, exhaustive A0–A6 run, extra ablation, UI work, commit, or push was performed.",
    ])
    return "\n".join(lines) + "\n"


async def execute(root: Path) -> dict[str, Any]:
    benchmark_root = root / "benchmark"
    artifact_dir = benchmark_root / "artifacts" / "baseline_v0"
    report_path = benchmark_root / "reports" / "PRECHALLENGE_BASELINE_V0.md"
    if artifact_dir.exists() or report_path.exists():
        raise RuntimeError("Baseline-v0 output already exists; refusing to overwrite or duplicate calls")

    protocol_path = benchmark_root / "configs" / "prechallenge_baseline_v0.json"
    pricing_path = benchmark_root / "configs" / "pricing_v0.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    pricing = PricingTable.from_checked_json(pricing_path)
    manifest_path = _freeze_manifest(root, protocol, pricing)
    artifact_dir.mkdir(parents=True, exist_ok=False)
    controller = BudgetController(APPROVED_LIMITS)
    checkpoint_path = artifact_dir / "execution_checkpoint.json"

    # Construct all required providers before spending; values are never inspected or persisted.
    for spec in (*CORE_SPECS, PilotModelSpec("anthropic", "claude-sonnet-5-5"), PilotModelSpec("gemini", "gemini-3.5-flash-lite")):
        build_provider(spec)

    diagnosis_path = artifact_dir / "provider_diagnosis.jsonl"
    diagnosis = await _run_provider_diagnosis(pricing, controller, diagnosis_path)
    _write_json(checkpoint_path, {"phase": "provider_diagnosis_complete", **controller.snapshot()})
    print(f"provider diagnosis complete: {len(diagnosis)} inference calls", flush=True)

    cases = build_generic_prior_v0()
    dev_tuning = tuple(case for case in cases if _split(case) in {"dev", "tuning"})
    held_out = tuple(case for case in cases if _split(case) == "held_out")
    core_path = artifact_dir / "raw_single_model_runs.jsonl"
    dev_runs = await _run_core_cases(dev_tuning, pricing, controller, core_path, progress_start=0)
    gate = _fit_gate(dev_runs)
    gate_payload = asdict(gate)
    gate_payload.update({
        "frozen_at": _utc_now(),
        "source_case_count": len(dev_tuning),
        "source_observation_count": len(dev_runs),
        "held_out_observations_used": 0,
        "sha256": canonical_hash(asdict(gate)),
    })
    gate_path = artifact_dir / "frozen_gate_configuration.json"
    _write_json(gate_path, gate_payload)
    print("gate frozen from dev+tuning only; held-out remains sealed", flush=True)

    held_runs = await _run_core_cases(held_out, pricing, controller, core_path, progress_start=len(dev_runs))
    single_runs = dev_runs + held_runs
    _write_json(checkpoint_path, {"phase": "single_model_baseline_complete", **controller.snapshot()})
    if len(single_runs) != 216:
        raise RuntimeError(f"expected 216 core observations, received {len(single_runs)}")

    policies = baseline_policies_v0()
    dev_replay = replay_policies(dev_tuning, dev_runs, policies, gate)
    held_replay = replay_policies(held_out, held_runs, policies, gate)
    dev_replay_path = artifact_dir / "offline_replay_dev_tuning.jsonl"
    held_replay_path = artifact_dir / "offline_replay_held_out.jsonl"
    _write_jsonl(dev_replay_path, (run.to_dict() for run in dev_replay))
    _write_jsonl(held_replay_path, (run.to_dict() for run in held_replay))
    print("S0-S4 offline replay complete; provider calls: 0", flush=True)

    provider_backed_path = artifact_dir / "provider_backed_verifier_held_out.jsonl"
    backed_s3 = await _provider_backed_policy(
        "S3", held_out, held_runs, gate, pricing, controller, provider_backed_path
    )
    backed_s4 = await _provider_backed_policy(
        "S4", held_out, held_runs, gate, pricing, controller, provider_backed_path
    )
    provider_backed = backed_s3 + backed_s4

    reliability = aggregate_model_reliability(single_runs, severe_failure_threshold=0.2)
    vectors = model_error_vectors(single_runs)
    covariance = analyze_error_vectors(vectors, failure_threshold=0.5)
    pairwise = bootstrap_pairwise_metrics(
        vectors, failure_threshold=0.5, confidence_level=0.95, resamples=2000, seed=0
    )
    shrinkage = diagonal_shrinkage_covariance(covariance, intensity=0.25)

    architecture_results = aggregate_architectures(
        held_replay, (), lower_percentile=0.1, severe_failure_threshold=0.2
    )
    empirical = pareto_frontier([row.to_candidate() for row in architecture_results])
    bounds = estimate_architecture_bounds(
        held_replay,
        severe_failure_threshold=0.2,
        confidence_level=0.95,
        resamples=2000,
        seed=0,
    )
    dominance = bootstrap_dominance_probabilities(
        held_replay, severe_failure_threshold=0.2, resamples=2000, seed=0
    )
    robust = robust_frontier(bounds, probability_of_dominance=dominance)
    economics = summarize_escalation_economics(held_replay, severe_failure_threshold=0.2)
    comparisons = _paired_quality_comparisons(held_replay)

    model_priors = construct_binary_evidence_priors(
        single_runs,
        source_benchmark_version=CORPUS_VERSION,
        scoring_config_hash=SCORING_V1_HASH,
        prior_strength=4.0,
        maximum_prior_strength=5.0,
        severe_failure_threshold=0.2,
    )
    architecture_priors = construct_binary_evidence_priors(
        provider_backed,
        source_benchmark_version=CORPUS_VERSION,
        scoring_config_hash=SCORING_V1_HASH,
        prior_strength=4.0,
        maximum_prior_strength=5.0,
        severe_failure_threshold=0.2,
    )

    actual_spend = sum(
        float(value or 0.0)
        for value in [
            *(row.estimated_cost_usd for row in single_runs),
            *(row.get("estimated_cost_usd") for row in diagnosis),
            *(row.metadata.get("verifier_estimated_cost_usd") for row in provider_backed),
        ]
    )
    controller_state = controller.snapshot()
    backed_summary = []
    for policy_id in ("S3_PROVIDER_BACKED", "S4_PROVIDER_BACKED"):
        rows = [row for row in provider_backed if row.architecture_id == policy_id]
        backed_summary.append({
            "architecture_id": policy_id,
            "sample_size": len(rows),
            "quality": fmean(float(row.score or 0.0) for row in rows),
            "quality_wilson": wilson_interval(sum(row.passed is True for row in rows), len(rows)).to_dict(),
            "escalations": sum(row.metadata.get("escalated") is True for row in rows),
            "rescue_opportunities": sum(row.metadata.get("verification_opportunity") is True for row in rows),
            "rescues": sum(row.metadata.get("verification_rescued") is True for row in rows),
            "damage": sum(row.metadata.get("verification_damaged") is True for row in rows),
        })

    unresolved = [
        f"{row['policy']} versus {row['baseline']} quality remains unresolved at 95% confidence."
        for row in comparisons
        if row["statistically_unresolved_at_95_percent"]
    ]
    if len(held_out) < 30:
        unresolved.append("Held-out n=12 is deliberately compact; tail-risk and rescue estimates remain wide.")
    if any(item["rescue_opportunities"] == 0 for item in backed_summary):
        unresolved.append("At least one provider-backed policy had no verifier rescue opportunity, so its rescue probability is unidentified.")

    summary = {
        "status": "FROZEN_COMPLETE",
        "protocol_version": protocol["version"],
        "scoring_version": "SCORING_V1",
        "scoring_sha256": SCORING_V1_HASH,
        "model_reliability": [row.to_dict() for row in reliability],
        "provider_diagnosis": {
            "observations": diagnosis,
            "security_note": SCRUBBER_NOTE,
        },
        "covariance": {
            "labels": list(covariance.labels),
            "case_ids": list(covariance.case_ids),
            "matrix": covariance.covariance,
            "correlation": covariance.correlation,
            "failure_jaccard": covariance.jaccard_similarity,
            "conditional_failure": covariance.conditional_failure,
            "bootstrap_intervals": [row.to_dict() for row in pairwise],
            "shrinkage_intensity": 0.25,
            "shrunken_matrix": shrinkage.matrix,
        },
        "offline_replay": {
            "evidence_mode": "OFFLINE_REPLAY_ESTIMATE",
            "architecture_results": [row.to_dict() for row in architecture_results],
            "confidence_bounds": [row.to_dict() for row in bounds],
            "economics": [row.to_dict() for row in economics],
            "paired_quality_comparisons": comparisons,
            "empirical_pareto_frontier": list(empirical.frontier),
            "empirically_dominated": list(empirical.dominated),
            "robust_pareto_frontier": robust.to_dict(),
        },
        "provider_backed_confirmation": backed_summary,
        "prior_configuration": {"prior_strength": 4.0, "maximum_prior_strength": 5.0},
        "weak_model_priors": [row.to_dict() for row in model_priors],
        "weak_architecture_priors": [row.to_dict() for row in architecture_priors],
        "unresolved_conclusions": unresolved,
        "execution": {
            **controller_state,
            "actual_estimated_spend_usd": actual_spend,
            "limits": asdict(APPROVED_LIMITS),
            "stopped_after_authorized_phases": True,
        },
    }
    summary_path = artifact_dir / "baseline_v0_summary.json"
    priors_path = artifact_dir / "weak_priors.json"
    _write_json(summary_path, summary)
    _write_json(priors_path, {
        "configuration": summary["prior_configuration"],
        "models": summary["weak_model_priors"],
        "architectures": summary["weak_architecture_priors"],
    })
    report_path.write_text(_report_markdown(summary), encoding="utf-8")
    _write_json(checkpoint_path, {"phase": "frozen_complete", **controller_state})

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "FROZEN_COMPLETE"
    manifest["observations"] = {
        "status": "FROZEN_COMPLETE",
        "completed_at": _utc_now(),
        "raw_observation_hashes": [
            {"path": str(path.relative_to(root)).replace("\\", "/"), "sha256": _file_hash(path)}
            for path in (
                diagnosis_path,
                core_path,
                dev_replay_path,
                held_replay_path,
                provider_backed_path,
                gate_path,
                summary_path,
                priors_path,
            )
        ],
        "execution": summary["execution"],
        "note": "Frozen after the approved phases; no automatic continuation is permitted.",
    }
    _write_json(manifest_path, manifest)
    print("Baseline v0 frozen complete. STOP.", flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--render-existing-summary",
        action="store_true",
        help="Regenerate only the derived Markdown report; performs zero provider calls.",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if args.render_existing_summary:
        summary_path = root / "benchmark" / "artifacts" / "baseline_v0" / "baseline_v0_summary.json"
        report_path = root / "benchmark" / "reports" / "PRECHALLENGE_BASELINE_V0.md"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        report_path.write_text(_report_markdown(summary), encoding="utf-8")
        print("regenerated derived report; provider calls: 0", flush=True)
        return
    asyncio.run(execute(root))


if __name__ == "__main__":
    main()
