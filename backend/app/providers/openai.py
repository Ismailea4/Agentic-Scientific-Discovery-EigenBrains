"""Minimal OpenAI Chat Completions adapter.

The adapter accepts credentials only from a named environment variable. It
never places the credential in a dataclass, log field, trace, or return value.
No provider is constructed unless both a key and an explicit model are set.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from ..ai.provider import AIProvider
from ..ai.types import Message, ModelResponse, TokenUsage
from ..core.errors import ProviderError


class OpenAIProvider(AIProvider):
    def __init__(
        self,
        *,
        model: str,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str = "https://api.openai.com/v1",
        provider_name: str = "openai",
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise ValueError(f"required credential environment variable is not set: {api_key_env}")
        if not model.strip():
            raise ValueError("an explicit OpenAI model name is required")
        self.model = model.strip()
        self._provider_name = provider_name.strip()
        if not self._provider_name:
            raise ValueError("provider_name is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def name(self) -> str:
        return self._provider_name

    async def generate(self, messages: Sequence[Message], **kwargs: Any) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
        }
        for name in (
            "temperature", "max_tokens", "max_completion_tokens", "seed",
            "response_format", "reasoning_effort",
        ):
            if name in kwargs:
                payload[name] = kwargs[name]

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
        try:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
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
            content = body["choices"][0]["message"]["content"] or ""
            usage = body.get("usage") or {}
            return ModelResponse(
                content=str(content),
                model=str(body.get("model") or self.model),
                usage=TokenUsage(
                    input_tokens=int(usage.get("prompt_tokens") or 0),
                    output_tokens=int(usage.get("completion_tokens") or 0),
                ),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("OpenAI returned an invalid response shape") from exc

    def stream(self, messages: Sequence[Message], **kwargs: Any) -> AsyncIterator[str]:
        async def _generate_once() -> AsyncIterator[str]:
            response = await self.generate(messages, **kwargs)
            yield response.content

        return _generate_once()


def available_providers() -> list[AIProvider]:
    """Construct only explicitly configured providers; never return key data."""

    from .anthropic import AnthropicProvider
    from .gemini import GeminiProvider

    providers: list[AIProvider] = []
    openai_model = os.getenv("OPENAI_MODEL", "").strip()
    if os.getenv("OPENAI_API_KEY") and openai_model:
        providers.append(
            OpenAIProvider(
                model=openai_model,
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            )
        )
    groq_model = os.getenv("GROQ_MODEL", "").strip()
    if os.getenv("GROQ_API_KEY") and groq_model:
        providers.append(
            OpenAIProvider(
                model=groq_model,
                api_key_env="GROQ_API_KEY",
                base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
                provider_name="groq",
            )
        )
    anthropic_model = os.getenv("ANTHROPIC_MODEL", "").strip()
    if os.getenv("ANTHROPIC_API_KEY") and anthropic_model:
        providers.append(AnthropicProvider(model=anthropic_model))
    gemini_model = os.getenv("GEMINI_MODEL", "").strip()
    if os.getenv("GEMINI_API_KEY") and gemini_model:
        providers.append(GeminiProvider(model=gemini_model))
    openrouter_model = os.getenv("OPENROUTER_MODEL", "").strip()
    if os.getenv("OPENROUTER_API_KEY") and openrouter_model:
        providers.append(
            OpenAIProvider(
                model=openrouter_model,
                api_key_env="OPENROUTER_API_KEY",
                base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                provider_name="openrouter",
            )
        )
    return providers
