"""Bounded retry policy with exponential backoff and jitter."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 0.25
    max_delay_seconds: float = 4.0
    jitter_fraction: float = 0.2

    def validate(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.initial_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays must be >= 0")
        if not 0 <= self.jitter_fraction <= 1:
            raise ValueError("jitter_fraction must be in [0, 1]")


async def call_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    should_retry: Callable[[BaseException], bool],
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: random.Random | None = None,
) -> T:
    policy.validate()
    source = rng or random.Random()
    for attempt in range(policy.max_attempts):
        try:
            return await operation()
        except Exception as exc:
            if attempt + 1 >= policy.max_attempts or not should_retry(exc):
                raise
            base = min(policy.max_delay_seconds, policy.initial_delay_seconds * (2**attempt))
            jitter = base * policy.jitter_fraction * source.random()
            await sleep(base + jitter)
    raise AssertionError("unreachable")
