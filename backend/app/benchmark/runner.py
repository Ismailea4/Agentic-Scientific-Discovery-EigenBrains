"""Reproducible architecture benchmark runner with caller-supplied execution."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .evaluators import EvaluatorRegistry
from .models import ArchitectureTemplate, BenchmarkCase, BenchmarkRun, BenchmarkSplit, SystemOutcome


@dataclass(frozen=True)
class AgentCallObservation:
    agent_role: str
    provider: str
    model: str
    output: Any
    success: bool
    error_type: str | None
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float | None
    fallback: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    malformed_output: bool = False
    constraint_violations: tuple[str, ...] = ()
    confidence: float | None = None
    model_configuration: dict[str, Any] = field(default_factory=dict)
    prompt_config_hash: str | None = None


@dataclass(frozen=True)
class ArchitectureExecution:
    calls: tuple[AgentCallObservation, ...]
    final_output: Any
    outcome: SystemOutcome = SystemOutcome.ANSWER
    disagreement: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    abstained: bool = False


Executor = Callable[
    [BenchmarkCase, ArchitectureTemplate, int, int | None],
    ArchitectureExecution | Awaitable[ArchitectureExecution],
]


class BenchmarkRunner:
    def __init__(self, evaluator_registry: EvaluatorRegistry | None = None) -> None:
        self.evaluators = evaluator_registry or EvaluatorRegistry()

    async def run(
        self,
        cases: Iterable[BenchmarkCase],
        architectures: Sequence[ArchitectureTemplate],
        executor: Executor,
        *,
        repeats: int,
        seed: int | None,
        allowed_splits: frozenset[BenchmarkSplit | str] | None = frozenset({BenchmarkSplit.DEV}),
    ) -> list[BenchmarkRun]:
        if repeats < 1:
            raise ValueError("repeats must be >= 1")
        allowed = None if allowed_splits is None else {str(getattr(item, "value", item)) for item in allowed_splits}
        results: list[BenchmarkRun] = []
        for case in cases:
            split = str(getattr(case.split, "value", case.split))
            difficulty = str(getattr(case.difficulty, "value", case.difficulty))
            risk_level = str(getattr(case.risk_level, "value", case.risk_level))
            if allowed is not None and split not in allowed:
                continue
            evaluator = self.evaluators.resolve(case)
            task_type = str(getattr(case.task_type, "value", case.task_type))
            for architecture in architectures:
                for repeat in range(repeats):
                    execution = executor(case, architecture, repeat, seed)
                    if inspect.isawaitable(execution):
                        execution = await execution
                    evaluation = evaluator.evaluate(case, execution.final_output)
                    timestamp = datetime.now(timezone.utc).isoformat()
                    if not execution.calls:
                        results.append(
                            BenchmarkRun(
                                benchmark_case_id=case.id,
                                task_type=task_type,
                                architecture_id=architecture.id,
                                agent_role="system",
                                provider="none",
                                model="none",
                                output=execution.final_output,
                                success=execution.outcome in {SystemOutcome.ANSWER, SystemOutcome.VERIFY},
                                error_type=None,
                                latency_ms=0.0,
                                input_tokens=0,
                                output_tokens=0,
                                estimated_cost_usd=0.0,
                                score=evaluation.score,
                                passed=evaluation.passed,
                                disagreement=execution.disagreement,
                                outcome=execution.outcome,
                                repeat=repeat,
                                seed=seed,
                                timestamp=timestamp,
                                metadata={
                                    **execution.metadata,
                                    "case_metadata": dict(case.metadata),
                                    "should_abstain": case.metadata.get("should_abstain"),
                                    "final_output": True,
                                    "split": split,
                                    "difficulty": difficulty,
                                    "risk_level": risk_level,
                                    "evaluation": dict(evaluation.metadata),
                                },
                                abstained=execution.abstained,
                            )
                        )
                        continue
                    for index, call in enumerate(execution.calls):
                        is_final = index == len(execution.calls) - 1
                        results.append(
                            BenchmarkRun(
                                benchmark_case_id=case.id,
                                task_type=task_type,
                                architecture_id=architecture.id,
                                agent_role=call.agent_role,
                                provider=call.provider,
                                model=call.model,
                                output=call.output,
                                success=call.success,
                                error_type=call.error_type,
                                latency_ms=call.latency_ms,
                                input_tokens=call.input_tokens,
                                output_tokens=call.output_tokens,
                                estimated_cost_usd=call.estimated_cost_usd,
                                score=evaluation.score if is_final else None,
                                passed=evaluation.passed if is_final else None,
                                disagreement=execution.disagreement if is_final else None,
                                fallback=call.fallback,
                                outcome=execution.outcome,
                                repeat=repeat,
                                seed=seed,
                                timestamp=timestamp,
                                metadata={
                                    **call.metadata,
                                    **execution.metadata,
                                    "case_metadata": dict(case.metadata),
                                    "should_abstain": case.metadata.get("should_abstain"),
                                    "final_output": is_final,
                                    "split": split,
                                    "difficulty": difficulty,
                                    "risk_level": risk_level,
                                    "evaluation": dict(evaluation.metadata) if is_final else {},
                                },
                                malformed_output=call.malformed_output,
                                abstained=execution.abstained if is_final else False,
                                constraint_violations=call.constraint_violations,
                                confidence=call.confidence if is_final else None,
                                model_configuration=dict(call.model_configuration),
                                prompt_config_hash=call.prompt_config_hash,
                            )
                        )
        return results
