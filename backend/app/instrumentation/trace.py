"""Auditable execution trace for one task.

Prompts, secrets, and environment values are never stored here: the builder
only accepts identifiers, counts, scores, and decision records — never
message or prompt content — and every metadata value is coerced to ``str``.
Any metadata key that looks secret-ish (contains key, token, secret,
password, credential, or env, case-insensitive) is replaced with
``"[REDACTED]"``. The spec-mandated patterns are the first five; ``env`` is
added deliberately because environment dumps commonly carry credentials.

`latency_ms` is wall-clock time from builder start to `finish`. The sum of
model-call latencies is stored separately in metadata as `model_latency_ms`.
`cost_usd` is the sum of known estimated costs, or None when any successful
call had no price. Partial sums are not reported as a total.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ..capabilities.models import PolicyDecision
from ..fallback.models import FallbackDecision
from ..optimization.models import OptimizationResult
from ..core.redaction import mask_secret_text
from .models import ModelCallMetrics

REDACTED = "[REDACTED]"
_SECRETISH_KEY = re.compile(r"key|token|secret|password|credential|env", re.IGNORECASE)

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    """Coerce values to ``str``; replace secret-ish keys with ``[REDACTED]``."""

    cleaned: dict[str, str] = {}
    for key, value in metadata.items():
        text_key = str(key)
        cleaned[mask_secret_text(text_key)] = (
            REDACTED if _SECRETISH_KEY.search(text_key) else mask_secret_text(str(value))
        )
    return cleaned


class ExecutionTrace(BaseModel):
    """The audit artifact for one task. All fields are metadata, never payloads."""

    task_id: str
    task_type: str
    selected_architecture: str | None = None
    agents_used: list[str] = Field(default_factory=list)
    models_used: list[str] = Field(default_factory=list)
    capability_grants: list[str] = Field(default_factory=list)
    capability_denials: list[str] = Field(default_factory=list)
    fallback_decisions: list[dict[str, Any]] = Field(default_factory=list)
    optimization_decision: dict[str, Any] | None = None
    latency_ms: float | None = None
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    quality_score: float | None = None
    risk_score: float | None = None
    policy_decisions: list[dict[str, Any]] = Field(default_factory=list)
    started_at: datetime
    ended_at: datetime | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ExecutionTraceBuilder:
    """Accumulates decisions and instrumented calls into an `ExecutionTrace`.

    Attach `observe_model_call` as a `MetricsRecorder` sink. Call metadata is
    not copied onto the trace. Use `set_metadata` for non-secret annotations;
    those values pass through `sanitize_metadata`.
    """

    def __init__(self, task_id: str, task_type: str, *, clock: Clock | None = None) -> None:
        self._clock = clock or _utc_now
        self._task_id = task_id
        self._task_type = task_type
        self._started = self._clock()
        self._finished: datetime | None = None
        self._architecture: str | None = None
        self._agents: list[str] = []
        self._models: list[str] = []
        self._grants: list[str] = []
        self._denials: list[str] = []
        self._fallbacks: list[dict[str, Any]] = []
        self._policies: list[dict[str, Any]] = []
        self._optimization: dict[str, Any] | None = None
        self._input_tokens = 0
        self._output_tokens = 0
        self._model_latency_ms = 0.0
        self._known_cost = 0.0
        self._cost_complete = True
        self._calls = 0
        self._quality: float | None = None
        self._risk: float | None = None
        self._metadata: dict[str, str] = {}

    def observe_model_call(self, metrics: ModelCallMetrics) -> None:
        """Fold one instrumented call into token, cost, and participant totals."""

        self._calls += 1
        if metrics.agent_name not in self._agents:
            self._agents.append(metrics.agent_name)
        if metrics.model_name not in self._models:
            self._models.append(metrics.model_name)
        self._input_tokens += metrics.input_tokens
        self._output_tokens += metrics.output_tokens
        self._model_latency_ms += metrics.latency_ms
        if metrics.success and metrics.estimated_cost_usd is not None:
            self._known_cost += metrics.estimated_cost_usd
        elif metrics.success:
            self._cost_complete = False

    def set_architecture(self, architecture_id: str | None) -> None:
        self._architecture = architecture_id

    def add_policy_decision(self, decision: PolicyDecision) -> None:
        self._policies.append(decision.to_dict())
        for name in decision.granted:
            if name not in self._grants:
                self._grants.append(name)
        for name in decision.denied:
            if name not in self._denials:
                self._denials.append(name)

    def add_fallback(self, decision: FallbackDecision) -> None:
        self._fallbacks.append(decision.to_dict())

    def add_optimization(self, result: OptimizationResult) -> None:
        """Store the optimizer result. Logging already happened inside selection."""

        self._optimization = result.to_dict()

    def set_quality_score(self, score: float | None) -> None:
        self._quality = score

    def set_risk_score(self, score: float | None) -> None:
        self._risk = score

    def set_metadata(self, metadata: dict[str, Any]) -> None:
        self._metadata = sanitize_metadata(metadata)

    def finish(self) -> ExecutionTrace:
        self._finished = self._clock()
        return self.build()

    def build(self) -> ExecutionTrace:
        latency_ms = None
        ended_at = None
        if self._finished is not None:
            latency_ms = (self._finished - self._started).total_seconds() * 1000.0
            ended_at = self._finished

        metadata = dict(self._metadata)
        metadata["model_latency_ms"] = str(self._model_latency_ms)
        metadata["model_calls"] = str(self._calls)
        metadata["cost_complete"] = str(self._cost_complete)

        if self._calls and self._cost_complete:
            cost_usd: float | None = self._known_cost
        else:
            cost_usd = None

        return ExecutionTrace(
            task_id=self._task_id,
            task_type=self._task_type,
            selected_architecture=self._architecture,
            agents_used=list(self._agents),
            models_used=list(self._models),
            capability_grants=list(self._grants),
            capability_denials=list(self._denials),
            fallback_decisions=list(self._fallbacks),
            optimization_decision=self._optimization,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            input_tokens=self._input_tokens if self._calls else None,
            output_tokens=self._output_tokens if self._calls else None,
            quality_score=self._quality,
            risk_score=self._risk,
            policy_decisions=list(self._policies),
            started_at=self._started,
            ended_at=ended_at,
            metadata=metadata,
        )
