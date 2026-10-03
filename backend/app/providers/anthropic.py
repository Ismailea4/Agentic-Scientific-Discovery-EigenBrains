"""Minimal environment-only Anthropic Messages adapter."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from ..ai.provider import AIProvider
from ..ai.types import Message, ModelResponse, TokenUsage
from ..core.errors import ProviderError


class AnthropicProvider(AIProvider):
    def __init__(
        self,
        *,
        model: str,
        api_key_env: str = "ANTHROPIC_API_KEY",
        base_url: str = "https://api.anthropic.com/v1",
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise ValueError(f"required credential environment variable is not set: {api_key_env}")
        if not model.strip():
            raise ValueError("an explicit Anthropic model name is required")
        self.model = model.strip()
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def name(self) -> str:
        return "anthropic"

    async def generate(self, messages: Sequence[Message], **kwargs: Any) -> ModelResponse:
        system = "\n\n".join(item.content for item in messages if item.role == "system")
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": int(kwargs.get("max_tokens", kwargs.get("max_completion_tokens", 1024))),
            "messages": [
                {"role": "assistant" if item.role == "assistant" else "user", "content": item.content}
                for item in messages
                if item.role != "system"
            ],
        }
        if system:
            payload["system"] = system
        for name in ("temperature", "top_p"):
            if name in kwargs:
                payload[name] = kwargs[name]

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
        try:
            response = await client.post(
                f"{self._base_url}/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            raise ProviderError(f"Provider request failed ({type(exc).__name__})") from exc
        finally:
            if owns_client:
                await client.aclose()

        try:
            content = "".join(
                str(block.get("text") or "")
                for block in body.get("content", [])
                if block.get("type") == "text"
            )
            usage = body.get("usage") or {}
            return ModelResponse(
                content=content,
                model=str(body.get("model") or self.model),
                usage=TokenUsage(
                    input_tokens=int(usage.get("input_tokens") or 0),
                    output_tokens=int(usage.get("output_tokens") or 0),
                ),
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ProviderError("Anthropic returned an invalid response shape") from exc

    def stream(self, messages: Sequence[Message], **kwargs: Any) -> AsyncIterator[str]:
        async def _generate_once() -> AsyncIterator[str]:
            response = await self.generate(messages, **kwargs)
            yield response.content

        return _generate_once()
