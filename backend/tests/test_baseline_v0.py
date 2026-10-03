import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.benchmark.analysis import aggregate_model_reliability
from app.benchmark.baseline_artifacts import write_prechallenge_baseline_v0
from app.benchmark.baseline_plan import build_protocol_manifest, build_reduced_budget
from app.benchmark.artifacts import SecretScrubber
from app.benchmark.bounds import (
    ArchitectureBounds,
    bootstrap_dominance_probabilities,
    estimate_architecture_bounds,
    robust_frontier,
    robustly_dominates,
    wilson_interval,
)
from app.benchmark.corpus import build_generic_prior_v0
from app.benchmark.evaluators import SCORING_V1_HASH, EvaluatorRegistry
from app.benchmark.distributions import summarize_runs
from app.benchmark.downside import empirical_downside_risk
from app.benchmark.marginal import marginal_agent_value
from app.benchmark.metrics import aggregate_architectures
from app.benchmark.models import ArchitectureBenchmarkResult, BenchmarkRun, SystemOutcome
from app.benchmark.observations import execution_observations
from app.benchmark.policies import baseline_policies_v0
from app.benchmark.priors import (
    construct_architecture_priors,
    construct_binary_evidence_priors,
    update_beta_prior,
)
from app.benchmark.racing import confidence_bound_race
from app.benchmark.stress import StressScenario, recompute_stress_scenarios
from app.benchmark.templates import architecture_templates
from app.optimization.covariance import ErrorCovarianceMatrix, analyze_error_vectors
from app.optimization.models import OptimizationWeights
from app.optimization.portfolio import analyze_computational_allocation
from app.optimization.robust_router import select_architecture_robust
from app.optimization.router import RoutingRequest
from app.optimization.tail_risk import TailRiskEstimate
from app.benchmark.statistics import ConfidenceInterval
from app.instrumentation.pricing import PricingTable
from app.benchmark.selective_replay import (
    FrozenGateConfiguration,
    replay_policies,
    summarize_escalation_economics,
)
from app.optimization.covariance import (
    bootstrap_pairwise_metrics,
    diagonal_shrinkage_covariance,
)


def _run(
    architecture: str,
    case: str,
    *,
    score: float,
    cost: float,
    latency: float,
    model: str,
    repeat: int = 0,
) -> BenchmarkRun:
    return BenchmarkRun(
        benchmark_case_id=case,
        task_type="classification",
        architecture_id=architecture,
        agent_role="solver",
        provider="offline",
        model=model,
        output="ok",
        success=True,
        error_type=None,
        latency_ms=latency,
        input_tokens=10,
        output_tokens=2,
        estimated_cost_usd=cost,
        score=score,
        passed=score >= 0.5,
        outcome=SystemOutcome.ANSWER,
        repeat=repeat,
        seed=11,
        timestamp="2026-01-01T00:00:00Z",
        metadata={
            "final_output": True,
            "split": "held_out",
            "risk_level": "high",
            "difficulty": "medium",
        },
        model_configuration={"temperature": 0},
        prompt_config_hash="prompt-v1",
    )


def _result(identifier: str, quality: float, cost: float, latency: float, risk: float):
    return ArchitectureBenchmarkResult(
        architecture_id=identifier,
        architecture_name=identifier,
        expected_quality=quality,
        cost=cost,
        latency=latency,
        failure_rate=1 - quality,
        risk=risk,
        quality_variance=0.01,
        sample_size=10,
        tail_risk=TailRiskEstimate(score=risk, sample_size=10),
        task_types=("classification",),
        metadata={"difficulty_levels": ["medium"], "risk_levels": ["high"]},
    )


def _interval(estimate, lower, upper):
    return ConfidenceInterval(estimate, lower, upper, 0.95, "test", 100)


def test_baseline_corpus_has_72_objective_cases_and_locked_splits():
    cases = build_generic_prior_v0()
    assert len(cases) == 72
    assert len({case.id for case in cases}) == 72
    counts = {
        split: sum(str(getattr(case.split, "value", case.split)) == split for case in cases)
        for split in ("dev", "tuning", "held_out")
    }
    assert counts == {"dev": 48, "tuning": 12, "held_out": 12}
    assert len({str(getattr(case.task_type, "value", case.task_type)) for case in cases}) == 12


