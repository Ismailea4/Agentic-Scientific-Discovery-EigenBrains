import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.ai.types import Message
from app.benchmark.ablation import ablation_variants, compare_ablations
from app.benchmark.artifacts import SecretScrubber, write_benchmark_artifacts
from app.benchmark.dataset import load_benchmark_cases
from app.benchmark.metrics import aggregate_architectures
from app.benchmark.models import (
    ArchitectureBenchmarkResult,
    BenchmarkRun,
    SystemOutcome,
)
from app.benchmark.templates import architecture_templates
from app.fallback import FallbackCandidate, FallbackPolicy, resolve_fallback
from app.instrumentation.pricing import PricingTable
from app.optimization.bayesian import update_bounded_quality
from app.optimization.covariance import analyze_error_vectors, select_complementary_pair
from app.optimization.information_gain import evaluate_information_gain
from app.optimization.models import (
    ArchitectureCandidate,
    ArchitectureMetrics,
    OptimizationConstraints,
    OptimizationWeights,
)
from app.optimization.router import RoutingRequest, select_architecture_for_task
from app.optimization.selection import select_best
from app.optimization.tail_risk import TailRiskEstimate, empirical_tail_risk
from app.providers.base import invoke_normalized
from app.providers.anthropic import AnthropicProvider
from app.providers.gemini import GeminiProvider
from app.providers.openai import OpenAIProvider, available_providers


def _result(
    identifier: str,
    *,
    quality: float,
    cost: float | None,
    latency: float,
    risk: float,
    failure_rate: float = 0.0,
    metadata: dict | None = None,
) -> ArchitectureBenchmarkResult:
    return ArchitectureBenchmarkResult(
        architecture_id=identifier,
        architecture_name=identifier,
        expected_quality=quality,
        cost=cost,
        latency=latency,
        failure_rate=failure_rate,
        risk=risk,
        quality_variance=0.01,
        sample_size=4,
        tail_risk=TailRiskEstimate(score=risk, sample_size=4),
        task_types=("classification",),
        metadata=metadata or {},
    )


def _run(
    architecture_id: str,
    case_id: str,
    *,
    score: float,
    cost: float | None,
    output: str = "ok",
    success: bool = True,
) -> BenchmarkRun:
    return BenchmarkRun(
        benchmark_case_id=case_id,
        task_type="classification",
        architecture_id=architecture_id,
        agent_role="solver",
        provider="offline-test",
        model="deterministic",
        output=output,
        success=success,
        error_type=None if success else "SyntheticFailure",
        latency_ms=10.0,
        input_tokens=2,
        output_tokens=1,
        estimated_cost_usd=cost,
        score=score,
        passed=score == 1.0,
        outcome=SystemOutcome.ANSWER if success else SystemOutcome.NO_CALL,
        repeat=0,
        seed=7,
        timestamp="2026-01-01T00:00:00+00:00",
        metadata={"final_output": True, "split": "dev"},
    )


def test_generic_prior_dataset_is_valid_and_has_unique_pipeline_cases():
    path = Path(__file__).parents[2] / "benchmark" / "cases" / "generic_prior.json"
    cases = load_benchmark_cases(path)
    assert len(cases) >= 5
    assert len({case.id for case in cases}) == len(cases)
    assert {str(getattr(case.task_type, "value", case.task_type)) for case in cases} >= {
        "structured_extraction",
        "classification",
        "mathematical_reasoning",
        "evidence_verification",
    }


def test_aggregate_preserves_unknown_cost_and_computes_tail_risk():
    runs = [
        _run("A0", "c1", score=1.0, cost=0.01),
        _run("A0", "c2", score=0.0, cost=None),
    ]
    (result,) = aggregate_architectures(
        runs,
        architecture_templates(),
        lower_percentile=0.25,
        severe_failure_threshold=0.2,
    )
    assert result.cost is None
    assert result.expected_quality == pytest.approx(0.5)
    assert result.tail_risk.worst_case_score == 0.0
    assert result.tail_risk.severe_failure_rate == pytest.approx(0.5)


def test_security_constraints_exclude_higher_quality_unsafe_candidate():
    safe = ArchitectureCandidate(
        id="safe",
        name="safe",
        metrics=ArchitectureMetrics(0.8, 1.0, 100.0, 0.2),
        required_capabilities=("read",),
        privacy_class="restricted",
    )
    unsafe = ArchitectureCandidate(
        id="unsafe",
        name="unsafe",
        metrics=ArchitectureMetrics(0.99, 0.1, 10.0, 0.01),
        required_capabilities=("network",),
        privacy_class="public",
    )
    decision = select_best(
        [safe, unsafe],
        constraints=OptimizationConstraints(
            available_capabilities=frozenset({"read", "network"}),
            denied_capabilities=frozenset({"network"}),
            accepted_privacy_classes=frozenset({"restricted"}),
        ),
    )
    assert decision.selected_id == "safe"
    assert dict(decision.rejected)["unsafe"] == (
        "denied capability 'network'; privacy class is not accepted"
    )


