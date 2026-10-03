"""Load versioned benchmark cases from JSON without executing them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import BenchmarkCase


def load_benchmark_cases(path: str | Path) -> tuple[BenchmarkCase, ...]:
    source = Path(path)
    payload: Any = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("benchmark dataset must be an object containing a cases list")
    cases = tuple(BenchmarkCase(**item) for item in payload["cases"])
    identifiers = [case.id for case in cases]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("benchmark case ids must be unique")
    return cases
