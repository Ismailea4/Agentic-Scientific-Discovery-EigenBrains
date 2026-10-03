import pytest

from app.capabilities import Capability
from app.fallback import FallbackCandidate, FallbackPolicy, resolve_fallback


def _policy(**kwargs) -> FallbackPolicy:
    base = dict(
        mandatory_capabilities=("read",),
        accepted_privacy_classes=("restricted",),
        task="review",
        preference_order=("primary", "local", "open-model"),
    )
    base.update(kwargs)
    return FallbackPolicy(**base)


def test_fallback_skips_unavailable_and_underprivileged_candidates():
    catalogue = [Capability(name="draft", implies=("read",))]
    decision = resolve_fallback(
        [
            FallbackCandidate(
                id="primary",
                available=False,
                capabilities=("read",),
                privacy_class="restricted",
                allowed_tasks=("review",),
            ),
            FallbackCandidate(
                id="open-model",
                available=True,
                capabilities=("draft",),
                privacy_class="public",
                allowed_tasks=("review",),
            ),
            FallbackCandidate(
                id="local",
                available=True,
                capabilities=("read",),
                privacy_class="restricted",
                allowed_tasks=("review",),
            ),
        ],
        _policy(),
        catalogue,
    )

    assert decision.selected_id == "local"
    assert decision.rejected == (
        ("open-model", "privacy class 'public' is not accepted"),
        ("primary", "unavailable"),
    )
    assert "first preference-order" in decision.reason


def test_fallback_rejects_wrong_task_even_if_it_is_first_preference():
    decision = resolve_fallback(
        [
            FallbackCandidate(
                id="primary",
                available=True,
                capabilities=("read",),
                privacy_class="restricted",
                allowed_tasks=("other",),
            )
        ],
        _policy(preference_order=("primary",)),
    )

    assert decision.selected_id is None
    assert decision.rejected == (("primary", "task 'review' is not allowed"),)
    assert "no candidate satisfied" in decision.reason


def test_fallback_decision_carries_audit_metadata():
    decision = resolve_fallback(
        [
            FallbackCandidate(
                id="local",
                available=True,
                capabilities=("read",),
                privacy_class="restricted",
                allowed_tasks=("review",),
            )
        ],
        _policy(preference_order=("local",)),
    )

    assert decision.deterministic is True
    assert decision.timestamp is not None
    assert decision.to_dict()["timestamp"] == decision.timestamp.isoformat()


def test_fallback_does_not_select_an_eligible_candidate_outside_preference_order():
    decision = resolve_fallback(
        [
            FallbackCandidate(
                id="extra",
                available=True,
                capabilities=("read",),
                privacy_class="restricted",
                allowed_tasks=("review",),
            )
        ],
        _policy(preference_order=("missing",)),
    )

    assert decision.selected_id is None
    assert ("extra", "not in preference order") in decision.rejected
    assert ("missing", "not a known candidate") in decision.rejected


def test_inherited_capability_satisfies_a_mandatory_requirement():
    decision = resolve_fallback(
        [
            FallbackCandidate(
                id="local",
                available=True,
                capabilities=("draft",),
                privacy_class="restricted",
                allowed_tasks=("review",),
            )
        ],
        _policy(preference_order=("local",)),
        [Capability(name="draft", implies=("read",))],
    )

    assert decision.selected_id == "local"
    assert decision.rejected == ()


def test_duplicate_fallback_ids_are_rejected():
    candidate = FallbackCandidate(
        id="local",
        available=True,
        capabilities=("read",),
        privacy_class="restricted",
        allowed_tasks=("review",),
    )
    with pytest.raises(ValueError, match="unique"):
        resolve_fallback([candidate, candidate], _policy(preference_order=("local",)))
