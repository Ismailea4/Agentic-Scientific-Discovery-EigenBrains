"""Data model for a single instrumented model call."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..core.redaction import redact


@dataclass
class ModelCallMetrics:
    timestamp: str
    model_name: str
    agent_name: str
    task_type: str
    provider: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    estimated_cost_usd: float | None = None
    success: bool = True
    error: str | None = None
    quality_score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return redact(asdict(self))
