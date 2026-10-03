"""Least-privilege capability evaluation.

Implication edges point from a stronger capability to the weaker ones it
includes. Denial travels the other way: if a capability implies a denied
one, the stronger capability is denied too, so a grant cannot smuggle in a
blocked action.

Leases are the only runtime grants. An unscoped lease applies to every task.
A scoped lease applies only to that exact task scope. When an allowing lease
and a denying lease both apply and are active, denial wins.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone

from ..core.logging import log_event
from .models import (
    AgentCapabilityProfile,
    Capability,
    CapabilityLease,
    CapabilityPolicy,
    CapabilityRequirement,
    PolicyDecision,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def implication_map(catalogue: Sequence[Capability]) -> dict[str, tuple[str, ...]]:
    return {capability.name: tuple(capability.implies) for capability in catalogue}


def downward_closure(seeds: Iterable[str], implies: Mapping[str, Sequence[str]]) -> set[str]:
    """Capabilities held by inheriting everything `seeds` imply."""

    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(implies.get(current, ()))
    return seen


def denial_closure(
    denied: Iterable[str],
    implies: Mapping[str, Sequence[str]],
    extra_nodes: Iterable[str] = (),
) -> set[str]:
    """Explicit denials plus every capability that implies a denied one."""

    denied_set = set(denied)
    nodes = set(implies) | denied_set | set(extra_nodes)
    for targets in implies.values():
        nodes.update(targets)

    changed = True
    while changed:
        changed = False
        for node in list(nodes):
            if node in denied_set:
                continue
            if any(child in denied_set for child in implies.get(node, ())):
                denied_set.add(node)
                changed = True
    return denied_set


def _inactive_reason(lease: CapabilityLease, now: datetime) -> str | None:
    if lease.expires_at is not None and now >= _as_utc(lease.expires_at):
        return "expired"
    if lease.max_calls is not None and lease.calls_used >= lease.max_calls:
        return "exhausted"
    return None


def _explain_missing(
    name: str,
    leases: Sequence[CapabilityLease],
    task_scope: str | None,
    now: datetime,
    denied: set[str],
) -> list[str]:
    if name in denied:
        return [f"capability '{name}' is denied"]

    related = [lease for lease in leases if lease.capability == name]
    if not related:
        return [f"no lease grants '{name}'"]

    explanations: list[str] = []
    for lease in related:
        if lease.task_scope is not None and lease.task_scope != task_scope:
            scope = task_scope if task_scope is not None else "unscoped"
            explanations.append(
                f"lease for '{name}' is scoped to '{lease.task_scope}', not '{scope}'"
            )
            continue
        inactive = _inactive_reason(lease, now)
        if inactive == "expired":
            explanations.append(f"lease for '{name}' is expired")
        elif inactive == "exhausted":
            explanations.append(f"lease for '{name}' has reached max_calls")
        elif not lease.allowed:
            explanations.append(f"capability '{name}' is denied")
    if explanations:
        return explanations
    return [f"no active lease grants '{name}'"]


def evaluate_policy(
    catalogue: Sequence[Capability],
    requirements: Sequence[CapabilityRequirement],
    denied: Sequence[str],
    leases: Sequence[CapabilityLease],
    task_scope: str | None,
    now: datetime | None = None,
) -> PolicyDecision:
    """Decide which capabilities are effective for one task scope.

    `allowed` is true only when every mandatory requirement is in the
    effective set. Optional requirements are reported when missing and never
    flip `allowed` on their own. The function does not score quality or cost.
    """

    moment = _as_utc(now or datetime.now(timezone.utc))
    implies = implication_map(catalogue)

    active_grants: list[str] = []
    active_denials: list[str] = []
    for lease in leases:
        if lease.task_scope is not None and lease.task_scope != task_scope:
            continue
        if _inactive_reason(lease, moment) is not None:
            continue
        if lease.allowed:
            active_grants.append(lease.capability)
        else:
            active_denials.append(lease.capability)

    extra_nodes = [lease.capability for lease in leases]
    extra_nodes.extend(requirement.capability for requirement in requirements)
    closed_denied = denial_closure(
        set(denied) | set(active_denials), implies, extra_nodes
    )
    direct_grants = [name for name in active_grants if name not in closed_denied]
    effective = downward_closure(direct_grants, implies) - closed_denied

    missing_mandatory = tuple(
        sorted(
            {
                requirement.capability
                for requirement in requirements
                if requirement.mandatory and requirement.capability not in effective
            }
        )
    )
    missing_optional = tuple(
        sorted(
            {
                requirement.capability
                for requirement in requirements
                if not requirement.mandatory and requirement.capability not in effective
            }
        )
    )

    reasons: list[str] = []
    if missing_mandatory:
        for name in missing_mandatory:
            reasons.append(f"missing mandatory capability '{name}'")
            reasons.extend(
                _explain_missing(name, leases, task_scope, moment, closed_denied)
            )
    else:
        reasons.append("all mandatory capabilities are satisfied")
    for name in missing_optional:
        reasons.append(f"missing optional capability '{name}'")

    decision = PolicyDecision(
        allowed=not missing_mandatory,
        granted=tuple(sorted(effective)),
        denied=tuple(sorted(closed_denied)),
        missing_mandatory=missing_mandatory,
        missing_optional=missing_optional,
        reasons=tuple(sorted(set(reasons))),
        timestamp=moment,
    )
    requested = [item.capability for item in requirements]
    if decision.allowed:
        log_event(
            "capability.granted",
            capability_requested=requested,
            capability_granted=list(decision.granted),
            task_scope=task_scope,
            capability_reason=list(decision.reasons),
        )
    if decision.denied or not decision.allowed:
        log_event(
            "capability.denied",
            capability_requested=requested,
            capability_denied=list(decision.denied),
            missing_mandatory=list(decision.missing_mandatory),
            task_scope=task_scope,
            capability_reason=list(decision.reasons),
        )
    return decision


class CapabilityPolicyEngine:
    """Object facade over the functional policy core.

    Holds one `CapabilityPolicy` (catalog + explicit denials) and evaluates
    agent profiles, leases, and task requirements against it. Semantics are
    identical to `evaluate_policy`: explicit denials always win, mandatory
    requirements must all be effectively granted, and expired, exhausted, or
    out-of-scope leases never count as grants.
    """

    def __init__(self, policy: CapabilityPolicy) -> None:
        self.policy = policy
        self._implies = implication_map(policy.capabilities)

    def effective_closure(self, names: Iterable[str]) -> set[str]:
        """Transitively close `names` over the catalog's implication edges."""

        return downward_closure(names, self._implies)

    def evaluate(
        self,
        profile: AgentCapabilityProfile | None = None,
        requirements: Sequence[CapabilityRequirement] | None = None,
        leases: Sequence[CapabilityLease] = (),
        task_scope: str | None = None,
        now: datetime | None = None,
    ) -> PolicyDecision:
        """Evaluate an agent profile plus leases against task requirements.

        Profile grants behave as permanent leases (scoped when the grant
        carries a task scope). Profile denials union with policy denials.
        Requirements default to the profile's own requirements.
        """

        merged_leases = list(leases)
        merged_denied: list[str] = list(self.policy.denied)
        if profile is not None:
            for grant in profile.grants:
                merged_leases.append(
                    CapabilityLease(
                        capability=grant.capability,
                        allowed=True,
                        task_scope=grant.task_scope,
                        source=grant.source,
                    )
                )
            merged_denied.extend(profile.denials)
            if requirements is None:
                requirements = profile.requirements
        return evaluate_policy(
            self.policy.capabilities,
            requirements or (),
            merged_denied,
            merged_leases,
            task_scope,
            now,
        )
