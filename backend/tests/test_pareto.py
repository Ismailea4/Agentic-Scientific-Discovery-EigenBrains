import pytest

from app.optimization import (
    AgentProfile,
    ArchitectureCandidate,
    ArchitectureMetrics,
    ErrorCovarianceMatrix,
    OptimizationConstraints,
    OptimizationWeights,
    TailRiskEstimate,
    pareto_frontier,
    select_best,
    weighted_utility,
)


def _candidate(identifier: str, quality: float, cost: float, latency: float, risk: float, **kwargs):
    return ArchitectureCandidate(
        id=identifier,
        name=identifier,
        metrics=ArchitectureMetrics(quality=quality, cost=cost, latency=latency, risk=risk),
        **kwargs,
    )


def test_pareto_marks_dominated_candidate_and_keeps_tradeoffs():
    candidates = [
        _candidate("lean", 0.5, 1.0, 10.0, 0.25),
        _candidate("careful", 1.0, 2.0, 20.0, 0.125),
        _candidate("heavy", 0.75, 4.0, 40.0, 0.5),
    ]

    result = pareto_frontier(candidates)

    assert result.frontier == ("careful", "lean")
    assert result.dominated == ("heavy",)


def test_equal_objectives_do_not_dominate():
    result = pareto_frontier(
        [
            _candidate("a", 1.0, 1.0, 1.0, 1.0),
            _candidate("b", 1.0, 1.0, 1.0, 1.0),
        ]
    )

    assert result.frontier == ("a", "b")
    assert result.dominated == ()


def test_single_candidate_is_on_the_frontier():
    result = pareto_frontier([_candidate("only", 0.5, 1.0, 1.0, 0.1)])

    assert result.frontier == ("only",)
    assert result.dominated == ()


def test_duplicate_architecture_ids_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        pareto_frontier(
            [
                _candidate("same", 1.0, 1.0, 1.0, 1.0),
                _candidate("same", 0.5, 2.0, 2.0, 2.0),
            ]
        )


def test_utility_uses_caller_weights():
    metrics = ArchitectureMetrics(quality=1.0, cost=2.0, latency=4.0, risk=0.5)
    weights = OptimizationWeights(
        quality_weight=1.0, lambda_risk=1.0, eta_cost=0.25, rho_latency=0.125
    )

    assert weighted_utility(metrics, weights) == pytest.approx(1.0 - 0.5 - 0.5 - 0.5)


def test_negative_weights_are_rejected():
    with pytest.raises(ValueError, match="eta_cost"):
        OptimizationWeights(eta_cost=-1.0).validate()


def test_selection_is_deterministic_and_prefers_frontier_utility():
    candidates = [
        _candidate("lean", 0.5, 1.0, 10.0, 0.25),
        _candidate("careful", 1.0, 2.0, 20.0, 0.125),
        _candidate("heavy", 0.75, 4.0, 40.0, 0.5),
    ]

    by_quality = select_best(candidates, OptimizationWeights())
    by_cost = select_best(candidates, OptimizationWeights(quality_weight=1.0, eta_cost=1.0))

    assert by_quality.selected_id == "careful"
    assert by_quality.frontier_ids == ("careful", "lean")
    assert by_quality.dominated_ids == ("heavy",)
    # lean: 0.5 - 1.0, careful: 1.0 - 2.0. Lean wins the weighted comparison.
    assert by_cost.selected_id == "lean"
    assert by_cost.utility == pytest.approx(0.5 - 1.0)


def test_selection_tie_breaks_by_candidate_id():
    candidates = [
        _candidate("b", 1.0, 1.0, 1.0, 1.0),
        _candidate("a", 1.0, 1.0, 1.0, 1.0),
    ]

    result = select_best(candidates, OptimizationWeights())

    assert result.selected_id == "a"


def test_security_constraint_rejects_a_higher_utility_architecture():
    exposed = _candidate(
        "exposed",
        1.0,
        0.25,
        5.0,
        0.0,
        required_capabilities=("export",),
        privacy_class="public",
    )
    held = _candidate(
        "held",
        0.25,
        1.0,
        30.0,
        0.25,
        required_capabilities=("read",),
        privacy_class="restricted",
    )
    result = select_best(
        [exposed, held],
        OptimizationWeights(),
        OptimizationConstraints(
            available_capabilities=frozenset({"read"}),
            denied_capabilities=frozenset({"export"}),
            accepted_privacy_classes=frozenset({"restricted"}),
        ),
    )

    assert result.selected_id == "held"
    assert result.feasible_ids == ("held",)
    assert any("missing capability 'export'" in reason for _, reason in result.rejected)
    assert any("denied capability 'export'" in reason for _, reason in result.rejected)
    assert any("privacy class" in reason for _, reason in result.rejected)


def test_numeric_constraints_filter_before_utility():
    cheap = _candidate("cheap", 0.5, 1.0, 10.0, 0.25)
    pricey = _candidate("pricey", 1.0, 99.0, 10.0, 0.1)

    result = select_best(
        [cheap, pricey],
        OptimizationWeights(),
        OptimizationConstraints(max_cost=10.0),
    )

    assert result.selected_id == "cheap"
    assert result.feasible_ids == ("cheap",)
    assert any("cost above maximum" in reason for _, reason in result.rejected)


def test_empty_candidate_set_selects_nothing():
    result = select_best([])

    assert result.selected_id is None
    assert result.utility is None
    assert result.reasons == ("no architecture satisfied the hard constraints",)


def test_covariance_requires_a_caller_supplied_square_symmetric_matrix():
    matrix = ErrorCovarianceMatrix(labels=("a", "b"), matrix=((1.0, 0.2), (0.2, 1.0)))

    assert matrix.pair("a", "b") == pytest.approx(0.2)
    with pytest.raises(ValueError, match="square"):
        ErrorCovarianceMatrix(labels=("a", "b"), matrix=((1.0,),))
    with pytest.raises(ValueError, match="unique"):
        ErrorCovarianceMatrix(labels=("a", "a"), matrix=((1.0, 0.0), (0.0, 1.0)))
    with pytest.raises(ValueError, match="symmetric"):
        ErrorCovarianceMatrix(labels=("a", "b"), matrix=((1.0, 0.2), (0.3, 1.0)))


def test_covariance_accepts_an_optional_correlation_matrix():
    matrix = ErrorCovarianceMatrix(
        labels=("a", "b"),
        matrix=((1.0, 0.2), (0.2, 1.0)),
        correlations=((1.0, 0.5), (0.5, 1.0)),
    )

    assert matrix.correlations is not None
    with pytest.raises(ValueError, match="square"):
        ErrorCovarianceMatrix(
            labels=("a", "b"),
            matrix=((1.0, 0.2), (0.2, 1.0)),
            correlations=((1.0,),),
        )


def test_tail_risk_estimate_does_not_invent_a_score():
    empty = TailRiskEstimate()
    supplied = TailRiskEstimate(score=0.2, alpha=0.95, method="caller-cvar")

    assert empty.is_specified() is False
    assert empty.score is None
    assert supplied.is_specified() is True
    assert supplied.score == pytest.approx(0.2)


def test_agent_profile_starts_without_benchmark_numbers():
    profile = AgentProfile(name="unmeasured")

    assert profile.metrics.expected_quality is None
    assert profile.metrics.cost is None
    assert profile.metrics.tail_risk is None
    assert profile.metrics.sample_size is None
    assert profile.metrics.provenance is None
    assert profile.metrics.required_capabilities == ()
