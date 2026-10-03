"""Minimal environment-only Gemini GenerateContent adapter."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from typing import Any
from urllib.parse import quote

import httpx

from ..ai.provider import AIProvider
from ..ai.types import Message, ModelResponse, TokenUsage
from ..core.errors import ProviderError


class GeminiProvider(AIProvider):
    def __init__(
        self,
        *,
        model: str,
        api_key_env: str = "GEMINI_API_KEY",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise ValueError(f"required credential environment variable is not set: {api_key_env}")
        if not model.strip():
            raise ValueError("an explicit Gemini model name is required")
        self.model = model.strip().removeprefix("models/")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def name(self) -> str:
        return "gemini"

    async def generate(self, messages: Sequence[Message], **kwargs: Any) -> ModelResponse:
        system = "\n\n".join(item.content for item in messages if item.role == "system")
        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "model" if item.role == "assistant" else "user",
                    "parts": [{"text": item.content}],
                }
                for item in messages
                if item.role != "system"
            ]
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        generation: dict[str, Any] = {}
        if "temperature" in kwargs:
            generation["temperature"] = kwargs["temperature"]
        token_limit = kwargs.get("max_tokens", kwargs.get("max_completion_tokens"))
        if token_limit is not None:
            generation["maxOutputTokens"] = int(token_limit)
        if generation:
            payload["generationConfig"] = generation

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
        try:
            response = await client.post(
                f"{self._base_url}/models/{quote(self.model, safe='')}:generateContent",
                headers={"x-goog-api-key": self._api_key},
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
            parts = body["candidates"][0]["content"]["parts"]
            content = "".join(str(part.get("text") or "") for part in parts)
            usage = body.get("usageMetadata") or {}
            return ModelResponse(
                content=content,
                model=str(body.get("modelVersion") or self.model),
                usage=TokenUsage(
                    input_tokens=int(usage.get("promptTokenCount") or 0),
                    output_tokens=int(usage.get("candidatesTokenCount") or 0),
                ),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("Gemini returned an invalid response shape") from exc

    def stream(self, messages: Sequence[Message], **kwargs: Any) -> AsyncIterator[str]:
        async def _generate_once() -> AsyncIterator[str]:
            response = await self.generate(messages, **kwargs)
            yield response.content

        return _generate_once()
