"""In-memory registries for capabilities and architectures.

Both registries start empty. The API does not seed demonstration rows.
"""

from .registry import ArchitectureRegistry, CapabilityRegistry

__all__ = ["ArchitectureRegistry", "CapabilityRegistry"]
