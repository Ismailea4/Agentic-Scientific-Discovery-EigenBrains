"""Normalize provider calls without exposing request payloads or credentials."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from ..ai.provider import AIProvider
from ..ai.types import Message, TaskType
from ..instrumentation.pricing import PricingTable


@dataclass(frozen=True)
class NormalizedProviderCall:
    provider: str
    model: str
    task_type: str
    output: str | None
    success: bool
    error_type: str | None
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def invoke_normalized(
    provider: AIProvider,
    messages: list[Message],
    *,
    task_type: TaskType | str,
    pricing: PricingTable | None = None,
    **kwargs: Any,
) -> NormalizedProviderCall:
    """Call a provider and normalize success or failure into one safe record.

    Exception messages are deliberately not copied into the result because an
    upstream SDK may echo request headers. Operational logging already applies
    the central redaction layer.
    """

    started = time.perf_counter()
    task = task_type.value if isinstance(task_type, TaskType) else str(task_type)
    provider_name = provider.name
    configured_model = str(getattr(provider, "model", provider_name))
    try:
        response = await provider.generate(messages, **kwargs)
    except Exception as exc:
        return NormalizedProviderCall(
            provider=provider_name,
            model=configured_model,
            task_type=task,
            output=None,
            success=False,
            error_type=type(exc).__name__,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=None,
        )

    cost = None
    if pricing is not None:
        cost = pricing.estimate_cost(
            response.model,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
    return NormalizedProviderCall(
        provider=provider_name,
        model=response.model,
        task_type=task,
        output=response.content,
        success=True,
        error_type=None,
        latency_ms=(time.perf_counter() - started) * 1000.0,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        estimated_cost_usd=cost,
    )
