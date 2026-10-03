"""Evaluator interfaces; challenge-specific scoring plugs in here."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Protocol

from .models import BenchmarkCase


SCORING_V1_VERSION = "SCORING_V1"
SCORING_V1_SPEC = {
    "version": SCORING_V1_VERSION,
    "base": "primary_v0_casefolded_exact_match",
    "normalizations": [
        "strip_outer_whitespace",
        "unicode_casefold",
        "strip_trailing_sentence_punctuation",
        "planning_comma_whitespace",
    ],
    "critique_aliases": {
        "overgeneralization": ["hasty generalization", "overgeneralization"],
        "causal_inference": [
            "causal inference",
            "causal_inference",
            "correlation does not imply causation",
            "false cause",
        ],
    },
    "json": "parsed structural exact equality; malformed JSON fails",
    "scope": "Only the equivalences documented before Baseline v0 execution.",
}
SCORING_V1_HASH = hashlib.sha256(
    json.dumps(SCORING_V1_SPEC, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()


@dataclass(frozen=True)
class EvaluationOutcome:
    score: float | None
    passed: bool | None
    metadata: dict[str, Any] = field(default_factory=dict)


class Evaluator(Protocol):
    def evaluate(self, case: BenchmarkCase, output: Any) -> EvaluationOutcome: ...


class ExactMatchEvaluator:
    def __init__(self, *, case_sensitive: bool = False) -> None:
        self.case_sensitive = case_sensitive

    def evaluate(self, case: BenchmarkCase, output: Any) -> EvaluationOutcome:
        expected = str(case.expected_answer).strip()
        actual = str(output).strip()
        if not self.case_sensitive:
            expected = expected.casefold()
            actual = actual.casefold()
        passed = actual == expected
        return EvaluationOutcome(score=1.0 if passed else 0.0, passed=passed)


def canonicalize_scoring_v1(case: BenchmarkCase, value: Any) -> str:
    normalized = str(value).strip().casefold().rstrip(". !?;:")
    task_type = str(getattr(case.task_type, "value", case.task_type))
    if task_type == "planning":
        normalized = re.sub(r"\s*,\s*", ",", normalized)
    if task_type == "critique":
        aliases = SCORING_V1_SPEC["critique_aliases"]
        for canonical, accepted in aliases.items():
            if normalized in accepted:
                return canonical
    return normalized


class ScoringV1Evaluator:
    """Frozen canonical evaluator plus the preserved exact-match v0 result."""

    def __init__(self) -> None:
        self.primary_v0 = ExactMatchEvaluator()

    def evaluate(self, case: BenchmarkCase, output: Any) -> EvaluationOutcome:
        primary_v0 = self.primary_v0.evaluate(case, output)
        expected = canonicalize_scoring_v1(case, case.expected_answer)
        actual = canonicalize_scoring_v1(case, output)
        passed = actual == expected
        return EvaluationOutcome(
            score=1.0 if passed else 0.0,
            passed=passed,
            metadata={
                "evaluator_version": SCORING_V1_VERSION,
                "evaluator_hash": SCORING_V1_HASH,
                "primary_v0_score": primary_v0.score,
                "primary_v0_passed": primary_v0.passed,
            },
        )


class NumericToleranceEvaluator:
    def __init__(self, *, absolute_tolerance: float) -> None:
        if absolute_tolerance < 0:
            raise ValueError("absolute_tolerance must be >= 0")
        self.absolute_tolerance = absolute_tolerance

    def evaluate(self, case: BenchmarkCase, output: Any) -> EvaluationOutcome:
        try:
            error = abs(float(output) - float(case.expected_answer))
        except (TypeError, ValueError):
            return EvaluationOutcome(score=0.0, passed=False, metadata={"reason": "non_numeric_output"})
        passed = error <= self.absolute_tolerance
        score = max(0.0, 1.0 - error / max(abs(float(case.expected_answer)), 1.0))
        return EvaluationOutcome(score=score, passed=passed, metadata={"absolute_error": error})


class JsonExactEvaluator:
    def evaluate(self, case: BenchmarkCase, output: Any) -> EvaluationOutcome:
        try:
            actual = json.loads(output) if isinstance(output, str) else output
        except (TypeError, json.JSONDecodeError):
            return EvaluationOutcome(
                score=0.0,
                passed=False,
                metadata={
                    "reason": "malformed_json",
                    "evaluator_version": SCORING_V1_VERSION,
                    "evaluator_hash": SCORING_V1_HASH,
                    "primary_v0_score": 0.0,
                    "primary_v0_passed": False,
                },
            )
        passed = actual == case.expected_answer
        return EvaluationOutcome(
            score=1.0 if passed else 0.0,
            passed=passed,
            metadata={
                "evaluator_version": SCORING_V1_VERSION,
                "evaluator_hash": SCORING_V1_HASH,
                "primary_v0_score": 1.0 if passed else 0.0,
                "primary_v0_passed": passed,
            },
        )


class EvaluatorRegistry:
    def __init__(self) -> None:
        self._evaluators: dict[str, Evaluator] = {
            "exact_match": ExactMatchEvaluator(),
            "scoring_v1": ScoringV1Evaluator(),
            "json_exact": JsonExactEvaluator(),
        }

    def register(self, name: str, evaluator: Evaluator) -> None:
        if not name.strip():
            raise ValueError("evaluator name must not be empty")
        self._evaluators[name] = evaluator

    def resolve(self, case: BenchmarkCase) -> Evaluator:
        name = case.evaluator or "exact_match"
        try:
            return self._evaluators[name]
        except KeyError as exc:
            raise ValueError(f"unknown evaluator '{name}'") from exc
