"""Abstract AI provider interface.

No concrete providers ship with the scaffold — challenge code plugs in
implementations (OpenAI, Anthropic, local models, ...) behind this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from typing import Any

from .types import Message, ModelResponse


class AIProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Identifier used for metrics and pricing lookups (e.g. 'gpt-4o')."""

    @abstractmethod
    async def generate(self, messages: Sequence[Message], **kwargs: Any) -> ModelResponse:
        """Produce a full response for the given conversation."""

    @abstractmethod
    def stream(self, messages: Sequence[Message], **kwargs: Any) -> AsyncIterator[str]:
        """Stream response chunks. Implement as an async generator."""
