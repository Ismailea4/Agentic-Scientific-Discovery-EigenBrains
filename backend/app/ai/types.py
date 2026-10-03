"""Shared types for the AI layer.

These types are provider-agnostic. Concrete providers adapt their SDK payloads
into `ModelResponse` so instrumentation always sees a uniform shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


@dataclass
class Message:
    role: str
    content: str


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ModelResponse:
    content: str
    model: str
    usage: TokenUsage
    raw: Any | None = None


class TaskType(str, Enum):
    """Challenge-agnostic benchmark categories.

    Challenge-specific categories may be added after the prompt is known, but
    these stable values keep generic baseline measurements comparable.
    """

    GENERIC = "generic"
    EXTRACTION = "extraction"
    STRUCTURED_EXTRACTION = "structured_extraction"
    CLASSIFICATION = "classification"
    NUMERICAL_REASONING = "numerical_reasoning"
    MATHEMATICAL_REASONING = "mathematical_reasoning"
    LOGICAL_REASONING = "logical_reasoning"
    DOMAIN_REASONING = "domain_reasoning"
    PLANNING = "planning"
    CRITIQUE = "critique"
    EVIDENCE_VERIFICATION = "evidence_verification"
    TOOL_USE_REASONING = "tool_use_reasoning"
    CODE_UNDERSTANDING_DEBUGGING = "code_understanding_debugging"
    UNCERTAINTY_ABSTENTION = "uncertainty_abstention"
    SYNTHESIS = "synthesis"