def test_distribution_summary_contains_requested_location_dispersion_and_coverage():
    runs = [
        _run("A0", "c1", score=1.0, cost=0.01, latency=10, model="m0"),
        replace(
            _run("A0", "c2", score=0.0, cost=0.03, latency=30, model="m0"),
            outcome=SystemOutcome.INSUFFICIENT_EVIDENCE,
            abstained=True,
        ),
    ]
    (summary,) = summarize_runs(
        runs, severe_failure_threshold=0.2, task_specific=False
    )
    assert summary.quality_mean == pytest.approx(0.5)
    assert summary.quality_median == pytest.approx(0.5)
    assert summary.latency_median_ms == pytest.approx(20)
    assert summary.cost_p90_usd == pytest.approx(0.03)
    assert summary.coverage == pytest.approx(0.5)
    assert summary.quality_conditional_on_answering == 1.0


def test_wilson_bounds_and_robust_dominance_are_conservative():
    wilson = wilson_interval(8, 10, confidence_level=0.95)
    assert wilson.lower < 0.8 < wilson.upper
    strong = ArchitectureBounds(
        "strong", 100, _interval(0.9, 0.88, 0.92), _interval(0.05, 0.03, 0.07),
        _interval(0.01, 0.0, 0.02), _interval(1.0, 0.9, 1.1), _interval(100, 90, 110),
    )
    weak = ArchitectureBounds(
        "weak", 100, _interval(0.7, 0.68, 0.72), _interval(0.2, 0.17, 0.23),
        _interval(0.15, 0.12, 0.18), _interval(2.0, 1.9, 2.1), _interval(200, 190, 210),
    )
    assert robustly_dominates(strong, weak)
    frontier = robust_frontier([strong, weak])
    assert frontier.frontier_ids == ("strong",)
    assert frontier.dominated_ids == ("weak",)


def test_downside_metrics_label_small_cvar_tail_unstable():
    qualities = [index / 99 for index in range(100)]
    risk = empirical_downside_risk(
        qualities,
        severe_failure_threshold=0.1,
        minimum_tail_observations=7,
        resamples=100,
        seed=3,
    )
    assert risk.var_loss["0.90"] >= 0.89
    assert risk.cvar_loss["0.90"] >= risk.var_loss["0.90"]
    assert "0.95" in risk.unstable_levels
    assert risk.downside_deviation > 0


def test_portfolio_math_uses_normalized_cost_latency_and_covariance():
    covariance = ErrorCovarianceMatrix(
        labels=("a", "b"),
        matrix=((0.04, 0.0), (0.0, 0.09)),
    )
    allocation = analyze_computational_allocation(
        weights=(0.5, 0.5),
        mean_quality=(0.8, 0.9),
        mean_cost=(1.0, 3.0),
        mean_latency=(100.0, 300.0),
        covariance=covariance,
        allowed_budget=4.0,
        latency_limit=400.0,
        lambda_risk=1.0,
        eta_cost=0.2,
        rho_latency=0.2,
    )
    assert allocation.expected_quality == pytest.approx(0.85)
    assert allocation.normalized_cost == pytest.approx(0.5)
    assert allocation.normalized_latency == pytest.approx(0.5)
    assert allocation.interpretation == "routing probabilities over a workload"


def test_marginal_agent_value_uses_paired_cases_and_can_reject_theatre():
    full_runs = [
        _run("A1", f"c{i}", score=score, cost=0.02, latency=20, model="m1")
        for i, score in enumerate((1.0, 1.0, 0.0, 0.0))
    ]
    ablated_runs = [
        _run("A1-minus-verifier", f"c{i}", score=score, cost=0.01, latency=10, model="m1")
        for i, score in enumerate((1.0, 1.0, 0.0, 0.0))
    ]
    full = execution_observations(full_runs, severe_failure_threshold=0.2)
    ablated = execution_observations(ablated_runs, severe_failure_threshold=0.2)
    value = marginal_agent_value(
        full,
        ablated,
        architecture_id="A1",
        ablation_id="A1-minus-verifier",
        component="verifier",
        resamples=100,
        seed=1,
    )
    assert value.quality_delta == 0
    assert value.cost_delta_usd == pytest.approx(0.01)
    assert value.verdict == "NOT JUSTIFIED BY BASELINE"