def test_budget_and_latency_constraints_change_router_selection():
    measured = [
        _result("lean", quality=0.8, cost=1.0, latency=100.0, risk=0.2),
        _result("deep", quality=0.95, cost=5.0, latency=500.0, risk=0.1),
    ]
    base = dict(
        task_type="classification",
        difficulty="medium",
        risk_level="low",
        capabilities=frozenset(),
        accepted_privacy_classes=None,
    )
    unconstrained = select_architecture_for_task(
        RoutingRequest(**base, budget=None, latency_limit=None),
        measured,
        weights=OptimizationWeights(),
    )
    budgeted = select_architecture_for_task(
        RoutingRequest(**base, budget=2.0, latency_limit=None),
        measured,
        weights=OptimizationWeights(),
    )
    fast = select_architecture_for_task(
        RoutingRequest(**base, budget=None, latency_limit=200.0),
        measured,
        weights=OptimizationWeights(),
    )
    assert unconstrained.architecture_id == "deep"
    assert budgeted.architecture_id == "lean"
    assert fast.architecture_id == "lean"


def test_router_refuses_out_of_distribution_and_unavailable_calls():
    measured = [_result("A0", quality=0.8, cost=1.0, latency=10.0, risk=0.1)]
    missing_evidence = select_architecture_for_task(
        RoutingRequest("planning", "hard", "high", frozenset(), None, None),
        measured,
        weights=OptimizationWeights(),
    )
    unavailable = select_architecture_for_task(
        RoutingRequest(
            "classification", "medium", "low", frozenset(), None, None,
            available_architecture_ids=frozenset(),
        ),
        measured,
        weights=OptimizationWeights(),
    )
    assert missing_evidence.outcome is SystemOutcome.OUT_OF_DISTRIBUTION
    assert unavailable.outcome is SystemOutcome.NO_CALL


def test_error_correlation_changes_complementary_pair_choice():
    analysis = analyze_error_vectors(
        {
            "m1": {"a": 1.0, "b": 0.0, "c": 1.0, "d": 0.0},
            "m2": {"a": 1.0, "b": 0.0, "c": 1.0, "d": 0.0},
            "m3": {"a": 0.0, "b": 1.0, "c": 0.0, "d": 1.0},
        },
        failure_threshold=0.5,
    )
    quality = {"m1": 0.9, "m2": 0.9, "m3": 0.85}
    assert select_complementary_pair(analysis, quality, correlation_penalty=0.0) == ("m1", "m2")
    assert select_complementary_pair(analysis, quality, correlation_penalty=1.0) == ("m1", "m3")


def test_fallback_respects_capability_and_privacy_constraints():
    decision = resolve_fallback(
        [
            FallbackCandidate(
                id="remote", available=True, capabilities=("read",),
                privacy_class="public", allowed_tasks=("review",),
            ),
            FallbackCandidate(
                id="local", available=True, capabilities=("read", "verify"),
                privacy_class="restricted", allowed_tasks=("review",),
            ),
        ],
        FallbackPolicy(
            mandatory_capabilities=("verify",),
            accepted_privacy_classes=("restricted",),
            task="review",
            preference_order=("remote", "local"),
        ),
    )
    assert decision.selected_id == "local"
    assert "missing mandatory capability" in dict(decision.rejected)["remote"]


def test_ablation_variants_and_measured_necessity_are_explicit():
    architecture = next(item for item in architecture_templates() if item.id == "A3")
    variants = ablation_variants(architecture)
    assert {item.metadata.get("removed_roles", [None])[0] for item in variants[:-1]} == {
        "specialist",
        "verifier",
    }
    full = _result("A3", quality=0.9, cost=3.0, latency=300.0, risk=0.1)
    without = _result(
        "A3-minus_verifier", quality=0.7, cost=2.0, latency=200.0, risk=0.3,
        failure_rate=0.2, metadata={"removed_roles": ["verifier"]},
    )
    (comparison,) = compare_ablations(
        full, [without], minimum_quality_effect=0.1, minimum_failure_effect=0.1
    )
    assert comparison.component_necessary is True
    assert comparison.quality_delta == pytest.approx(-0.2)


def test_tail_risk_bayesian_update_and_information_gain_are_data_driven():
    tail = empirical_tail_risk(
        [1.0, 0.8, 0.2, 0.0], lower_percentile=0.25, severe_failure_threshold=0.2
    )
    posterior = update_bounded_quality(
        prior_source="development-v1", prior_alpha=2.0, prior_beta=2.0,
        observed_scores=[1.0, 0.0],
    )
    invoke = evaluate_information_gain(
        expected_value_of_information=0.5,
        incremental_cost=0.1,
        incremental_latency=1.0,
        cost_weight=1.0,
        latency_weight=0.1,
    )
    skip = evaluate_information_gain(
        expected_value_of_information=0.05,
        incremental_cost=0.1,
        incremental_latency=1.0,
        cost_weight=1.0,
        latency_weight=0.1,
    )
    assert tail.worst_case_score == 0.0
    assert posterior.posterior_estimate == pytest.approx(0.5)
    assert invoke.invoke is True
    assert skip.invoke is False


