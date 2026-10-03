"""Provider-neutral, minimal credential validation orchestration.

Provider-specific probes implement the official requests. This module never
logs credentials or response bodies and performs at most one inference probe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .key_status import CredentialStatus, KeyStatusRecord, classify_http_status


@dataclass(frozen=True)
class ProbeObservation:
    status_code: int | None
    latency_ms: float
    accessible_models: tuple[str, ...] = ()
    succeeded: bool = False
    quota_exhausted: bool = False
    model_not_allowed: bool = False


class CredentialProbe(Protocol):
    provider: str

    async def authenticate(self, credential: str) -> ProbeObservation: ...

    async def tiny_inference(self, credential: str, model: str) -> ProbeObservation: ...


def _status(observation: ProbeObservation) -> CredentialStatus:
    if observation.status_code is None:
        return CredentialStatus.NETWORK_ERROR
    return classify_http_status(
        observation.status_code,
        quota_exhausted=observation.quota_exhausted,
        model_not_allowed=observation.model_not_allowed,
    )


async def validate_labeled_credential(
    credential: str,
    probe: CredentialProbe,
    *,
    relevant_models: tuple[str, ...] = (),
) -> KeyStatusRecord:
    """Authenticate, select an accessible model, make one tiny call, and stop."""

    tested_at = datetime.now(timezone.utc).isoformat()
    try:
        authentication = await probe.authenticate(credential)
    except (TimeoutError, OSError):
        return KeyStatusRecord(
            probe.provider, CredentialStatus.NETWORK_ERROR,
            CredentialStatus.NETWORK_ERROR, (), None, None, tested_at,
            notes="authentication probe encountered a network error",
        )
    auth_status = _status(authentication)
    models = tuple(sorted(set(authentication.accessible_models)))
    if auth_status is not CredentialStatus.VALID_AUTH:
        return KeyStatusRecord(
            probe.provider, auth_status, CredentialStatus.UNKNOWN,
            models, auth_status.value if auth_status is CredentialStatus.RATE_LIMITED else None,
            auth_status.value if auth_status in {CredentialStatus.QUOTA_EXHAUSTED, CredentialStatus.BILLING_REQUIRED} else None,
            tested_at,
        )
    eligible = [model for model in relevant_models if model in models] if relevant_models else list(models)
    if not eligible:
        return KeyStatusRecord(
            probe.provider, CredentialStatus.VALID_AUTH,
            CredentialStatus.MODEL_NOT_ALLOWED, models, None, None, tested_at,
            notes="authentication succeeded but no relevant accessible model was identified",
        )
    try:
        inference = await probe.tiny_inference(credential, eligible[0])
    except (TimeoutError, OSError):
        inference_status = CredentialStatus.NETWORK_ERROR
        latency = None
    else:
        inference_status = CredentialStatus.VALID_INFERENCE if inference.succeeded else _status(inference)
        latency = inference.latency_ms
    return KeyStatusRecord(
        provider=probe.provider,
        auth_status=CredentialStatus.VALID_AUTH,
        inference_status=inference_status,
        accessible_models=models,
        rate_limit_status=(inference_status.value if inference_status is CredentialStatus.RATE_LIMITED else None),
        billing_or_quota_status=(
            inference_status.value
            if inference_status in {CredentialStatus.QUOTA_EXHAUSTED, CredentialStatus.BILLING_REQUIRED}
            else None
        ),
        tested_at=tested_at,
        validation_latency_ms=latency,
    )
