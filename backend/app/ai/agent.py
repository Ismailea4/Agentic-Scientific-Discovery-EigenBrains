"""Abstract agent base class.

Agents wrap an `AIProvider` and route every model call through
`MetricsRecorder.track_call` via `_generate`, so instrumentation cannot be
accidentally bypassed by challenge code.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from ..core.logging import log_event, safe_error
from ..instrumentation.recorder import MetricsRecorder
from .provider import AIProvider
from .types import Message, ModelResponse, TaskType


class Agent(ABC):
    def __init__(
        self,
        provider: AIProvider,
        name: str,
        task_type: TaskType = TaskType.GENERIC,
        recorder: MetricsRecorder | None = None,
    ) -> None:
        self.provider = provider
        self.name = name
        self.task_type = task_type
        self.recorder = recorder or MetricsRecorder()

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the agent's task. Signature is challenge-specific."""

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Run the agent and emit agent.started / completed / failed.

        Challenge code should call this instead of `run` so the boundary is logged.
        """

        task = self.task_type.value if isinstance(self.task_type, TaskType) else str(self.task_type)
        log_event("agent.started", agent_name=self.name, task_type=task, provider=self.provider.name)
        try:
            result = await self.run(*args, **kwargs)
        except Exception as exc:
            log_event(
                "agent.failed",
                level=logging.ERROR,
                agent_name=self.name,
                task_type=task,
                provider=self.provider.name,
                success=False,
                exception_type=type(exc).__name__,
                error=safe_error(exc),
            )
            raise
        log_event(
            "agent.completed",
            agent_name=self.name,
            task_type=task,
            provider=self.provider.name,
            success=True,
        )
        return result

    async def _generate(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Instrumented wrapper around `provider.generate`."""
        model_name = model or str(getattr(self.provider, "model", self.provider.name))
        async with self.recorder.track_call(
            model=model_name,
            agent=self.name,
            task_type=self.task_type,
            metadata=metadata,
            provider=self.provider.name,
        ) as call:
            response = await self.provider.generate(messages, **kwargs)
            call.set_response(response)
        return response