def test_weak_priors_are_task_specific_and_strength_limited():
    runs = [_run("A0", "c1", score=1.0, cost=0.01, latency=10, model="m0")]
    with pytest.raises(ValueError, match="exceeds"):
        construct_architecture_priors(
            runs,
            source_benchmark_version="v0",
            benchmark_date="2026-01-01",
            prior_strength=10,
            maximum_prior_strength=5,
            severe_failure_threshold=0.2,
        )
    priors = construct_architecture_priors(
        runs,
        source_benchmark_version="v0",
        benchmark_date="2026-01-01",
        prior_strength=2,
        maximum_prior_strength=5,
        severe_failure_threshold=0.2,
    )
    assert {prior.scope for prior in priors} == {"global", "task_risk"}
    updated = update_beta_prior(priors[0].success, successes=0, failures=2)
    assert updated.beta == priors[0].success.beta + 2
    assert updated.effective_prior_strength == 2


def test_confidence_racing_eliminates_only_after_minimum_sample():
    bounds = [
        ArchitectureBounds("a", 10, _interval(0.9, 0.85, 0.95), _interval(0.1, 0.05, 0.15), _interval(0.05, 0.0, 0.1), _interval(1, 0.9, 1.1), _interval(100, 90, 110)),
        ArchitectureBounds("b", 10, _interval(0.6, 0.55, 0.65), _interval(0.3, 0.25, 0.35), _interval(0.25, 0.2, 0.3), _interval(2, 1.9, 2.1), _interval(200, 190, 210)),
    ]
    minimum = confidence_bound_race(
        bounds,
        sample_counts={"a": 2, "b": 10},
        minimum_sample=5,
        confidence_width_target=0.05,
        calls_remaining=10,
    )
    assert minimum.eliminated_ids == ()
    assert minimum.allocate_more_ids == ("a",)
    raced = confidence_bound_race(
        bounds,
        sample_counts={"a": 10, "b": 10},
        minimum_sample=5,
        confidence_width_target=0.2,
        calls_remaining=10,
    )
    assert raced.eliminated_ids == ("b",)


def test_robust_router_uses_bounds_and_hard_constraints():
    measured = [
        _result("A0", 0.8, 1.0, 100, 0.1),
        _result("A1", 0.9, 2.0, 200, 0.05),
    ]
    bounds = [
        ArchitectureBounds("A0", 20, _interval(0.8, 0.75, 0.85), _interval(0.2, 0.1, 0.3), _interval(0.1, 0.05, 0.15), _interval(1, 0.9, 1.1), _interval(100, 90, 110)),
        ArchitectureBounds("A1", 20, _interval(0.9, 0.82, 0.98), _interval(0.1, 0.05, 0.2), _interval(0.05, 0.01, 0.1), _interval(2, 1.8, 2.2), _interval(200, 180, 220)),
    ]
    request = RoutingRequest(
        "classification", "medium", "high", frozenset(), 3.0, 300.0
    )
    decision = select_architecture_robust(
        request,
        measured,
        bounds,
        weights=OptimizationWeights(quality_weight=1, lambda_risk=1, eta_cost=0.1, rho_latency=0.1),
    )
    assert decision.architecture_id == "A1"
    assert decision.confidence_level == 0.95


def test_paired_bootstrap_dominance_and_stress_recomputation():
    runs = []
    for index in range(6):
        runs.extend(
            [
                _run("A0", f"c{index}", score=0.6, cost=2.0, latency=200, model="m0"),
                _run("A1", f"c{index}", score=0.9, cost=1.0, latency=100, model="m1"),
            ]
        )
    probabilities = bootstrap_dominance_probabilities(
        runs, severe_failure_threshold=0.2, resamples=100, seed=2
    )
    assert probabilities["A1>A0"] == 1.0
    measured = [_result("A0", 0.6, 2.0, 200, 0.4), _result("A1", 0.9, 1.0, 100, 0.1)]
    request = RoutingRequest("classification", "medium", "high", frozenset(), 3.0, 300.0)
    (stress,) = recompute_stress_scenarios(
        request,
        measured,
        [StressScenario("A1 unavailable", available_architecture_ids=frozenset({"A0"}))],
        weights=OptimizationWeights(),
    )
    assert stress.selected_architecture_id == "A0"
    assert stress.quality_change == pytest.approx(-0.3)


