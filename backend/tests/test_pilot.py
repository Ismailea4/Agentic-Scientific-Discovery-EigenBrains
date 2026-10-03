from pathlib import Path

import pytest

from app.benchmark.controls import BenchmarkLimitError, BenchmarkLimits, authorize_projection
from app.benchmark.corpus import build_generic_prior_v0
from app.benchmark.models import BenchmarkRun
from app.benchmark.pilot import load_shortlist, pilot_projection, select_pilot_cases
from app.benchmark.pilot_report import build_pilot_report
from app.instrumentation.pricing import PricingTable


ROOT = Path(__file__).resolve().parents[2]


def test_pilot_selects_two_paired_dev_cases_per_task():
    cases = select_pilot_cases(build_generic_prior_v0(), per_task=2)
    assert len(cases) == 24
    assert all(str(getattr(case.split, "value", case.split)) == "dev" for case in cases)
    assert len({str(getattr(case.task_type, "value", case.task_type)) for case in cases}) == 12


def test_pilot_projection_is_costed_and_requires_explicit_limits():
    cases = select_pilot_cases(build_generic_prior_v0(), per_task=2)
    specs = load_shortlist(ROOT / "benchmark" / "configs" / "provider_shortlist_v0.json")
    pricing = PricingTable.from_checked_json(ROOT / "benchmark" / "configs" / "pricing_v0.json")
    projection = pilot_projection(
        specs, cases, pricing, input_token_cap=1024, output_token_cap=256
    )
    assert sum(item.projected_calls for item in projection) == 120
    assert sum(float(item.projected_cost_usd or 0) for item in projection) == pytest.approx(0.18763776)
    with pytest.raises(BenchmarkLimitError, match="MAX_BENCHMARK_SPEND_USD"):
        authorize_projection(projection, BenchmarkLimits(None, 120, 24, 1))
    authorize_projection(projection, BenchmarkLimits(0.20, 120, 24, 1))
    with pytest.raises(BenchmarkLimitError, match="MAX_PROVIDER_REQUESTS"):
        authorize_projection(
            projection,
            BenchmarkLimits(0.20, 120, 24, 1, max_provider_requests=119),
        )


def test_baseline_environment_limit_names_take_precedence(monkeypatch):
    monkeypatch.setenv("MAX_BENCHMARK_SPEND_USD", "0.20")
    monkeypatch.setenv("MAX_TOTAL_CALLS", "999")
    monkeypatch.setenv("MAX_TOTAL_INFERENCE_CALLS", "245")
    monkeypatch.setenv("MAX_PROVIDER_REQUESTS", "246")
    monkeypatch.setenv("MAX_CONCURRENCY", "1")

    limits = BenchmarkLimits.from_environment()

    assert limits.max_total_calls == 245
    assert limits.max_provider_requests == 246


def _report_run(
    model: str,
    case_id: str,
    task_type: str,
    *,
    output: str,
    passed: bool,
) -> BenchmarkRun:
    return BenchmarkRun(
        benchmark_case_id=case_id,
        task_type=task_type,
        architecture_id="A0",
        agent_role="solver",
        provider="offline-test",
        model=model,
        output=output,
        success=True,
        error_type=None,
        latency_ms=10.0,
        input_tokens=3,
        output_tokens=2,
        estimated_cost_usd=0.000001,
        score=1.0 if passed else 0.0,
        passed=passed,
    )


def test_pilot_report_preserves_primary_score_and_separates_alias_sensitivity():
    cases = [
        ("dev-critique-01", "critique", "Hasty generalization", False),
        ("dev-planning-01", "planning", "pilot, projection, full", False),
        ("dev-structured-01", "structured_extraction", "ok", True),
    ]
    runs = [
        _report_run("alias-model", case_id, task, output=output, passed=passed)
        for case_id, task, output, passed in cases
    ] + [
        _report_run("exact-model", case_id, task, output="ok", passed=True)
        for case_id, task, _, _ in cases
    ]

    report = build_pilot_report(runs, resamples=100, seed=11)
    rows = {row["model"]: row for row in report["model_statistics"]}

    alias = rows["offline-test/alias-model"]
    assert alias["passed"] == 1
    assert alias["sensitivity_passed"] == 3
    assert alias["sensitivity_adjustments"] == 2
    assert report["scoring_sensitivity"]["status"] == "post_hoc_audit_not_primary"