def test_artifact_bundle_is_complete_and_never_contains_known_secret(tmp_path):
    secret = "credential-value-never-write"
    runs = [
        _run("A0", "pass", score=1.0, cost=0.01, output=f"safe {secret}"),
        _run("A0", "fail", score=0.0, cost=0.01, output=f"failed {secret}", success=False),
    ]
    results = aggregate_architectures(
        runs, architecture_templates(), lower_percentile=0.25, severe_failure_threshold=0.2
    )
    paths = write_benchmark_artifacts(
        tmp_path / "artifacts",
        runs=runs,
        architecture_results=results,
        scrubber=SecretScrubber([secret]),
    )
    assert set(paths) == {
        "runs.jsonl", "model_summary.csv", "architecture_summary.csv",
        "ablation_results.csv", "error_correlation.csv", "failure_overlap.csv",
        "pareto_frontier.json", "calibration.json", "tail_risk.csv",
        "failure_cases.json", "benchmark_summary.json", "BENCHMARK_REPORT.md",
    }
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths.values())
    assert secret not in combined
    assert "[redacted]" in combined
    summary = json.loads(paths["benchmark_summary.json"].read_text())
    assert summary["evidence_state"] == "BENCHMARK"
    assert "confidence_intervals" in summary
    assert summary["baselines"]["B0_strongest_single"] == "A0"


def test_checked_pricing_records_provenance(tmp_path):
    config = tmp_path / "pricing.json"
    config.write_text(json.dumps({"models": [{
        "model": "measured-model", "input_cost_per_1k": 0.1,
        "output_cost_per_1k": 0.2, "source": "provider-price-page",
        "checked_at": "2026-01-01T00:00:00Z",
    }]}), encoding="utf-8")
    pricing = PricingTable.from_checked_json(config)
    assert pricing.estimate_cost("measured-model", 1000, 500) == pytest.approx(0.2)
    assert pricing.provenance("measured-model").source == "provider-price-page"
    assert pricing.estimate_cost("unknown", 1000, 500) is None


def test_openai_adapter_normalizes_mocked_call_without_exposing_key(monkeypatch):
    secret = "credential-value-never-log"
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        return httpx.Response(200, json={
            "model": "test-model",
            "choices": [{"message": {"content": "answer"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        })

    monkeypatch.setenv("OPENAI_API_KEY", secret)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def exercise():
        provider = OpenAIProvider(model="test-model", base_url="https://example.test", client=client)
        try:
            return await invoke_normalized(
                provider,
                [Message(role="user", content="offline test")],
                task_type="classification",
            )
        finally:
            await client.aclose()

    call = asyncio.run(exercise())
    assert captured["authorization"] == f"Bearer {secret}"
    assert call.success is True
    assert call.provider == "openai"
    assert call.input_tokens == 3
    assert secret not in json.dumps(call.to_dict())


def test_available_providers_uses_groq_environment_without_exposing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "opaque-groq-credential")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")

    providers = available_providers()

    assert [(provider.name, provider.model) for provider in providers] == [
        ("groq", "openai/gpt-oss-20b")
    ]
    assert "opaque-groq-credential" not in repr(providers)


def test_anthropic_adapter_normalizes_mocked_call(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "opaque-anthropic-credential")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "opaque-anthropic-credential"
        return httpx.Response(200, json={
            "model": "claude-test",
            "content": [{"type": "text", "text": "answer"}],
            "usage": {"input_tokens": 4, "output_tokens": 2},
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def exercise():
        provider = AnthropicProvider(model="claude-test", base_url="https://example.test", client=client)
        try:
            return await invoke_normalized(provider, [Message("user", "test")], task_type="classification")
        finally:
            await client.aclose()

    call = asyncio.run(exercise())
    assert (call.provider, call.model, call.input_tokens, call.output_tokens) == (
        "anthropic", "claude-test", 4, 2
    )


def test_gemini_adapter_normalizes_mocked_call(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "opaque-gemini-credential")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "opaque-gemini-credential"
        return httpx.Response(200, json={
            "modelVersion": "gemini-test",
            "candidates": [{"content": {"parts": [{"text": "answer"}]}}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1},
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def exercise():
        provider = GeminiProvider(model="gemini-test", base_url="https://example.test", client=client)
        try:
            return await invoke_normalized(provider, [Message("user", "test")], task_type="classification")
        finally:
            await client.aclose()

    call = asyncio.run(exercise())
    assert (call.provider, call.model, call.input_tokens, call.output_tokens) == (
        "gemini", "gemini-test", 3, 1
    )
