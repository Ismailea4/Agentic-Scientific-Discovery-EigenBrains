"""Bounded single-model pilot built on the existing benchmark spine."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from ..ai.provider import AIProvider
from ..ai.types import Message
from ..instrumentation.pricing import PricingTable
from ..providers import AnthropicProvider, GeminiProvider, OpenAIProvider, invoke_normalized
from .artifacts import SecretScrubber, _write_jsonl
from .controls import BenchmarkLimits, BudgetController, ModelProjection, authorize_projection
from .models import BenchmarkCase, BenchmarkRun, SystemOutcome
from .runner import AgentCallObservation, ArchitectureExecution, BenchmarkRunner
from .templates import architecture_templates

PILOT_PROMPT = (
    "Answer the objective benchmark item. Return only the requested answer, "
    "with no explanation or markdown."
)


def pilot_prompt_config_hash(output_token_cap: int) -> str:
    payload = {
        "system": PILOT_PROMPT,
        "temperature": 0,
        "max_output_tokens": output_token_cap,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PilotModelSpec:
    provider: str
    model: str


def load_shortlist(path: str | Path) -> tuple[PilotModelSpec, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(PilotModelSpec(row["provider"], row["model"]) for row in payload["models"])


def select_pilot_cases(
    cases: Sequence[BenchmarkCase], *, per_task: int = 2
) -> tuple[BenchmarkCase, ...]:
    if per_task < 1:
        raise ValueError("per_task must be >= 1")
    grouped: dict[str, list[BenchmarkCase]] = defaultdict(list)
    for case in cases:
        split = str(getattr(case.split, "value", case.split))
        if split == "dev":
            grouped[str(getattr(case.task_type, "value", case.task_type))].append(case)
    return tuple(
        case
        for task in sorted(grouped)
        for case in sorted(grouped[task], key=lambda item: item.id)[:per_task]
    )


def pilot_projection(
    specs: Sequence[PilotModelSpec],
    cases: Sequence[BenchmarkCase],
    pricing: PricingTable,
    *,
    input_token_cap: int,
    output_token_cap: int,
) -> tuple[ModelProjection, ...]:
    if input_token_cap < 1 or output_token_cap < 1:
        raise ValueError("token caps must be positive")
    calls = len(cases)
    return tuple(
        ModelProjection(
            provider=spec.provider,
            model=spec.model,
            projected_calls=calls,
            projected_input_tokens=input_token_cap * calls,
            projected_output_tokens=output_token_cap * calls,
            projected_cost_usd=(
                None
                if pricing.estimate_cost(spec.model, input_token_cap, output_token_cap) is None
                else pricing.estimate_cost(spec.model, input_token_cap, output_token_cap) * calls
            ),
            projected_runtime_seconds=0.0,
        )
        for spec in specs
    )


def build_provider(spec: PilotModelSpec) -> AIProvider:
    if spec.provider == "anthropic":
        return AnthropicProvider(model=spec.model)
    if spec.provider == "gemini":
        return GeminiProvider(model=spec.model)
    if spec.provider == "groq":
        return OpenAIProvider(
            model=spec.model,
            api_key_env="GROQ_API_KEY",
            base_url="https://api.groq.com/openai/v1",
            provider_name="groq",
        )
    if spec.provider == "openrouter":
        return OpenAIProvider(
            model=spec.model,
            api_key_env="OPENROUTER_API_KEY",
            base_url="https://openrouter.ai/api/v1",
            provider_name="openrouter",
        )
    if spec.provider == "openai":
        return OpenAIProvider(model=spec.model)
    raise ValueError(f"unsupported pilot provider '{spec.provider}'")


async def run_single_model_pilot(
    cases: Sequence[BenchmarkCase],
    specs: Sequence[PilotModelSpec],
    pricing: PricingTable,
    limits: BenchmarkLimits,
    *,
    output_token_cap: int = 256,
    input_token_cap: int = 1024,
    seed: int = 0,
    allowed_splits: frozenset[str] | None = frozenset({"dev"}),
    controller: BudgetController | None = None,
) -> list[BenchmarkRun]:
    projection = pilot_projection(
        specs,
        cases,
        pricing,
        input_token_cap=input_token_cap,
        output_token_cap=output_token_cap,
    )
    authorize_projection(projection, limits)
    active_controller = controller or BudgetController(limits)
    runner = BenchmarkRunner()
    architecture = architecture_templates()[0]
    runs: list[BenchmarkRun] = []

    for spec in specs:
        provider = build_provider(spec)
        maximum_cost = pricing.estimate_cost(spec.model, input_token_cap, output_token_cap)

        async def execute(
            case: BenchmarkCase,
            _architecture: Any,
            _repeat: int,
            _seed: int | None,
            *,
            selected_provider: AIProvider = provider,
            selected_spec: PilotModelSpec = spec,
            call_cost: float | None = maximum_cost,
        ) -> ArchitectureExecution:
            async with active_controller.slot(selected_spec.model, projected_cost_usd=call_cost):
                call = await invoke_normalized(
                    selected_provider,
                    [Message("system", PILOT_PROMPT), Message("user", str(case.input))],
                    task_type=case.task_type,
                    pricing=pricing,
                    max_tokens=output_token_cap,
                    temperature=0,
                )
            malformed = False
            if case.evaluator == "json_exact" and call.output is not None:
                try:
                    json.loads(call.output)
                except (TypeError, json.JSONDecodeError):
                    malformed = True
            observation = AgentCallObservation(
                agent_role="solver",
                provider=call.provider,
                model=selected_spec.model,
                output=call.output,
                success=call.success,
                error_type=call.error_type,
                latency_ms=call.latency_ms,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                estimated_cost_usd=(
                    call.estimated_cost_usd
                    if call.estimated_cost_usd is not None
                    else pricing.estimate_cost(
                        selected_spec.model, call.input_tokens, call.output_tokens
                    )
                    if call.success
                    else None
                ),
                malformed_output=malformed,
                metadata={"resolved_provider_model": call.model},
                model_configuration={"temperature": 0, "max_tokens": output_token_cap},
                prompt_config_hash=pilot_prompt_config_hash(output_token_cap),
            )
            return ArchitectureExecution(
                calls=(observation,),
                final_output=call.output or "",
                outcome=SystemOutcome.ANSWER if call.success else SystemOutcome.INSUFFICIENT_EVIDENCE,
            )

        runs.extend(
            await runner.run(
                cases,
                [architecture],
                execute,
                repeats=1,
                seed=seed,
                allowed_splits=allowed_splits,
            )
        )
    return runs


def write_pilot_runs(path: str | Path, runs: Sequence[BenchmarkRun]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(
        destination,
        [run.to_dict() for run in runs],
        SecretScrubber.from_environment(),
    )
    return destination
