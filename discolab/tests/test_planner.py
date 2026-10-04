import pytest

from discolab.planner import (assumed_effect, eig_bits, entropy_bits, likelihood_table, outcome_probs,
                              posterior, sesoi_standardised)
from discolab.prereg import load_prereg

ALPHA = 0.05


def test_outcome_probabilities_are_a_distribution_with_correct_null_rate():
    for delta in (0.0, 0.3, 1.0):
        p = outcome_probs(delta, 40, 0.2, ALPHA)
        assert sum(p.values()) == pytest.approx(1.0)
    assert outcome_probs(0.0, 40, 0.2, ALPHA)["supported"] == pytest.approx(0.025, abs=1e-3)


def test_eig_properties():
    t = likelihood_table(0.5, 60, 0.2, ALPHA)
    assert eig_bits(0.0, t) == pytest.approx(0.0, abs=1e-9) and eig_bits(1.0, t) == pytest.approx(0.0, abs=1e-9)
    assert 0 < eig_bits(0.5, t) <= entropy_bits(0.5)
    assert eig_bits(0.5, t) > eig_bits(0.1, t)  # settled questions are worth less
    weak = likelihood_table(0.1, 4, 0.2, ALPHA)
    assert eig_bits(0.5, weak) < eig_bits(0.5, t)  # underpowered designs are worth less


def test_posterior_direction():
    t = likelihood_table(0.5, 60, 0.2, ALPHA)
    assert posterior(0.5, "supported", t) > 0.9
    assert posterior(0.5, "refuted", t) < 0.1


def test_inconclusive_from_a_powered_design_lowers_the_posterior():
    # Regression for run 1 (prereg v1): an inconclusive verdict raised H3 from 0.5 to 0.667.
    t = likelihood_table(0.5, 72, 0.2, ALPHA)
    assert posterior(0.5, "inconclusive", t) < 0.5


def _hyp(hid, family, effect=None, raw=None, seq=1):
    h = {"id": hid, "family": family, "history": [], "posterior": 0.5}
    if effect is not None:
        h["history"].append({"experiment": "E1", "effect": effect, "seq": seq,
                             "interval": {"estimate": raw, "low": raw, "high": raw}})
        h["latest_effect"] = effect
    return h


def test_assumed_effect_is_order_independent_family_mean():
    pol = load_prereg()["planner_policy"]
    a = {"H1": _hyp("H1", "prediction"), "H2": _hyp("H2", "prediction", 0.8, 0.03, seq=1),
         "H3": _hyp("H3", "prediction", 0.2, 0.008, seq=2)}
    b = {"H1": _hyp("H1", "prediction"), "H2": _hyp("H2", "prediction", 0.8, 0.03, seq=2),
         "H3": _hyp("H3", "prediction", 0.2, 0.008, seq=1)}
    ea, _ = assumed_effect("H1", a, pol)
    eb, _ = assumed_effect("H1", b, pol)
    assert ea == eb == pytest.approx(0.5)
    own, src = assumed_effect("H2", a, pol)
    assert own == pytest.approx(0.8) and "H2" in src


def test_assumed_effect_is_floored_and_defaults_before_data():
    pol = load_prereg()["planner_policy"]
    hyps = {"H1": _hyp("H1", "control"), "H2": _hyp("H2", "control", -0.4, -1.0)}
    e, _ = assumed_effect("H1", hyps, pol)
    assert e == pol["min_assumed_standardised_effect"]
    e0, src = assumed_effect("H1", {"H1": _hyp("H1", "control")}, pol)
    assert e0 == pol["assumed_standardised_effect"] and src == "pre-registered default"


def test_sesoi_uses_measured_unit_scale():
    pr = load_prereg()
    hyps = {"H1": _hyp("H1", "prediction"), "H2": _hyp("H2", "prediction", 0.5, 0.025)}
    s, src = sesoi_standardised("H1", hyps, pr)
    assert s == pytest.approx(0.01 / (0.025 / 0.5)) and "measured" in src
    s0, src0 = sesoi_standardised("H1", {"H1": _hyp("H1", "prediction")}, pr)
    assert s0 == pr["planner_policy"]["default_sesoi_standardised"]


def test_run2_h3_case_is_not_refuted_by_an_inconclusive_verdict():
    # Regression for run 2 (prereg v2): H3 went 0.5 -> 0.019 ("refuted") on an inconclusive verdict.
    from discolab.planner import _status
    t = likelihood_table(0.5, 72, 0.2, ALPHA)
    p = posterior(0.5, "inconclusive", t)
    assert 0.1 < p < 0.5  # inconclusive is evidence against H1, but not decisive
    assert _status(0.05, ["inconclusive"]) == "open"
    assert _status(0.05, ["refuted"]) == "refuted"
    assert _status(0.95, ["supported"]) == "supported"
    assert _status(0.95, ["inconclusive"]) == "open"


def test_inconclusive_weighs_more_with_larger_designs_but_refuted_is_decisive():
    small, large = likelihood_table(0.5, 24, 0.2, ALPHA), likelihood_table(0.5, 120, 0.2, ALPHA)
    assert posterior(0.5, "inconclusive", large) < posterior(0.5, "inconclusive", small) < 0.5
    assert posterior(0.5, "refuted", small) < 0.1 and posterior(0.5, "supported", small) > 0.9
