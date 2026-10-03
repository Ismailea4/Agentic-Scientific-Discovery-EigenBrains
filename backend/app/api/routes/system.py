"""Generic inspection routes.

GET catalogues read the in-memory registries and are empty until something
registers. POST routes compute over the caller's payload. None of them
invent metrics, grants, or architectures.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ...capabilities.models import Capability, CapabilityLease, CapabilityRequirement
from ...capabilities.policy import evaluate_policy
from ...core.errors import ValidationError
from ...fallback.models import FallbackCandidate, FallbackPolicy
from ...fallback.resolver import resolve_fallback
from ...optimization.models import ArchitectureCandidate, ArchitectureMetrics
from ...optimization.pareto import log_pareto_result, pareto_frontier

router = APIRouter(prefix="/system", tags=["system"])


class CapabilityDescriptorModel(BaseModel):
    name: str
    description: str | None = None
    implies: list[str] = Field(default_factory=list)


class CapabilitiesResponse(BaseModel):
    capabilities: list[CapabilityDescriptorModel]


class ArchitectureModel(BaseModel):
    id: str
    name: str
    quality: float
    cost: float
    latency: float
    risk: float
    metadata: dict[str, Any] | None = None


class ArchitecturesResponse(BaseModel):
    architectures: list[ArchitectureModel]


class ParetoCandidateModel(BaseModel):
    id: str
    quality: float
    cost: float
    latency: float
    risk: float
    metadata: dict[str, Any] | None = None


class ParetoFrontierRequest(BaseModel):
    candidates: list[ParetoCandidateModel]


class ParetoFrontierResponse(BaseModel):
    frontier: list[str]
    dominated: list[str]


class PolicyRequirementModel(BaseModel):
    capability: str
    mandatory: bool = True


class CapabilityLeaseModel(BaseModel):
    capability: str
    allowed: bool
    task_scope: str | None = None
    expires_at: str | None = None
    max_calls: int | None = None
    calls_used: int = 0
    source: str = ""


class EvaluatePolicyRequest(BaseModel):
    capabilities: list[CapabilityDescriptorModel] = Field(default_factory=list)
    requirements: list[PolicyRequirementModel] = Field(default_factory=list)
    denied: list[str] = Field(default_factory=list)
    leases: list[CapabilityLeaseModel] = Field(default_factory=list)
    task_scope: str | None = None


class PolicyEvaluationResponse(BaseModel):
    allowed: bool
    granted: list[str]
    denied: list[str]
    missing_mandatory: list[str]
    missing_optional: list[str]
    reasons: list[str]


class FallbackCandidateModel(BaseModel):
    id: str
    available: bool
    capabilities: list[str]
    privacy_class: str
    allowed_tasks: list[str]


class ResolveFallbackRequest(BaseModel):
    candidates: list[FallbackCandidateModel]
    mandatory_capabilities: list[str]
    accepted_privacy_classes: list[str]
    task: str
    preference_order: list[str]
    capabilities: list[CapabilityDescriptorModel] = Field(default_factory=list)


class FallbackRejectionModel(BaseModel):
    id: str
    reason: str


class FallbackDecisionResponse(BaseModel):
    selected_id: str | None
    considered: list[str]
    rejected: list[FallbackRejectionModel]
    reason: str


def _catalogue(items: list[CapabilityDescriptorModel]) -> list[Capability]:
    names = [item.name for item in items]
    if len(names) != len(set(names)):
        raise ValidationError("capability names must be unique")
    return [
        Capability(name=item.name, description=item.description, implies=tuple(item.implies))
        for item in items
    ]


def _parse_lease_expiry(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(
            "expires_at must be an ISO-8601 timestamp",
            details={"expires_at": raw},
        ) from exc


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def list_capabilities(request: Request) -> CapabilitiesResponse:
    items = [
        CapabilityDescriptorModel(
            name=capability.name,
            description=capability.description,
            implies=list(capability.implies),
        )
        for capability in request.app.state.capabilities.list()
    ]
    return CapabilitiesResponse(capabilities=items)


@router.get("/architectures", response_model=ArchitecturesResponse)
async def list_architectures(request: Request) -> ArchitecturesResponse:
    rows = []
    for candidate in request.app.state.architectures.list():
        rows.append(
            ArchitectureModel(
                id=candidate.id,
                name=candidate.name,
                quality=candidate.metrics.quality,
                cost=candidate.metrics.cost,
                latency=candidate.metrics.latency,
                risk=candidate.metrics.risk,
                metadata=candidate.metadata or None,
            )
        )
    return ArchitecturesResponse(architectures=rows)


@router.post("/pareto-frontier", response_model=ParetoFrontierResponse)
async def classify_pareto(body: ParetoFrontierRequest) -> ParetoFrontierResponse:
    candidates = [
        ArchitectureCandidate(
            id=item.id,
            name=item.id,
            metrics=ArchitectureMetrics(
                quality=item.quality,
                cost=item.cost,
                latency=item.latency,
                risk=item.risk,
            ),
            metadata=dict(item.metadata or {}),
        )
        for item in body.candidates
    ]
    try:
        result = pareto_frontier(candidates)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    log_pareto_result(result)
    return ParetoFrontierResponse(frontier=list(result.frontier), dominated=list(result.dominated))


@router.post("/evaluate-policy", response_model=PolicyEvaluationResponse)
async def evaluate_policy_route(body: EvaluatePolicyRequest) -> PolicyEvaluationResponse:
    catalogue = _catalogue(body.capabilities)
    leases = [
        CapabilityLease(
            capability=lease.capability,
            allowed=lease.allowed,
            task_scope=lease.task_scope,
            expires_at=_parse_lease_expiry(lease.expires_at),
            max_calls=lease.max_calls,
            calls_used=lease.calls_used,
            source=lease.source,
        )
        for lease in body.leases
    ]
    decision = evaluate_policy(
        catalogue,
        [
            CapabilityRequirement(capability=item.capability, mandatory=item.mandatory)
            for item in body.requirements
        ],
        body.denied,
        leases,
        body.task_scope,
    )
    return PolicyEvaluationResponse(**decision.to_dict())


@router.post("/resolve-fallback", response_model=FallbackDecisionResponse)
async def resolve_fallback_route(body: ResolveFallbackRequest) -> FallbackDecisionResponse:
    catalogue = _catalogue(body.capabilities)
    candidates = [
        FallbackCandidate(
            id=item.id,
            available=item.available,
            capabilities=tuple(item.capabilities),
            privacy_class=item.privacy_class,
            allowed_tasks=tuple(item.allowed_tasks),
        )
        for item in body.candidates
    ]
    policy = FallbackPolicy(
        mandatory_capabilities=tuple(body.mandatory_capabilities),
        accepted_privacy_classes=tuple(body.accepted_privacy_classes),
        task=body.task,
        preference_order=tuple(body.preference_order),
    )
    try:
        decision = resolve_fallback(candidates, policy, catalogue)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    payload = decision.to_dict()
    return FallbackDecisionResponse(
        selected_id=payload["selected_id"],
        considered=payload["considered"],
        rejected=[FallbackRejectionModel(**row) for row in payload["rejected"]],
        reason=payload["reason"],
    )
