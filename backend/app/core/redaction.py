"""Shared redaction for logs and execution traces.

Key matching is by token, so `input_tokens` is kept and `api_key` is not.
Prompt, message, and document fields are removed: this layer cannot tell
which of them contain secrets, and neither logs nor traces are a transcript
store.
"""

from __future__ import annotations

import os
import re
from typing import Any

_SECRET_PARTS = {
    "password",
    "secret",
    "token",
    "apikey",
    "authorization",
    "credential",
    "cookie",
    "cookies",
    "prompt",
    "prompts",
    "message",
    "messages",
    "document",
    "documents",
    "env",
    "environment",
}

_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
_SK = re.compile(r"sk-[A-Za-z0-9]{8,}")
_AWS = re.compile(r"AKIA[0-9A-Z]{16}")


def is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    parts = set(normalized.split("_"))
    if parts & _SECRET_PARTS:
        return True
    if "api" in parts and "key" in parts:
        return True
    if "private" in parts and "key" in parts:
        return True
    if "access" in parts and "key" in parts:
        return True
    return False


def mask_secret_text(value: str) -> str:
    masked = _BEARER.sub("Bearer [redacted]", value)
    masked = _SK.sub("[redacted]", masked)
    masked = _AWS.sub("[redacted]", masked)
    for name, secret in os.environ.items():
        if is_secret_key(name) and len(secret) >= 6:
            masked = masked.replace(secret, "[redacted]")
    return masked


def redact(value: Any) -> Any:
    """Return a copy safe to serialize. Mappings and lists are walked."""

    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if is_secret_key(text_key):
                cleaned[text_key] = "[redacted]"
            else:
                cleaned[text_key] = redact(item)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return mask_secret_text(value)
    return value
