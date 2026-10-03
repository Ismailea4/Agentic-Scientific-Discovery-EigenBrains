"""Immutable benchmark cache keyed by every result-defining input."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .artifacts import SecretScrubber


def benchmark_cache_key(
    *,
    case_id: str,
    model: str,
    model_configuration: Mapping[str, Any],
    prompt_configuration: Mapping[str, Any],
) -> str:
    canonical = json.dumps(
        {
            "case_id": case_id,
            "model": model,
            "model_configuration": model_configuration,
            "prompt_configuration": prompt_configuration,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


class ImmutableBenchmarkCache:
    def __init__(self, directory: str | Path, *, scrubber: SecretScrubber | None = None) -> None:
        self.directory = Path(directory)
        self.scrubber = scrubber or SecretScrubber.from_environment()

    def get(self, key: str) -> dict[str, Any] | None:
        if not _is_sha256(key):
            raise ValueError("cache key must be a SHA-256 hex digest")
        path = self.directory / f"{key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put(self, key: str, value: Mapping[str, Any]) -> Path:
        if not _is_sha256(key):
            raise ValueError("cache key must be a SHA-256 hex digest")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{key}.json"
        payload = self.scrubber.clean(dict(value))
        serialized = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        if path.exists():
            if path.read_text(encoding="utf-8") != serialized:
                raise ValueError("immutable benchmark cache entry already exists with different content")
            return path
        temporary = path.with_suffix(".tmp")
        temporary.write_text(serialized, encoding="utf-8")
        temporary.replace(path)
        return path
