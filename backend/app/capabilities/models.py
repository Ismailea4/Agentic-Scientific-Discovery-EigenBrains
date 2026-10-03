"""Typed capability model (pydantic v2).

Nothing here names a challenge, a provider, or a real agent. Callers supply
capability names when the challenge is known.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class Capability(BaseModel):
    """A named capability. `implies` lists weaker capabilities it inherits."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str | None = None
    implies: tuple[str, ...] = ()


class CapabilityGrant(BaseModel):
    """A recorded grant. `source` is an audit label, not a secret."""

    model_config = ConfigDict(frozen=True)

    capability: str
    source: str = "profile"
    task_scope: str | None = None


class CapabilityRequirement(BaseModel):
    model_config = ConfigDict(frozen=True)

    capability: str
    mandatory: bool = True


class AgentCapabilityProfile(BaseModel):
    """Capabilities an agent holds before lease and policy filtering."""

    model_config = ConfigDict(frozen=True)

    agent_name: str
    grants: tuple[CapabilityGrant, ...] = ()
    denials: tuple[str, ...] = ()
    requirements: tuple[CapabilityRequirement, ...] = ()


class CapabilityPolicy(BaseModel):
    """Catalog of known capabilities plus the explicit denial set.

    Denials are hard constraints: they are never traded away by an optimizer.
    """

    model_config = ConfigDict(frozen=True)

    capabilities: tuple[Capability, ...] = ()
    denied: frozenset[str] = frozenset()


class CapabilityLease(BaseModel):
    """A scoped, expiring, call-limited authorization for one capability.

    `allowed=False` is an explicit denial for the lease's task scope. A lease
    with `task_scope=None` applies to every task; a scoped lease applies only
    when the task scope matches. `consume()` mutates `calls_used`, so this
    model is deliberately not frozen.
    """

    capability: str
    allowed: bool = True
    task_scope: str | None = None
    expires_at: datetime | None = None
    max_calls: int | None = None
    calls_used: int = 0
    source: str = ""
    reason: str = ""

    def is_valid(self, now: datetime | None = None, task_scope: str | None = None) -> bool:
        """True when the lease currently authorizes `task_scope`.

        A lease is valid only when it allows, is unexpired, matches the task
        scope (an unscoped lease matches everything), and has calls remaining.
        """

        moment = _as_utc(now or _utc_now())
        if not self.allowed:
            return False
        if self.task_scope is not None and self.task_scope != task_scope:
            return False
        if self.expires_at is not None and moment >= _as_utc(self.expires_at):
            return False
        if self.max_calls is not None and self.calls_used >= self.max_calls:
            return False
        return True

    def consume(self) -> None:
        """Record one authorized call. Raises when the lease is exhausted."""

        if self.max_calls is not None and self.calls_used >= self.max_calls:
            raise ValueError(f"lease for '{self.capability}' has reached max_calls")
        self.calls_used += 1


class PolicyDecision(BaseModel):
    """Auditable result of a policy evaluation.

    `granted` is the effective closure (direct grants plus inherited
    capabilities, minus denials). `denied` is the denial closure. The two
    sets are disjoint.
    """

    model_config = ConfigDict(frozen=True)

    allowed: bool
    granted: tuple[str, ...]
    denied: tuple[str, ...]
    missing_mandatory: tuple[str, ...]
    missing_optional: tuple[str, ...]
    reasons: tuple[str, ...]
    timestamp: datetime = Field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "granted": list(self.granted),
            "denied": list(self.denied),
            "missing_mandatory": list(self.missing_mandatory),
            "missing_optional": list(self.missing_optional),
            "reasons": list(self.reasons),
            "timestamp": self.timestamp.isoformat(),
        }
