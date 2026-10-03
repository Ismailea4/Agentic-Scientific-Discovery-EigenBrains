"""Process-local catalogues. Challenge code registers real entries later."""

from __future__ import annotations

from ..capabilities.models import Capability
from ..optimization.models import ArchitectureCandidate


class CapabilityRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        self._items[capability.name] = capability

    def list(self) -> list[Capability]:
        return [self._items[name] for name in sorted(self._items)]

    def clear(self) -> None:
        self._items.clear()


class ArchitectureRegistry:
    def __init__(self) -> None:
        self._items: dict[str, ArchitectureCandidate] = {}

    def register(self, candidate: ArchitectureCandidate) -> None:
        self._items[candidate.id] = candidate

    def list(self) -> list[ArchitectureCandidate]:
        return [self._items[identifier] for identifier in sorted(self._items)]

    def clear(self) -> None:
        self._items.clear()
