from datetime import datetime, timedelta, timezone

import pytest

from app.capabilities import (
    AgentCapabilityProfile,
    Capability,
    CapabilityGrant,
    CapabilityLease,
    CapabilityPolicy,
    CapabilityPolicyEngine,
    CapabilityRequirement,
    evaluate_policy,
)


def _lease(capability: str, **kwargs) -> CapabilityLease:
    return CapabilityLease(capability=capability, allowed=True, source="test", **kwargs)


def test_inheritance_closes_over_implied_capabilities():
    catalogue = [
        Capability(name="read"),
        Capability(name="draft", implies=("read",)),
        Capability(name="review", implies=("draft",)),
    ]
    decision = evaluate_policy(
        catalogue,
        [CapabilityRequirement(capability="read")],
        denied=[],
        leases=[_lease("review")],
        task_scope=None,
    )

    assert decision.allowed is True
    assert decision.granted == ("draft", "read", "review")
    assert decision.missing_mandatory == ()
    assert set(decision.granted).isdisjoint(decision.denied)
    assert decision.timestamp is not None


def test_denial_removes_stronger_capabilities_that_imply_it():
    catalogue = [Capability(name="admin", implies=("read", "write"))]
    decision = evaluate_policy(
        catalogue,
        [CapabilityRequirement(capability="admin"), CapabilityRequirement(capability="write")],
        denied=["read"],
        leases=[_lease("admin"), _lease("write")],
        task_scope=None,
    )

    assert decision.allowed is False
    assert "admin" in decision.denied
    assert "read" in decision.denied
    assert "write" in decision.granted
    assert decision.missing_mandatory == ("admin",)


def test_missing_mandatory_capability_is_reported_and_blocks():
    decision = evaluate_policy(
        [Capability(name="export")],
        [
            CapabilityRequirement(capability="export"),
            CapabilityRequirement(capability="read", mandatory=False),
        ],
        denied=[],
        leases=[],
        task_scope="task",
    )

    assert decision.allowed is False
    assert decision.missing_mandatory == ("export",)
    assert decision.missing_optional == ("read",)
    assert any("missing mandatory capability 'export'" in reason for reason in decision.reasons)


def test_optional_gap_does_not_block_when_mandatory_capabilities_hold():
    decision = evaluate_policy(
        [Capability(name="read")],
        [
            CapabilityRequirement(capability="read"),
            CapabilityRequirement(capability="export", mandatory=False),
        ],
        denied=[],
        leases=[_lease("read")],
        task_scope=None,
    )

    assert decision.allowed is True
    assert decision.missing_optional == ("export",)
    assert decision.missing_mandatory == ()


def test_scoped_lease_applies_only_to_its_task():
    catalogue = [Capability(name="read")]
    leases = [_lease("read", task_scope="alpha")]
    requirements = [CapabilityRequirement(capability="read")]

    outside = evaluate_policy(catalogue, requirements, [], leases, task_scope="beta")
    inside = evaluate_policy(catalogue, requirements, [], leases, task_scope="alpha")
    unscoped = evaluate_policy(catalogue, requirements, [], leases, task_scope=None)

    assert outside.allowed is False
    assert "read" not in outside.granted
    assert any("scoped to 'alpha'" in reason for reason in outside.reasons)
    assert inside.allowed is True
    assert inside.granted == ("read",)
    assert unscoped.allowed is False


def test_expired_or_exhausted_lease_does_not_grant():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    catalogue = [Capability(name="read")]
    requirements = [CapabilityRequirement(capability="read")]

    expired = evaluate_policy(
        catalogue,
        requirements,
        [],
        [_lease("read", expires_at=now - timedelta(seconds=1))],
        task_scope=None,
        now=now,
    )
    exhausted = evaluate_policy(
        catalogue,
        requirements,
        [],
        [_lease("read", max_calls=2, calls_used=2)],
        task_scope=None,
        now=now,
    )
    still_open = evaluate_policy(
        catalogue,
        requirements,
        [],
        [_lease("read", max_calls=2, calls_used=1, expires_at=now + timedelta(seconds=5))],
        task_scope=None,
        now=now,
    )

    assert expired.allowed is False
    assert any("expired" in reason for reason in expired.reasons)
    assert exhausted.allowed is False
    assert any("max_calls" in reason for reason in exhausted.reasons)
    assert still_open.allowed is True


