import asyncio
import json
import random
from dataclasses import replace
from pathlib import Path

import pytest

from app.benchmark.analysis import aggregate_models
from app.benchmark.artifacts import SecretScrubber
from app.benchmark.baselines import identify_baselines
from app.benchmark.cache import ImmutableBenchmarkCache, benchmark_cache_key
from app.benchmark.calibration import abstention_metrics, calibration_metrics
from app.benchmark.controls import (
    BenchmarkLimitError,
    BenchmarkLimits,
    authorize_projection,
    project_full_benchmark,
)
from app.benchmark.dataset import load_benchmark_cases
from app.benchmark.key_status import (
    CredentialStatus,
    KeyStatusRecord,
    classify_http_status,
    write_key_status_inventory,
)
from app.benchmark.models import ArchitectureBenchmarkResult, BenchmarkCase, BenchmarkRun, SystemOutcome
from app.benchmark.runner import ArchitectureExecution, BenchmarkRunner
from app.benchmark.retry import RetryPolicy, call_with_retry
from app.benchmark.statistics import (
    bootstrap_confidence_interval,
    mcnemar_exact,
    paired_bootstrap_difference,
)
from app.benchmark.templates import architecture_templates
from app.benchmark.validation import ProbeObservation, validate_labeled_credential
from app.optimization.covariance import analyze_error_vectors
from app.optimization.tail_risk import TailRiskEstimate


def _run(case_id: str, *, score: float = 1.0, confidence: float | None = None) -> BenchmarkRun:
    return BenchmarkRun(
        benchmark_case_id=case_id,
        task_type="classification",
        architecture_id="A0",
        agent_role="solver",
        provider="offline",
        model="fixed-model",
        output="answer",
        success=True,
        error_type=None,
        latency_ms=20.0,
        input_tokens=10,
        output_tokens=2,
        estimated_cost_usd=0.01,
        score=score,
        passed=score == 1.0,
        confidence=confidence,
        metadata={"final_output": True, "split": "dev"},
    )


def _result(identifier: str, quality: float, cost: float) -> ArchitectureBenchmarkResult:
    return ArchitectureBenchmarkResult(
        architecture_id=identifier,
        architecture_name=identifier,
        expected_quality=quality,
        cost=cost,
        latency=100.0,
        failure_rate=1.0 - quality,
        risk=1.0 - quality,
        quality_variance=0.01,
        sample_size=10,
        tail_risk=TailRiskEstimate(score=1.0 - quality, sample_size=10),
    )


def test_generic_prior_has_all_taxonomy_and_locked_split_sizes():
    path = Path(__file__).parents[2] / "benchmark" / "cases" / "generic_prior.json"
    cases = load_benchmark_cases(path)
    task_types = {str(getattr(case.task_type, "value", case.task_type)) for case in cases}
    assert task_types == {
        "structured_extraction", "classification", "numerical_reasoning",
        "mathematical_reasoning", "logical_reasoning", "planning",
        "evidence_verification", "critique", "synthesis", "tool_use_reasoning",
        "code_understanding_debugging", "uncertainty_abstention",
    }
    counts = {
        split: sum(str(getattr(case.split, "value", case.split)) == split for case in cases)
        for split in ("dev", "tuning", "held_out")
    }
    assert counts == {"dev": 6, "tuning": 3, "held_out": 3}


def test_runner_defaults_to_dev_and_does_not_touch_held_out():
    cases = [
        BenchmarkCase("dev-case", "classification", "x", expected_answer="ok", split="dev"),
        BenchmarkCase("held-case", "classification", "x", expected_answer="ok", split="held_out"),
    ]
    observed = []

    def executor(case, architecture, repeat, seed):
        observed.append(case.id)
        return ArchitectureExecution(calls=(), final_output="ok")

    runs = asyncio.run(
        BenchmarkRunner().run(cases, architecture_templates()[:1], executor, repeats=1, seed=0)
    )
    assert observed == ["dev-case"]
    assert {run.benchmark_case_id for run in runs} == {"dev-case"}


def test_architecture_templates_match_bounded_a0_to_a6_space():
    templates = architecture_templates()
    assert [template.id for template in templates] == [f"A{index}" for index in range(7)]
    assert templates[0].baseline_kind == "single_model"
    assert templates[2].baseline_kind == "static_multi_agent"
    assert templates[5].metadata["conditional_role"] == "critic"


def test_key_status_contains_no_value_derived_identifier_and_429_is_not_invalid(tmp_path):
    secret = "opaque-test-credential"
    assert classify_http_status(429) is CredentialStatus.RATE_LIMITED
    record = KeyStatusRecord(
        provider="test-provider",
        auth_status=CredentialStatus.VALID_AUTH,
        inference_status=CredentialStatus.VALID_INFERENCE,
        accessible_models=("model-a",),
        rate_limit_status=None,
        billing_or_quota_status=None,
        tested_at="2026-01-01T00:00:00Z",
        notes=f"never serialize {secret}",
    )
    path = write_key_status_inventory(
        tmp_path / "key_status.json", [record], scrubber=SecretScrubber([secret])
    )
    encoded = path.read_text(encoding="utf-8")
    assert secret not in encoded
    assert "fingerprint" not in encoded