def test_baseline_v0_artifact_bundle_is_complete_and_scrubbed(tmp_path):
    secret = "baseline-secret-value"
    runs = []
    for index in range(4):
        runs.extend(
            [
                _run("A0", f"c{index}", score=0.5, cost=0.01, latency=10, model="m0"),
                replace(
                    _run("A1", f"c{index}", score=1.0, cost=0.02, latency=20, model="m1"),
                    output=f"safe-{secret}",
                ),
            ]
        )
    results = aggregate_architectures(
        runs,
        architecture_templates(),
        lower_percentile=0.1,
        severe_failure_threshold=0.2,
    )
    paths = write_prechallenge_baseline_v0(
        tmp_path / "benchmark",
        runs=runs,
        architecture_results=results,
        experiment_metadata={
            "benchmark_version": "baseline-v0-test",
            "benchmark_date": "2026-01-01",
            "split": "held_out",
            "confidence_level": 0.95,
            "bootstrap_resamples": 100,
            "seed": 7,
            "severe_failure_threshold": 0.2,
            "failure_threshold": 0.5,
            "prior_strength": 2,
            "maximum_prior_strength": 5,
            "scoring_config_hash": SCORING_V1_HASH,
            "covariance_shrinkage_intensity": 0.25,
        },
        scrubber=SecretScrubber([secret]),
    )
    assert len(paths) == 22
    required = {
        "raw_runs.jsonl", "model_statistics.csv", "model_reliability.csv", "architecture_statistics.csv",
        "architecture_task_statistics.csv", "confidence_bounds.csv", "covariance.csv",
        "pairwise_uncertainty.json", "shrinkage_covariance.json",
        "failure_overlap.csv", "ablations.csv", "marginal_agent_value.csv", "escalation_economics.csv",
        "empirical_frontier.json", "robust_frontier.json", "tail_risk.csv",
        "stress_tests.csv", "routing_scenarios.csv", "priors.json", "binary_priors.json",
        "architecture_cards.json", "PRECHALLENGE_BASELINE_V0.md",
    }
    assert set(paths) == required
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths.values())
    assert secret not in combined
    robust = json.loads(paths["robust_frontier.json"].read_text(encoding="utf-8"))
    assert "probability_of_dominance" in robust


def test_conditional_failure_is_exported_with_covariance():
    analysis = analyze_error_vectors(
        {
            "a": {"x": 1.0, "y": 1.0, "z": 0.0},
            "b": {"x": 1.0, "y": 0.0, "z": 0.0},
        },
        failure_threshold=0.5,
    )
    assert analysis.pair_metrics("a", "b")["conditional_failure"] == pytest.approx(0.5)


def test_scoring_v1_is_frozen_and_preserves_primary_v0_result():
    case = next(case for case in build_generic_prior_v0() if case.id == "dev-critique-01")
    outcome = EvaluatorRegistry().resolve(case).evaluate(case, "Hasty generalization.")
    assert len(SCORING_V1_HASH) == 64
    assert outcome.passed is True
    assert outcome.metadata["evaluator_hash"] == SCORING_V1_HASH
    assert outcome.metadata["primary_v0_passed"] is False


def test_model_reliability_does_not_treat_provider_failure_as_reasoning_error():
    rows = [
        _run("A0", "c1", score=1.0, cost=0.01, latency=10, model="m0"),
        _run("A0", "c2", score=0.0, cost=0.01, latency=20, model="m0"),
        replace(
            _run("A0", "c3", score=0.0, cost=0.01, latency=30, model="m0"),
            success=False,
            error_type="ProviderError",
            estimated_cost_usd=None,
        ),
    ]
    (result,) = aggregate_model_reliability(rows, severe_failure_threshold=0.2)
    assert result.provider_success_probability == pytest.approx(2 / 3)
    assert result.correct_given_provider_success == pytest.approx(0.5)
    assert result.operational_correct_probability == pytest.approx(1 / 3)


def test_pairwise_bootstrap_and_shrinkage_keep_empirical_matrix_visible():
    vectors = {
        "a": {f"c{i}": value for i, value in enumerate((1, 1, 0, 0, 1, 0))},
        "b": {f"c{i}": value for i, value in enumerate((1, 0, 0, 0, 1, 1))},
    }
    empirical = analyze_error_vectors(vectors, failure_threshold=0.5)
    (uncertainty,) = bootstrap_pairwise_metrics(
        vectors, failure_threshold=0.5, resamples=100, seed=4
    )
    shrunk = diagonal_shrinkage_covariance(empirical, intensity=0.25)
    assert uncertainty.metrics["phi"].estimate is not None
    assert uncertainty.metrics["p_right_succeeds_given_left_fails"].lower is not None
    assert shrunk.pair("a", "b") == pytest.approx(empirical.covariance[0][1] * 0.75)
    assert empirical.covariance[0][1] != shrunk.pair("a", "b")


