"""Fallback records. Task allow-lists are explicit; nothing is allowed by default."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FallbackCandidate(BaseModel):
    """One fallback option. `ref` identifies the agent/architecture it runs."""

    model_config = ConfigDict(frozen=True)

    id: str
    available: bool
    capabilities: tuple[str, ...]
    privacy_class: str
    allowed_tasks: tuple[str, ...]
    ref: str | None = None


class FallbackPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    mandatory_capabilities: tuple[str, ...]
    accepted_privacy_classes: tuple[str, ...]
    task: str
    preference_order: tuple[str, ...]


class FallbackDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    selected_id: str | None
    considered: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]
    reason: str
    timestamp: datetime = Field(default_factory=_utc_now)
    deterministic: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_id": self.selected_id,
            "considered": list(self.considered),
            "rejected": [
                {"id": identifier, "reason": why} for identifier, why in self.rejected
            ],
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "deterministic": self.deterministic,
        }
