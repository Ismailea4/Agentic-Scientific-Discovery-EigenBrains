"""Publish measured, complete candidates to the existing inspection registry."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from ..system.registry import ArchitectureRegistry
from .models import ArchitectureBenchmarkResult


def publish_measured_architectures(
    registry: ArchitectureRegistry,
    results: Iterable[ArchitectureBenchmarkResult],
) -> tuple[str, ...]:
    """Register only candidates with complete cost-aware measurements."""

    candidates = [result.to_candidate() for result in results]
    published: list[str] = []
    for raw_candidate in candidates:
        candidate = replace(
            raw_candidate,
            metadata={**raw_candidate.metadata, "evidence_state": "BENCHMARK"},
        )
        registry.register(candidate)
        published.append(candidate.id)
    return tuple(sorted(published))
