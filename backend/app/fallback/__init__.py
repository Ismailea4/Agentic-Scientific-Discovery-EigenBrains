"""Deterministic fallback resolution.

A fallback is chosen only when it is available, holds every mandatory
capability, matches an accepted privacy class, and lists the current task.
Preference order is the caller's audit order, not a quality score. No
candidate is selected merely because it is online.
"""

from .models import FallbackCandidate, FallbackDecision, FallbackPolicy
from .resolver import resolve_fallback

__all__ = [
    "FallbackCandidate",
    "FallbackDecision",
    "FallbackPolicy",
    "resolve_fallback",
]
