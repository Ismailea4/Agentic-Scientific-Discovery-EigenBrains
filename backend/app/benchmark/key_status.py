"""Secret-free credential validation status records.

Credential values and value-derived identifiers are never fields on a record.
Only provider observations and the non-secret source kind are serializable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .artifacts import SecretScrubber, _write_json

class CredentialStatus(str, Enum):
    INVALID = "INVALID"
    VALID_AUTH = "VALID_AUTH"
    VALID_INFERENCE = "VALID_INFERENCE"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    BILLING_REQUIRED = "BILLING_REQUIRED"
    MODEL_NOT_ALLOWED = "MODEL_NOT_ALLOWED"
    NETWORK_ERROR = "NETWORK_ERROR"
    UNKNOWN = "UNKNOWN"

@dataclass(frozen=True)
class KeyStatusRecord:
    provider: str
    auth_status: CredentialStatus
    inference_status: CredentialStatus
    accessible_models: tuple[str, ...]
    rate_limit_status: str | None
    billing_or_quota_status: str | None
    tested_at: str
    notes: str = ""
    validation_latency_ms: float | None = None
    credential_source: str = "environment"

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider is required")
        if self.credential_source != "environment":
            raise ValueError("only environment-backed credentials are supported")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["auth_status"] = self.auth_status.value
        payload["inference_status"] = self.inference_status.value
        return payload


def classify_http_status(
    status_code: int,
    *,
    quota_exhausted: bool = False,
    model_not_allowed: bool = False,
) -> CredentialStatus:
    """Classify using status and already-redacted provider-specific signals."""

    if status_code in {200, 201, 204}:
        return CredentialStatus.VALID_AUTH
    if status_code == 401:
        return CredentialStatus.INVALID
    if status_code == 402:
        return CredentialStatus.BILLING_REQUIRED
    if status_code == 429:
        return CredentialStatus.QUOTA_EXHAUSTED if quota_exhausted else CredentialStatus.RATE_LIMITED
    if status_code == 403 and model_not_allowed:
        return CredentialStatus.MODEL_NOT_ALLOWED
    return CredentialStatus.UNKNOWN


def write_key_status_inventory(
    path: str | Path,
    records: list[KeyStatusRecord],
    *,
    scrubber: SecretScrubber | None = None,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "credential_count": len(records),
        "credentials": [record.to_dict() for record in records],
    }
    _write_json(destination, payload, scrubber or SecretScrubber.from_environment())
    return destination
