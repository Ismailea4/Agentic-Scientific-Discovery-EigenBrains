"""Pick the first preferred candidate that passes every hard check."""

from __future__ import annotations

from collections.abc import Sequence

from ..capabilities.models import Capability
from ..capabilities.policy import downward_closure, implication_map
from ..core.logging import log_event
from .models import FallbackCandidate, FallbackDecision, FallbackPolicy


def _failures(
    candidate: FallbackCandidate,
    policy: FallbackPolicy,
    implies: dict[str, tuple[str, ...]],
) -> list[str]:
    reasons: list[str] = []
    if not candidate.available:
        reasons.append("unavailable")
    held = downward_closure(candidate.capabilities, implies)
    for capability in policy.mandatory_capabilities:
        if capability not in held:
            reasons.append(f"missing mandatory capability '{capability}'")
    if candidate.privacy_class not in policy.accepted_privacy_classes:
        reasons.append(f"privacy class '{candidate.privacy_class}' is not accepted")
    if policy.task not in candidate.allowed_tasks:
        reasons.append(f"task '{policy.task}' is not allowed")
    return reasons


def resolve_fallback(
    candidates: Sequence[FallbackCandidate],
    policy: FallbackPolicy,
    catalogue: Sequence[Capability] = (),
) -> FallbackDecision:
    """Return an auditable decision. `selected_id` is None when nothing qualifies.

    Candidates that pass every check but are absent from `preference_order`
    are rejected. Unknown ids in the preference order are recorded and skipped.
    """

    identifiers = [candidate.id for candidate in candidates]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("fallback candidate ids must be unique")

    implies = implication_map(catalogue)
    by_id = {candidate.id: candidate for candidate in candidates}
    rejected: list[tuple[str, str]] = []
    eligible: set[str] = set()

    for candidate in candidates:
        failures = _failures(candidate, policy, implies)
        if failures:
            rejected.append((candidate.id, "; ".join(failures)))
        else:
            eligible.add(candidate.id)

    for preferred in policy.preference_order:
        if preferred not in by_id:
            rejected.append((preferred, "not a known candidate"))

    for candidate in candidates:
        if candidate.id in eligible and candidate.id not in policy.preference_order:
            rejected.append((candidate.id, "not in preference order"))
            eligible.remove(candidate.id)

    selected: str | None = None
    for preferred in policy.preference_order:
        if preferred in eligible:
            selected = preferred
            break

    if selected is None:
        reason = (
            "no candidate satisfied availability, capabilities, privacy, and task allow-list"
        )
    else:
        reason = (
            f"selected '{selected}' as the first preference-order candidate "
            "that satisfied every constraint"
        )

    for candidate in candidates:
        log_event(
            "fallback.considered",
            fallback_attempted=candidate.id,
            available=candidate.available,
        )
    for identifier, why in sorted(rejected):
        log_event(
            "fallback.rejected",
            fallback_attempted=identifier,
            rejected_reason=why,
        )
    if selected is not None:
        log_event("fallback.selected", fallback_selected=selected, capability_reason=reason)
    else:
        log_event("fallback.rejected", rejected_reason=reason)

    return FallbackDecision(
        selected_id=selected,
        considered=tuple(sorted(by_id)),
        rejected=tuple(sorted(rejected)),
        reason=reason,
    )
