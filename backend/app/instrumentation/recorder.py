"""Metrics recording for instrumented model calls.

A recorder keeps an in-memory list (for tests and live inspection), optionally
appends each record as one JSON object per line to a JSONL file (path typically
taken from `Settings.metrics_output_dir`), and forwards records to any extra
sinks (callables accepting `ModelCallMetrics`).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..ai.types import ModelResponse, TaskType, TokenUsage
from ..core.redaction import redact
from ..core.logging import log_event
from .models import ModelCallMetrics
from .pricing import DEFAULT_PRICING, PricingTable


class CallContext:
    """Handle yielded by `track_call`; the caller assigns the response."""

    def __init__(self) -> None:
        self.response: ModelResponse | None = None
        self.quality_score: float | None = None

    def set_response(self, response: ModelResponse) -> None:
        self.response = response

    def set_quality_score(self, score: float) -> None:
        self.quality_score = score


class MetricsRecorder:
    def __init__(
        self,
        sinks: list[Callable[[ModelCallMetrics], None]] | None = None,
        jsonl_path: str | Path | None = None,
        pricing: PricingTable | None = None,
    ) -> None:
        self._records: list[ModelCallMetrics] = []
        self._sinks = list(sinks or [])
        self._jsonl_path = Path(jsonl_path) if jsonl_path is not None else None
        self._pricing = pricing or DEFAULT_PRICING

    def add_sink(self, sink: Callable[[ModelCallMetrics], None]) -> None:
        """Forward each later record to `sink`. Used by execution traces."""

        self._sinks.append(sink)

    def record(self, metrics: ModelCallMetrics) -> None:
        self._records.append(metrics)
        if self._jsonl_path is not None:
            self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self._jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(metrics.to_dict(), default=str) + "\n")
        for sink in self._sinks:
            sink(metrics)

    def get_records(self) -> list[ModelCallMetrics]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()

    @asynccontextmanager
    async def track_call(
        self,
        model: str,
        agent: str,
        task_type: TaskType | str,
        metadata: dict[str, Any] | None = None,
        *,
        provider: str | None = None,
    ) -> AsyncIterator[CallContext]:
        """Time a model call, capture token usage, and record the outcome.

        On exception the failure is recorded with `success=False` and the
        original exception is re-raised. Prompts and call metadata are not
        written to the log.
        """
        task = task_type.value if isinstance(task_type, TaskType) else str(task_type)
        ctx = CallContext()
        started = time.perf_counter()
        timestamp = datetime.now(timezone.utc).isoformat()
        log_event(
            "model.call.started",
            model_name=model,
            agent_name=agent,
            task_type=task,
            provider=provider,
        )
        try:
            yield ctx
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            usage = ctx.response.usage if ctx.response is not None else TokenUsage()
            self.record(
                ModelCallMetrics(
                    timestamp=timestamp,
                    model_name=model,
                    agent_name=agent,
                    task_type=task,
                    provider=provider,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    latency_ms=latency_ms,
                    estimated_cost_usd=None,
                    success=False,
                    error=type(exc).__name__,
                    quality_score=ctx.quality_score,
                    metadata=redact(dict(metadata or {})),
                )
            )
            log_event(
                "model.call.failed",
                level=logging.ERROR,
                model_name=model,
                agent_name=agent,
                task_type=task,
                provider=provider,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                model_latency_ms=round(latency_ms, 3),
                success=False,
                exception_type=type(exc).__name__,
                error_type=type(exc).__name__,
            )
            raise
        latency_ms = (time.perf_counter() - started) * 1000.0
        usage = ctx.response.usage if ctx.response is not None else TokenUsage()
        cost = self._pricing.estimate_cost(model, usage.input_tokens, usage.output_tokens)
        self.record(
            ModelCallMetrics(
                timestamp=timestamp,
                model_name=model,
                agent_name=agent,
                task_type=task,
                provider=provider,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                latency_ms=latency_ms,
                estimated_cost_usd=cost,
                success=True,
                error=None,
                quality_score=ctx.quality_score,
                metadata=redact(dict(metadata or {})),
            )
        )
        log_event(
            "model.call.completed",
            model_name=model,
            agent_name=agent,
            task_type=task,
            provider=provider,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            estimated_cost=cost,
            model_latency_ms=round(latency_ms, 3),
            success=True,
        )
