"""Frozen S0-S4 policies for the first selective-escalation experiment."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


QWEN = "groq/qwen/qwen3.8-27b"
GPT_OSS = "groq/openai/gpt-oss-20b"

VERIFIER_PROMPT_V1 = (
    "Independently verify the proposed answer against the task. Return only the corrected "
    "answer in the task's requested format; do not explain or mention the proposal."
)

ALLOWED_ESCALATION_SIGNALS = frozenset({
    "task_family",
    "schema_or_constraint_failure",
    "task_risk_level",
    "historical_task_family_error_ucb",
    "explicit_abstention",
})


@dataclass(frozen=True)
class EscalationPolicy:
    id: str
    name: str
    first_model: str
    second_model: str | None
    escalation_mode: str
    escalation_signals: tuple[str, ...]
    reconciliation_rule: str
    replayable_from_paired_single_model_runs: bool = True

    def __post_init__(self) -> None:
        if self.escalation_mode not in {"never", "always", "conditional"}:
            raise ValueError(f"unknown escalation mode '{self.escalation_mode}'")
        if self.escalation_mode == "never" and self.second_model is not None:
            raise ValueError("single-model policy cannot define a second model")
        if self.escalation_mode != "never" and self.second_model is None:
            raise ValueError("multi-model policy requires a second model")
        forbidden = set(self.escalation_signals) - ALLOWED_ESCALATION_SIGNALS
        if forbidden:
            raise ValueError(f"policy contains non-runtime signals: {sorted(forbidden)}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


RECONCILIATION_V1 = (
    "canonical agreement wins; otherwise choose the sole schema/constraint-valid answer; "
    "if both remain valid and disagree, high-risk cases return INSUFFICIENT_EVIDENCE and "
    "lower-risk cases use the task-family owner frozen on development/tuning data"
)


def baseline_policies_v0() -> tuple[EscalationPolicy, ...]:
    conditional_signals = (
        "schema_or_constraint_failure",
        "explicit_abstention",
        "task_risk_level",
        "historical_task_family_error_ucb",
        "task_family",
    )
    return (
        EscalationPolicy("S0", "GPT-OSS only", GPT_OSS, None, "never", (), "first_answer"),
        EscalationPolicy("S1", "Qwen only", QWEN, None, "never", (), "first_answer"),
        EscalationPolicy("S2", "Always GPT-OSS + Qwen", QWEN, GPT_OSS, "always", (), RECONCILIATION_V1),
        EscalationPolicy("S3", "Qwen then selective GPT-OSS", QWEN, GPT_OSS, "conditional", conditional_signals, RECONCILIATION_V1),
        EscalationPolicy("S4", "GPT-OSS then selective Qwen", GPT_OSS, QWEN, "conditional", conditional_signals, RECONCILIATION_V1),
    )


def validate_frozen_thresholds(
    thresholds: Mapping[str, Any], *, observed_splits: Sequence[str]
) -> None:
    """Reject held-out threshold fitting and undeclared runtime signals."""
    if "held_out" in set(observed_splits):
        raise ValueError("escalation thresholds cannot be fitted on held-out evidence")
    signals = set(thresholds.get("signals", ()))
    forbidden = signals - ALLOWED_ESCALATION_SIGNALS
    if forbidden:
        raise ValueError(f"thresholds contain non-runtime signals: {sorted(forbidden)}")
    if thresholds.get("uses_ground_truth") is not False:
        raise ValueError("threshold fitting must explicitly prohibit runtime ground truth")
