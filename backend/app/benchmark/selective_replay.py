"""Ground-truth-blind replay of S0-S4 from paired single-model observations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from statistics import fmean
from typing import Mapping, Sequence

from .evaluators import EvaluatorRegistry, canonicalize_scoring_v1
from .models import BenchmarkCase, BenchmarkRun, SystemOutcome
from .policies import EscalationPolicy


def _model_label(run: BenchmarkRun) -> str:
    return f"{run.provider}/{run.model}"


@dataclass(frozen=True)
class FrozenGateConfiguration:
    fitted_splits: tuple[str, ...]
    escalate_high_risk: bool
    escalate_task_families: tuple[str, ...]
    historical_task_family_error_ucb: dict[str, float]
    historical_error_ucb_threshold: float
    task_family_owner: dict[str, str]
    signals: tuple[str, ...] = (
        "schema_or_constraint_failure",
        "explicit_abstention",
        "task_risk_level",
        "historical_task_family_error_ucb",
        "task_family",
    )
    uses_ground_truth: bool = False

    def __post_init__(self) -> None:
        if "held_out" in self.fitted_splits:
            raise ValueError("gate configuration cannot be fitted on held-out evidence")
        if not 0 <= self.historical_error_ucb_threshold <= 1:
            raise ValueError("historical error threshold must be in [0, 1]")
        if self.uses_ground_truth:
            raise ValueError("runtime escalation cannot use ground truth")


@dataclass(frozen=True)
class ReplayDecision:
    output: object
    outcome: SystemOutcome
    escalated: bool
    escalation_reasons: tuple[str, ...] = ()
    reconciliation: str = "first_answer"
    selected_model: str | None = None


@dataclass(frozen=True)
class EscalationEconomics:
    policy_id: str
    baseline_policy_id: str
    sample_size: int
    escalation_probability: float
    rescue_probability: float | None
    damage_probability: float | None
    mean_quality: float
    severe_failure_probability: float
    mean_cost_usd: float | None
    mean_latency_ms: float
    incremental_quality: float
    incremental_cost_usd: float | None
    incremental_latency_ms: float
    cost_saving_vs_always_both_usd: float | None
    latency_saving_vs_always_both_ms: float
    severe_failures_avoided: float
    quality_gain_per_incremental_dollar: float | None
    severe_failures_avoided_per_incremental_dollar: float | None
    tail_risk_reduction_per_incremental_dollar: float | None
    quality_gain_per_incremental_second: float | None
    expected_loss_reduction: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _should_escalate(
    first: BenchmarkRun,
    case: BenchmarkCase,
    gate: FrozenGateConfiguration,
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    risk = str(getattr(case.risk_level, "value", case.risk_level))
    task = str(getattr(case.task_type, "value", case.task_type))
    if not first.success or first.malformed_output or first.constraint_violations:
        reasons.append("schema_or_constraint_failure")
    if first.abstained:
        reasons.append("explicit_abstention")
    if gate.escalate_high_risk and risk == "high":
        reasons.append("task_risk_level")
    if task in gate.escalate_task_families:
        reasons.append("task_family")
    if gate.historical_task_family_error_ucb.get(task, 0.0) >= gate.historical_error_ucb_threshold:
        reasons.append("historical_task_family_error_ucb")
    return bool(reasons), tuple(dict.fromkeys(reasons))


def replay_decision(
    policy: EscalationPolicy,
    case: BenchmarkCase,
    first: BenchmarkRun,
    second: BenchmarkRun | None,
    gate: FrozenGateConfiguration,
) -> ReplayDecision:
    if policy.escalation_mode == "never":
        return ReplayDecision(first.output, first.outcome, False, selected_model=policy.first_model)
    if policy.escalation_mode == "always":
        escalate, reasons = True, ("always",)
    else:
        escalate, reasons = _should_escalate(first, case, gate)
    if not escalate:
        return ReplayDecision(first.output, first.outcome, False, selected_model=policy.first_model)
    if second is None:
        raise ValueError(f"policy {policy.id} requires a paired second-model observation")
    if not first.success and not second.success:
        return ReplayDecision("INSUFFICIENT_EVIDENCE", SystemOutcome.INSUFFICIENT_EVIDENCE, True, reasons, "both_provider_failures")
    if not first.success:
        return ReplayDecision(second.output, second.outcome, True, reasons, "second_provider_success", policy.second_model)
    if not second.success:
        return ReplayDecision(first.output, first.outcome, True, reasons, "first_provider_success", policy.first_model)
    first_valid = not first.malformed_output and not first.constraint_violations
    second_valid = not second.malformed_output and not second.constraint_violations
    if first_valid and not second_valid:
        return ReplayDecision(first.output, first.outcome, True, reasons, "sole_valid_first", policy.first_model)
    if second_valid and not first_valid:
        return ReplayDecision(second.output, second.outcome, True, reasons, "sole_valid_second", policy.second_model)
    if canonicalize_scoring_v1(case, first.output) == canonicalize_scoring_v1(case, second.output):
        return ReplayDecision(first.output, first.outcome, True, reasons, "canonical_agreement", policy.first_model)
    risk = str(getattr(case.risk_level, "value", case.risk_level))
    if risk == "high":
        return ReplayDecision("INSUFFICIENT_EVIDENCE", SystemOutcome.INSUFFICIENT_EVIDENCE, True, reasons, "high_risk_disagreement")
    task = str(getattr(case.task_type, "value", case.task_type))
    owner = gate.task_family_owner.get(task)
    if owner == policy.second_model:
        return ReplayDecision(second.output, second.outcome, True, reasons, "frozen_task_owner", owner)
    return ReplayDecision(first.output, first.outcome, True, reasons, "frozen_task_owner", policy.first_model)


def replay_policies(
    cases: Sequence[BenchmarkCase],
    single_model_runs: Sequence[BenchmarkRun],
    policies: Sequence[EscalationPolicy],
    gate: FrozenGateConfiguration,
) -> list[BenchmarkRun]:
    """Evaluate policies without new inference calls; ground truth is used only after routing."""
    case_by_id = {case.id: case for case in cases}
    observations: dict[tuple[str, str], BenchmarkRun] = {}
    for run in single_model_runs:
        if run.metadata.get("final_output") is not True:
            continue
        key = (_model_label(run), run.benchmark_case_id)
        if key in observations:
            raise ValueError(f"duplicate single-model observation: {key}")
        observations[key] = run
    registry = EvaluatorRegistry()
    output: list[BenchmarkRun] = []
    for case in cases:
        for policy in policies:
            first = observations.get((policy.first_model, case.id))
            if first is None:
                raise ValueError(f"missing {policy.first_model} observation for {case.id}")
            second = (
                observations.get((policy.second_model, case.id))
                if policy.second_model is not None else None
            )
            decision = replay_decision(policy, case, first, second, gate)
            evaluation = registry.resolve(case).evaluate(case, decision.output)
            selected = [first]
            if decision.escalated and second is not None:
                selected.append(second)
            known_cost = all(row.estimated_cost_usd is not None for row in selected if row.success)
            cost = (
                sum(float(row.estimated_cost_usd or 0.0) for row in selected if row.success)
                if known_cost else None
            )
            first_correct = first.passed is True
            final_correct = evaluation.passed is True
            output.append(
                BenchmarkRun(
                    benchmark_case_id=case.id,
                    task_type=str(getattr(case.task_type, "value", case.task_type)),
                    architecture_id=policy.id,
                    agent_role="replay_policy",
                    provider="offline_replay",
                    model=policy.id,
                    output=decision.output,
                    success=decision.outcome in {SystemOutcome.ANSWER, SystemOutcome.VERIFY},
                    error_type=None,
                    latency_ms=sum(row.latency_ms for row in selected),
                    input_tokens=sum(row.input_tokens for row in selected),
                    output_tokens=sum(row.output_tokens for row in selected),
                    estimated_cost_usd=cost,
                    score=evaluation.score,
                    passed=evaluation.passed,
                    outcome=decision.outcome,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    metadata={
                        "final_output": True,
                        "split": str(getattr(case.split, "value", case.split)),
                        "risk_level": str(getattr(case.risk_level, "value", case.risk_level)),
                        "difficulty": str(getattr(case.difficulty, "value", case.difficulty)),
                        "replayed_without_provider_calls": True,
                        "escalated": decision.escalated,
                        "escalation_reasons": list(decision.escalation_reasons),
                        "reconciliation": decision.reconciliation,
                        "selected_model": decision.selected_model,
                        "verification_opportunity": decision.escalated and not first_correct,
                        "verification_rescued": decision.escalated and not first_correct and final_correct,
                        "verification_damaged": decision.escalated and first_correct and not final_correct,
                        "evaluation": dict(evaluation.metadata),
                    },
                    abstained=decision.outcome is SystemOutcome.INSUFFICIENT_EVIDENCE,
                )
            )
    return output


def summarize_escalation_economics(
    replay_runs: Sequence[BenchmarkRun],
    *,
    severe_failure_threshold: float = 0.2,
) -> list[EscalationEconomics]:
    """Quantify selective escalation relative to first-only and always-both."""
    grouped: dict[str, dict[str, BenchmarkRun]] = {}
    for run in replay_runs:
        if run.metadata.get("final_output") is True:
            grouped.setdefault(run.architecture_id, {})[run.benchmark_case_id] = run
    if "S2" not in grouped:
        raise ValueError("economics summary requires the always-both S2 policy")

    def metrics(rows: list[BenchmarkRun]) -> tuple[float, float, float | None, float, float]:
        quality = fmean(float(row.score or 0.0) for row in rows)
        severe = fmean(
            float(
                not row.success
                or row.score is None
                or float(row.score or 0.0) <= severe_failure_threshold
            )
            for row in rows
        )
        costs = [row.estimated_cost_usd for row in rows]
        cost = None if any(value is None for value in costs) else fmean(float(value) for value in costs)
        latency = fmean(row.latency_ms for row in rows)
        losses = sorted((1.0 - float(row.score or 0.0) for row in rows), reverse=True)
        worst_count = max(1, round(len(losses) * 0.1))
        tail_loss = fmean(losses[:worst_count])
        return quality, severe, cost, latency, tail_loss

    output: list[EscalationEconomics] = []
    for policy_id, baseline_id in (("S3", "S1"), ("S4", "S0"), ("S2", "S1")):
        if policy_id not in grouped or baseline_id not in grouped:
            continue
        case_ids = sorted(grouped[policy_id])
        if set(case_ids) != set(grouped[baseline_id]) or set(case_ids) != set(grouped["S2"]):
            raise ValueError("policy economics require identical paired case coverage")
        rows = [grouped[policy_id][case_id] for case_id in case_ids]
        baseline = [grouped[baseline_id][case_id] for case_id in case_ids]
        always = [grouped["S2"][case_id] for case_id in case_ids]
        quality, severe, cost, latency, tail = metrics(rows)
        base_quality, base_severe, base_cost, base_latency, base_tail = metrics(baseline)
        _, _, always_cost, always_latency, _ = metrics(always)
        incremental_cost = None if cost is None or base_cost is None else cost - base_cost
        quality_gain = quality - base_quality
        severe_avoided = base_severe - severe
        tail_reduction = base_tail - tail
        opportunities = [row for row in rows if row.metadata.get("verification_opportunity") is True]
        correct_escalations = [
            row for row in rows
            if row.metadata.get("escalated") is True
            and row.metadata.get("verification_opportunity") is not True
        ]
        output.append(
            EscalationEconomics(
                policy_id=policy_id,
                baseline_policy_id=baseline_id,
                sample_size=len(rows),
                escalation_probability=sum(row.metadata.get("escalated") is True for row in rows) / len(rows),
                rescue_probability=(
                    sum(row.metadata.get("verification_rescued") is True for row in opportunities) / len(opportunities)
                    if opportunities else None
                ),
                damage_probability=(
                    sum(row.metadata.get("verification_damaged") is True for row in correct_escalations) / len(correct_escalations)
                    if correct_escalations else None
                ),
                mean_quality=quality,
                severe_failure_probability=severe,
                mean_cost_usd=cost,
                mean_latency_ms=latency,
                incremental_quality=quality_gain,
                incremental_cost_usd=incremental_cost,
                incremental_latency_ms=latency - base_latency,
                cost_saving_vs_always_both_usd=(
                    None if always_cost is None or cost is None else always_cost - cost
                ),
                latency_saving_vs_always_both_ms=always_latency - latency,
                severe_failures_avoided=severe_avoided,
                quality_gain_per_incremental_dollar=(
                    quality_gain / incremental_cost
                    if incremental_cost is not None and incremental_cost > 0 else None
                ),
                severe_failures_avoided_per_incremental_dollar=(
                    severe_avoided / incremental_cost
                    if incremental_cost is not None and incremental_cost > 0 else None
                ),
                tail_risk_reduction_per_incremental_dollar=(
                    tail_reduction / incremental_cost
                    if incremental_cost is not None and incremental_cost > 0 else None
                ),
                quality_gain_per_incremental_second=(
                    quality_gain / ((latency - base_latency) / 1000.0)
                    if latency > base_latency else None
                ),
                expected_loss_reduction=quality_gain,
            )
        )
    return output
