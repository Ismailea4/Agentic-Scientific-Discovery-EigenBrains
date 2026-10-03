"""Challenge-agnostic capability types and least-privilege policy checks.

Security decisions produced here are hard constraints. An optimizer may
choose among architectures that already satisfy a `PolicyDecision`; it must
not relax grants, denials, or leases.
"""

from .models import (
    AgentCapabilityProfile,
    Capability,
    CapabilityGrant,
    CapabilityLease,
    CapabilityPolicy,
    CapabilityRequirement,
    PolicyDecision,
)
from .policy import CapabilityPolicyEngine, evaluate_policy

__all__ = [
    "AgentCapabilityProfile",
    "Capability",
    "CapabilityGrant",
    "CapabilityLease",
    "CapabilityPolicy",
    "CapabilityPolicyEngine",
    "CapabilityRequirement",
    "PolicyDecision",
    "evaluate_policy",
]