def test_binary_priors_are_separate_by_model_architecture_and_task():
    runs = [_run("A0", "c1", score=1.0, cost=0.01, latency=10, model="m0")]
    priors = construct_binary_evidence_priors(
        runs,
        source_benchmark_version="v0",
        scoring_config_hash=SCORING_V1_HASH,
        prior_strength=4,
        maximum_prior_strength=5,
    )
    assert {(item.entity_kind, item.scope) for item in priors} == {
        ("model", "global"),
        ("model", "task_family"),
        ("architecture", "global"),
        ("architecture", "task_family"),
    }
    assert all(item.provider_availability.effective_prior_strength == 4 for item in priors)


def test_qwen_first_selective_gpt_replay_measures_savings_without_ground_truth_gate():
    corpus = build_generic_prior_v0()
    cases = [
        next(case for case in corpus if case.id == "dev-numerical_reasoning-01"),
        next(case for case in corpus if case.id == "dev-mathematical_reasoning-01"),
    ]

    def model_run(case, provider, model, output, passed, cost, latency):
        return replace(
            _run("A0", case.id, score=float(passed), cost=cost, latency=latency, model=model),
            task_type=str(getattr(case.task_type, "value", case.task_type)),
            provider=provider,
            output=output,
            passed=passed,
            metadata={
                "final_output": True,
                "split": "dev",
                "risk_level": str(getattr(case.risk_level, "value", case.risk_level)),
                "difficulty": "medium",
            },
        )

    runs = [
        model_run(cases[0], "groq", "qwen/qwen3.8-27b", "wrong", False, 0.0010, 300),
        model_run(cases[0], "groq", "openai/gpt-oss-20b", cases[0].expected_answer, True, 0.0001, 600),
        model_run(cases[1], "groq", "qwen/qwen3.8-27b", cases[1].expected_answer, True, 0.0010, 300),
        model_run(cases[1], "groq", "openai/gpt-oss-20b", cases[1].expected_answer, True, 0.0001, 600),
    ]
    gate = FrozenGateConfiguration(
        fitted_splits=("dev", "tuning"),
        escalate_high_risk=False,
        escalate_task_families=("numerical_reasoning",),
        historical_task_family_error_ucb={},
        historical_error_ucb_threshold=0.5,
        task_family_owner={"numerical_reasoning": "groq/openai/gpt-oss-20b"},
    )
    replayed = replay_policies(cases, runs, baseline_policies_v0(), gate)
    economics = {item.policy_id: item for item in summarize_escalation_economics(replayed)}
    selective = economics["S3"]
    assert selective.incremental_quality == pytest.approx(0.5)
    assert selective.escalation_probability == pytest.approx(0.5)
    assert selective.rescue_probability == 1.0
    assert selective.cost_saving_vs_always_both_usd > 0
    assert selective.latency_saving_vs_always_both_ms > 0


def test_reduced_budget_and_manifest_are_frozen_before_provider_execution():
    root = Path(__file__).resolve().parents[2]
    pricing = PricingTable.from_checked_json(root / "benchmark" / "configs" / "pricing_v0.json")
    protocol = json.loads(
        (root / "benchmark" / "configs" / "prechallenge_baseline_v0.json").read_text(
            encoding="utf-8"
        )
    )
    budget = build_reduced_budget(pricing)
    manifest = build_protocol_manifest(build_generic_prior_v0(), protocol, budget)
    assert budget["core_total"]["inference_calls"] == 269
    assert budget["core_total"]["dollar_ceiling"] == pytest.approx(0.21330048)
    assert budget["recommended_initial_approval"]["inference_calls"] == 245
    assert budget["recommended_initial_approval"]["dollar_ceiling"] == pytest.approx(0.18933888)
    assert budget["authorization"] == "NOT_APPROVED"
    assert manifest["scoring"]["sha256"] == SCORING_V1_HASH
    assert manifest["observations"]["status"] == "NOT_RUN"
    assert manifest["policies"]["final_evaluation_split"] == "held_out"