def test_active_denial_beats_an_allowing_lease():
    decision = evaluate_policy(
        [Capability(name="export")],
        [CapabilityRequirement(capability="export")],
        denied=[],
        leases=[
            _lease("export"),
            CapabilityLease(capability="export", allowed=False, source="policy"),
        ],
        task_scope=None,
    )

    assert decision.allowed is False
    assert "export" in decision.denied
    assert "export" not in decision.granted


def test_expired_denial_does_not_outlive_its_lease():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    decision = evaluate_policy(
        [Capability(name="export")],
        [CapabilityRequirement(capability="export")],
        denied=[],
        leases=[
            _lease("export"),
            CapabilityLease(
                capability="export",
                allowed=False,
                expires_at=now - timedelta(seconds=1),
                source="old-policy",
            ),
        ],
        task_scope=None,
        now=now,
    )

    assert decision.allowed is True
    assert decision.granted == ("export",)


def test_implication_cycle_terminates():
    catalogue = [
        Capability(name="alpha", implies=("beta",)),
        Capability(name="beta", implies=("alpha",)),
    ]
    decision = evaluate_policy(
        catalogue,
        [CapabilityRequirement(capability="beta")],
        denied=[],
        leases=[_lease("alpha")],
        task_scope=None,
    )

    assert decision.allowed is True
    assert decision.granted == ("alpha", "beta")


def test_lease_is_valid_checks_scope_expiry_and_calls():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lease = CapabilityLease(
        capability="read", allowed=True, task_scope="alpha", max_calls=2,
        expires_at=now + timedelta(seconds=5),
    )

    assert lease.is_valid(now, "alpha") is True
    assert lease.is_valid(now, "beta") is False
    assert lease.is_valid(now + timedelta(seconds=10), "alpha") is False

    lease.consume()
    lease.consume()
    assert lease.calls_used == 2
    assert lease.is_valid(now, "alpha") is False
    with pytest.raises(ValueError, match="max_calls"):
        lease.consume()

    denied = CapabilityLease(capability="read", allowed=False)
    assert denied.is_valid() is False


def test_engine_combines_policy_profile_and_leases():
    policy = CapabilityPolicy(
        capabilities=(
            Capability(name="read"),
            Capability(name="draft", implies=("read",)),
            Capability(name="export"),
        ),
        denied=frozenset({"export"}),
    )
    engine = CapabilityPolicyEngine(policy)
    profile = AgentCapabilityProfile(
        agent_name="writer",
        grants=(CapabilityGrant(capability="draft", source="profile"),),
        requirements=(
            CapabilityRequirement(capability="read"),
            CapabilityRequirement(capability="export"),
        ),
    )

    decision = engine.evaluate(profile, task_scope=None)

    assert engine.effective_closure(["draft"]) == {"draft", "read"}
    assert decision.allowed is False
    assert "read" in decision.granted
    assert "export" in decision.denied
    assert decision.missing_mandatory == ("export",)
    assert any("denied" in reason for reason in decision.reasons)


def test_engine_profile_denial_beats_lease_grant():
    policy = CapabilityPolicy(capabilities=(Capability(name="read"),))
    engine = CapabilityPolicyEngine(policy)
    profile = AgentCapabilityProfile(agent_name="reader", denials=("read",))

    decision = engine.evaluate(
        profile,
        requirements=[CapabilityRequirement(capability="read")],
        leases=[_lease("read")],
        task_scope=None,
    )

    assert decision.allowed is False
    assert "read" in decision.denied
    assert "read" not in decision.granted
