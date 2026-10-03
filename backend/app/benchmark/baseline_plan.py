"""Offline freeze and reduced-budget proposal for Architecture Baseline v0."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..instrumentation.pricing import PricingTable
from .corpus import CORPUS_VERSION
from .evaluators import SCORING_V1_HASH, SCORING_V1_SPEC, SCORING_V1_VERSION
from .models import BenchmarkCase
from .pilot import PILOT_PROMPT
from .policies import VERIFIER_PROMPT_V1, baseline_policies_v0


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cost(
    pricing: PricingTable,
    model: str,
    calls: int,
    input_token_cap: int,
    output_token_cap: int,
) -> float:
    per_call = pricing.estimate_cost(model, input_token_cap, output_token_cap)
    if per_call is None:
        raise ValueError(f"missing checked pricing for {model}")
    return per_call * calls


def build_reduced_budget(pricing: PricingTable) -> dict[str, Any]:
    diagnosis_cost = (
        _cost(pricing, "claude-sonnet-5-5", 1, 256, 64)
        + _cost(pricing, "claude-haiku-4-5-20251001", 1, 256, 64)
        + _cost(pricing, "gemini-3.5-flash-lite", 3, 256, 64)
    )
    core_models = (
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
        "deepseek/deepseek-v4.1-flash",
    )
    baseline_cost = sum(_cost(pricing, model, 72, 1024, 256) for model in core_models)
    compact_confirmation_cost = (
        _cost(pricing, "qwen/qwen3.8-27b", 12, 1024, 256)
        + _cost(pricing, "openai/gpt-oss-20b", 12, 1024, 256)
    )
    racing_cost = compact_confirmation_cost
    gemini_optional = _cost(pricing, "gemini-3.5-flash-lite", 72, 1024, 256)
    claude_optional = _cost(pricing, "claude-sonnet-5-5", 72, 1024, 256)
    phases = {
        "provider_diagnosis": {
            "provider_requests": 6,
            "inference_calls": 5,
            "dollar_ceiling": diagnosis_cost,
            "note": "Includes one unpriced catalogue request and five capped inference calls.",
        },
        "core_72_case_single_model_baseline": {
            "provider_requests": 216,
            "inference_calls": 216,
            "dollar_ceiling": baseline_cost,
        },
        "s0_to_s4_offline_replay": {
            "provider_requests": 0,
            "inference_calls": 0,
            "dollar_ceiling": 0.0,
            "note": "Reuses paired single-model observations; no model outputs are fabricated.",
        },
        "compact_provider_backed_verifier_confirmation": {
            "provider_requests": 24,
            "inference_calls": 24,
            "dollar_ceiling": compact_confirmation_cost,
            "note": "At most 12 Qwen and 12 GPT-OSS verifier calls after policies are frozen.",
        },
        "targeted_sequential_racing": {
            "provider_requests": 24,
            "inference_calls": 24,
            "dollar_ceiling": racing_cost,
            "note": "Not automatic; release only for unresolved frontier or rescue questions.",
        },
    }
    core_total = sum(float(item["dollar_ceiling"]) for item in phases.values())
    core_requests = sum(int(item["provider_requests"]) for item in phases.values())
    initial_phase_names = (
        "provider_diagnosis",
        "core_72_case_single_model_baseline",
        "s0_to_s4_offline_replay",
        "compact_provider_backed_verifier_confirmation",
    )
    initial_cost = sum(float(phases[name]["dollar_ceiling"]) for name in initial_phase_names)
    initial_requests = sum(int(phases[name]["provider_requests"]) for name in initial_phase_names)
    initial_calls = sum(int(phases[name]["inference_calls"]) for name in initial_phase_names)
    return {
        "currency": "USD",
        "pricing_basis": "checked pricing_v0; 1024 input/256 output cap except 256/64 diagnostics",
        "phases": phases,
        "core_total": {
            "provider_requests": core_requests,
            "inference_calls": 269,
            "dollar_ceiling": core_total,
        },
        "recommended_initial_approval": {
            "phases": list(initial_phase_names),
            "provider_requests": initial_requests,
            "inference_calls": initial_calls,
            "dollar_ceiling": initial_cost,
            "excludes_sequential_racing": True,
        },
        "conditional_additions": {
            "gemini_72_cases_if_stable": {
                "provider_requests": 72,
                "dollar_ceiling": gemini_optional,
            },
            "claude_72_cases_if_resolved": {
                "provider_requests": 72,
                "dollar_ceiling": claude_optional,
            },
        },
        "authorization": "NOT_APPROVED",
    }


def build_protocol_manifest(
    cases: Sequence[BenchmarkCase],
    protocol: Mapping[str, Any],
    budget: Mapping[str, Any],
) -> dict[str, Any]:
    case_payload = [case.to_dict() for case in cases]
    policies = [policy.to_dict() for policy in baseline_policies_v0()]
    gate = dict(protocol["policies"]["gate"])
    solver_prompt = {
        "system": PILOT_PROMPT,
        "temperature": protocol["prompt"]["temperature"],
        "max_output_tokens": protocol["prompt"]["max_output_tokens"],
    }
    verifier_prompt = {
        "system": VERIFIER_PROMPT_V1,
        "temperature": protocol["prompt"]["temperature"],
        "max_output_tokens": protocol["prompt"]["max_output_tokens"],
    }
    manifest = {
        "version": protocol["version"],
        "status": "PLANNED_AWAITING_APPROVAL",
        "immutable_after_execution_starts": True,
        "corpus": {
            "version": CORPUS_VERSION,
            "case_count": len(cases),
            "sha256": canonical_hash(case_payload),
        },
        "scoring": {
            "version": SCORING_V1_VERSION,
            "sha256": SCORING_V1_HASH,
            "specification": SCORING_V1_SPEC,
            "secondary_metric": "primary_v0",
        },
        "prompts": {
            "solver": {**solver_prompt, "sha256": canonical_hash(solver_prompt)},
            "verifier": {**verifier_prompt, "sha256": canonical_hash(verifier_prompt)},
        },
        "models": {
            "core": list(protocol["core_models"]),
            "conditional": list(protocol["conditional_models"]),
        },
        "policies": {
            "version": protocol["policies"]["version"],
            "definitions": policies,
            "gate": gate,
            "sha256": canonical_hash({"definitions": policies, "gate": gate}),
            "threshold_fit_splits": list(protocol["splits"]["threshold_fitting"]),
            "final_evaluation_split": "held_out",
        },
        "statistics": dict(protocol["statistics"]),
        "budget_proposal": budget,
        "observations": {
            "status": "NOT_RUN",
            "raw_observation_hashes": [],
            "note": "Observation hashes are appended only after an approved execution; this file is never silently overwritten.",
        },
    }
    manifest["protocol_sha256"] = canonical_hash({
        key: manifest[key]
        for key in ("corpus", "scoring", "prompts", "models", "policies", "statistics", "budget_proposal")
    })
    return manifest


def write_plan_artifacts(
    benchmark_root: str | Path,
    *,
    cases: Sequence[BenchmarkCase],
    protocol: Mapping[str, Any],
    pricing: PricingTable,
) -> dict[str, Path]:
    root = Path(benchmark_root)
    budget = build_reduced_budget(pricing)
    manifest = build_protocol_manifest(cases, protocol, budget)
    manifest_path = root / "cases" / "pre_challenge_baseline_v0_manifest.json"
    budget_path = root / "configs" / "prechallenge_budget_v0.json"
    report_path = root / "reports" / "PRECHALLENGE_BASELINE_BUDGET.md"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("observations", {}).get("status") != "NOT_RUN":
            raise ValueError("Baseline-v0 manifest already contains observations and is immutable")
        existing_hash = existing.get("protocol_sha256")
        if (
            existing.get("status") != "PLANNED_AWAITING_APPROVAL"
            and existing_hash is not None
            and existing_hash != manifest["protocol_sha256"]
        ):
            raise ValueError("frozen Baseline-v0 protocol drift detected")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    budget_path.write_text(json.dumps(budget, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    phases = budget["phases"]
    report_lines = [
        "# Architecture Baseline v0 - approval gate",
        "",
        "No provider calls described here have been executed.",
        "",
        "## Reduced budget",
        "",
        "| Phase | Provider requests | Inference calls | Dollar ceiling |",
        "|---|---:|---:|---:|",
    ]
    for name, phase in phases.items():
        report_lines.append(
            f"| {name} | {phase['provider_requests']} | {phase['inference_calls']} | ${phase['dollar_ceiling']:.8f} |"
        )
    report_lines.extend([
        "",
        f"Recommended initial approval: **{budget['recommended_initial_approval']['provider_requests']} provider requests, "
        f"{budget['recommended_initial_approval']['inference_calls']} inference calls, "
        f"${budget['recommended_initial_approval']['dollar_ceiling']:.8f}**. This excludes sequential racing.",
        "",
        f"Maximum including the separately gated racing reserve: **{budget['core_total']['provider_requests']} provider requests, "
        f"{budget['core_total']['inference_calls']} inference calls, "
        f"${budget['core_total']['dollar_ceiling']:.8f}**.",
        "",
        "The sequential-racing allocation is a ceiling, not an automatic spend. S0-S4 replay itself makes zero provider calls.",
        "",
        "## Compact architecture claim",
        "",
        "The first target is Qwen-first selective GPT-OSS escalation versus GPT-OSS-only, Qwen-only, always-both, and reverse escalation. Evidence must report quality, severe/tail risk, escalation probability, rescue/damage, cost, latency, and confidence intervals. It must not claim that all A0-A6 architectures were measured.",
        "",
        "## Approval status",
        "",
        "`NOT_APPROVED` - stop here until the user authorizes explicit phase ceilings.",
    ])
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return {"manifest": manifest_path, "budget": budget_path, "report": report_path}
