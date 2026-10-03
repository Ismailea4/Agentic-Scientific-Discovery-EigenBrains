"""Explicit cost/call/concurrency limits and pilot projections."""

from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from statistics import fmean
from typing import Any, AsyncIterator, Sequence

from .models import BenchmarkRun


class BenchmarkLimitError(RuntimeError):
    pass


@dataclass(frozen=True)
class BenchmarkLimits:
    max_benchmark_spend_usd: float | None
    max_total_calls: int | None
    max_calls_per_model: int | None
    max_concurrency: int
    max_provider_requests: int | None = None

    @classmethod
    def from_environment(cls) -> "BenchmarkLimits":
        def optional_float(name: str) -> float | None:
            raw = os.getenv(name)
            return None if raw is None or not raw.strip() else float(raw)

        def optional_int(name: str) -> int | None:
            raw = os.getenv(name)
            return None if raw is None or not raw.strip() else int(raw)

        limits = cls(
            max_benchmark_spend_usd=optional_float("MAX_BENCHMARK_SPEND_USD"),
            max_total_calls=(
                optional_int("MAX_TOTAL_INFERENCE_CALLS")
                if os.getenv("MAX_TOTAL_INFERENCE_CALLS") is not None
                else optional_int("MAX_TOTAL_CALLS")
            ),
            max_calls_per_model=optional_int("MAX_CALLS_PER_MODEL"),
            max_concurrency=int(os.getenv("MAX_CONCURRENCY", "1")),
            max_provider_requests=optional_int("MAX_PROVIDER_REQUESTS"),
        )
        limits.validate()
        return limits

    def validate(self) -> None:
        if self.max_benchmark_spend_usd is not None and self.max_benchmark_spend_usd < 0:
            raise ValueError("MAX_BENCHMARK_SPEND_USD must be >= 0")
        for name in (
            "max_total_calls",
            "max_calls_per_model",
            "max_concurrency",
            "max_provider_requests",
        ):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} must be >= 1")


@dataclass(frozen=True)
class ModelProjection:
    provider: str
    model: str
    projected_calls: int
    projected_input_tokens: int
    projected_output_tokens: int
    projected_cost_usd: float | None
    projected_runtime_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def project_full_benchmark(
    pilot_runs: Sequence[BenchmarkRun],
    *,
    target_calls_per_model: int,
) -> list[ModelProjection]:
    if not pilot_runs:
        raise ValueError("a non-empty pilot is required")
    if target_calls_per_model < 1:
        raise ValueError("target_calls_per_model must be >= 1")
    grouped: dict[tuple[str, str], list[BenchmarkRun]] = defaultdict(list)
    for run in pilot_runs:
        grouped[(run.provider, run.model)].append(run)
    projections: list[ModelProjection] = []
    for (provider, model), runs in sorted(grouped.items()):
        scale = target_calls_per_model
        known_costs = [run.estimated_cost_usd for run in runs]
        cost = None if any(value is None for value in known_costs) else fmean(float(value) for value in known_costs) * scale
        projections.append(
            ModelProjection(
                provider=provider,
                model=model,
                projected_calls=scale,
                projected_input_tokens=round(fmean(run.input_tokens for run in runs) * scale),
                projected_output_tokens=round(fmean(run.output_tokens for run in runs) * scale),
                projected_cost_usd=cost,
                projected_runtime_seconds=fmean(run.latency_ms for run in runs) * scale / 1000.0,
            )
        )
    return projections


def authorize_projection(projections: Sequence[ModelProjection], limits: BenchmarkLimits) -> None:
    limits.validate()
    if limits.max_benchmark_spend_usd is None:
        raise BenchmarkLimitError("MAX_BENCHMARK_SPEND_USD is required before a benchmark run")
    if any(item.projected_cost_usd is None for item in projections):
        raise BenchmarkLimitError("projected cost is unknown for at least one model")
    total_cost = sum(float(item.projected_cost_usd) for item in projections)
    total_calls = sum(item.projected_calls for item in projections)
    if total_cost > limits.max_benchmark_spend_usd:
        raise BenchmarkLimitError("projected benchmark cost exceeds the configured spend limit")
    if limits.max_total_calls is not None and total_calls > limits.max_total_calls:
        raise BenchmarkLimitError("projected benchmark calls exceed MAX_TOTAL_CALLS")
    if limits.max_provider_requests is not None and total_calls > limits.max_provider_requests:
        raise BenchmarkLimitError("projected benchmark calls exceed MAX_PROVIDER_REQUESTS")
    if limits.max_calls_per_model is not None and any(
        item.projected_calls > limits.max_calls_per_model for item in projections
    ):
        raise BenchmarkLimitError("projected calls exceed MAX_CALLS_PER_MODEL")


class BudgetController:
    """Conservative pre-call accounting with bounded async concurrency."""

    def __init__(self, limits: BenchmarkLimits) -> None:
        limits.validate()
        self.limits = limits
        self._semaphore = asyncio.Semaphore(limits.max_concurrency)
        self._lock = asyncio.Lock()
        self._calls = 0
        self._provider_requests = 0
        self._spend = 0.0
        self._per_model: dict[str, int] = defaultdict(int)

    @asynccontextmanager
    async def slot(self, model: str, *, projected_cost_usd: float | None) -> AsyncIterator[None]:
        if self.limits.max_benchmark_spend_usd is None:
            raise BenchmarkLimitError("MAX_BENCHMARK_SPEND_USD is required before provider calls")
        if projected_cost_usd is None:
            raise BenchmarkLimitError("a checked projected cost is required before provider calls")
        async with self._semaphore:
            async with self._lock:
                next_calls = self._calls + 1
                next_provider_requests = self._provider_requests + 1
                next_model_calls = self._per_model[model] + 1
                next_spend = self._spend + projected_cost_usd
                if self.limits.max_total_calls is not None and next_calls > self.limits.max_total_calls:
                    raise BenchmarkLimitError("MAX_TOTAL_CALLS reached")
                if (
                    self.limits.max_provider_requests is not None
                    and next_provider_requests > self.limits.max_provider_requests
                ):
                    raise BenchmarkLimitError("MAX_PROVIDER_REQUESTS reached")
                if self.limits.max_calls_per_model is not None and next_model_calls > self.limits.max_calls_per_model:
                    raise BenchmarkLimitError("MAX_CALLS_PER_MODEL reached")
                if next_spend > self.limits.max_benchmark_spend_usd:
                    raise BenchmarkLimitError("MAX_BENCHMARK_SPEND_USD reached")
                self._calls = next_calls
                self._provider_requests = next_provider_requests
                self._per_model[model] = next_model_calls
                self._spend = next_spend
            yield

    def snapshot(self) -> dict[str, Any]:
        """Return non-secret conservative reservation totals."""

        return {
            "inference_calls": self._calls,
            "provider_requests": self._provider_requests,
            "reserved_spend_usd": self._spend,
            "calls_per_model": dict(sorted(self._per_model.items())),
        }