def test_minimal_validation_uses_one_inference_and_keeps_only_metadata():
    class Probe:
        provider = "offline-provider"

        def __init__(self):
            self.inference_calls = 0

        async def authenticate(self, credential):
            return ProbeObservation(200, 2.0, ("small-model",), succeeded=True)

        async def tiny_inference(self, credential, model):
            self.inference_calls += 1
            return ProbeObservation(200, 3.0, succeeded=True)

    probe = Probe()
    secret = "opaque-test-credential"
    result = asyncio.run(
        validate_labeled_credential(secret, probe, relevant_models=("small-model",))
    )
    assert probe.inference_calls == 1
    assert result.auth_status is CredentialStatus.VALID_AUTH
    assert result.inference_status is CredentialStatus.VALID_INFERENCE
    assert secret not in json.dumps(result.to_dict())


def test_pilot_projection_requires_explicit_known_spend_limit():
    projections = project_full_benchmark([_run("pilot")], target_calls_per_model=10)
    with pytest.raises(BenchmarkLimitError, match="MAX_BENCHMARK_SPEND_USD"):
        authorize_projection(
            projections,
            BenchmarkLimits(None, max_total_calls=100, max_calls_per_model=20, max_concurrency=1),
        )
    authorize_projection(
        projections,
        BenchmarkLimits(1.0, max_total_calls=100, max_calls_per_model=20, max_concurrency=1),
    )
    with pytest.raises(BenchmarkLimitError, match="cost exceeds"):
        authorize_projection(
            projections,
            BenchmarkLimits(0.01, max_total_calls=100, max_calls_per_model=20, max_concurrency=1),
        )


def test_cache_key_changes_with_configuration_and_entries_are_immutable(tmp_path):
    first = benchmark_cache_key(
        case_id="c1", model="m1", model_configuration={"temperature": 0},
        prompt_configuration={"version": 1},
    )
    second = benchmark_cache_key(
        case_id="c1", model="m1", model_configuration={"temperature": 0.1},
        prompt_configuration={"version": 1},
    )
    assert first != second
    secret = "cache-secret-value"
    cache = ImmutableBenchmarkCache(tmp_path, scrubber=SecretScrubber([secret]))
    path = cache.put(first, {"result": f"safe-{secret}"})
    assert secret not in path.read_text(encoding="utf-8")
    cache.put(first, {"result": f"safe-{secret}"})
    with pytest.raises(ValueError, match="immutable"):
        cache.put(first, {"result": "different"})


def test_retry_is_bounded_and_uses_exponential_delays():
    calls = 0
    delays = []

    async def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TimeoutError("temporary")
        return "ok"

    async def sleep(delay):
        delays.append(delay)

    result = asyncio.run(
        call_with_retry(
            operation,
            policy=RetryPolicy(max_attempts=3, initial_delay_seconds=1, max_delay_seconds=4, jitter_fraction=0),
            should_retry=lambda exc: isinstance(exc, TimeoutError),
            sleep=sleep,
            rng=random.Random(0),
        )
    )
    assert result == "ok"
    assert calls == 3
    assert delays == [1.0, 2.0]


def test_calibration_abstention_and_model_summary_use_normalized_runs():
    answered = _run("a", score=1.0, confidence=0.8)
    wrong = _run("b", score=0.0, confidence=0.7)
    refused = replace(
        _run("c", score=1.0, confidence=None),
        outcome=SystemOutcome.INSUFFICIENT_EVIDENCE,
        abstained=True,
    )
    calibration = calibration_metrics([answered, wrong, refused], bin_count=5)
    abstention = abstention_metrics([answered, wrong, refused])
    (model,) = aggregate_models([answered, wrong, refused])
    assert calibration.sample_size == 2
    assert calibration.expected_calibration_error is not None
    assert abstention.coverage == pytest.approx(2 / 3)
    assert abstention.abstention_rate == pytest.approx(1 / 3)
    assert model.abstention_rate == pytest.approx(1 / 3)


def test_statistics_are_deterministic_and_paired():
    first = bootstrap_confidence_interval([0, 1, 1, 1], resamples=100, seed=9)
    second = bootstrap_confidence_interval([0, 1, 1, 1], resamples=100, seed=9)
    paired = paired_bootstrap_difference([1, 1, 0], [1, 0, 0], resamples=100, seed=3)
    mcnemar = mcnemar_exact([True, True, False, False], [True, False, True, False])
    assert first == second
    assert paired.estimate == pytest.approx(1 / 3)
    assert mcnemar.left_only_correct == 1
    assert mcnemar.right_only_correct == 1
    assert mcnemar.p_value == 1.0


def test_correlation_includes_jaccard_and_required_baselines_are_mapped():
    correlation = analyze_error_vectors(
        {
            "a": {"c1": 1.0, "c2": 0.0, "c3": 1.0},
            "b": {"c1": 1.0, "c2": 1.0, "c3": 0.0},
        },
        failure_threshold=0.5,
    )
    assert correlation.pair_metrics("a", "b")["jaccard_similarity"] == pytest.approx(1 / 3)
    baselines = identify_baselines([
        _result("A0", 0.8, 2.0), _result("A2", 0.85, 3.0), _result("A6", 0.9, 2.5)
    ])
    assert baselines["B0_strongest_single"] == "A0"
    assert baselines["B1_static_multi_agent"] == "A2"
    assert baselines["B2_adaptive_eigenbrains"] == "A6"
    assert baselines["B3_cheapest_viable"] == "A0"
    assert baselines["B4_maximum_quality"] == "A6"
