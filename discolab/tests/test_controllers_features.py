import numpy as np
import pytest

from discolab import controllers as C
from discolab.features import FEATURE_SETS, feature_matrix, stagnation_labels
from discolab.ga import GAConfig, ObsView, run_ga
from discolab.landscapes import get_landscape, make_shift_schedule

CFG = GAConfig(pop_size=20, dim=5)


def run(ctrl, seed=2, epochs=3, period=15):
    L = get_landscape("ackley")
    sch = make_shift_schedule(L, CFG.dim, epochs, period, 0.2, seed)
    return run_ga(L, sch, ctrl, CFG, epochs * period, seed)


@pytest.mark.parametrize("name", [c for c in C.CONTROLLERS if c != "B3_predictive"])
def test_baselines_stay_in_rate_bounds(name):
    tr = run(C.make_controller(name))
    p = np.asarray(tr.p_mut)
    assert np.all((p >= 0.5 / CFG.dim - 1e-12) & (p <= 4.0 / CFG.dim + 1e-12))


def test_hypermutation_fires_after_a_shift():
    tr = run(C.Hypermutation())
    assert max(tr.p_mut) == pytest.approx(4.0 / CFG.dim)


def test_predictive_controller_requires_a_model():
    with pytest.raises(ValueError):
        C.make_controller("B3_predictive")


def test_logistic_model_round_trip():
    names = FEATURE_SETS["fitness+entropy"]
    m = C.LogisticModel("fitness+entropy", names, np.zeros(len(names)), np.ones(len(names)),
                        np.linspace(-1, 1, len(names)), 0.3)
    m2 = C.LogisticModel.from_dict(m.to_dict())
    x = np.random.default_rng(0).normal(size=(5, len(names)))
    np.testing.assert_allclose(m.predict_proba(x), m2.predict_proba(x))
    tr = run(C.Predictive(m))
    assert len(tr.p_mut) == 45


def test_labels_exclude_windows_crossing_shifts():
    improved = np.array([1, 0, 0, 1, 0, 0, 0, 0], dtype=bool)
    epoch = np.array([0, 0, 0, 0, 0, 1, 1, 1])
    y, mask = stagnation_labels(improved, epoch, horizon=2)
    assert mask.tolist() == [True, False, False, False, False, False, False, False]
    assert bool(y[0]) is True  # no improvement in generations 1-2


def test_feature_matrix_uses_only_past():
    tr = run(C.Fixed())
    full = feature_matrix(ObsView(tr), FEATURE_SETS["full"])
    tr.best_err[-1] = 1e9  # perturb the latest value
    again = feature_matrix(ObsView(tr), FEATURE_SETS["full"])
    np.testing.assert_array_equal(full[:-1], again[:-1])


def test_nested_feature_sets_extend_their_baselines():
    for name in ("fitness+entropy", "fitness+dispersion", "fitness+spread"):
        assert FEATURE_SETS[name][: len(FEATURE_SETS["fitness"])] == FEATURE_SETS["fitness"]
    nested = FEATURE_SETS["fitness+dispersion+entropy"]
    assert nested[: len(FEATURE_SETS["fitness+dispersion"])] == FEATURE_SETS["fitness+dispersion"]
    assert set(nested) - set(FEATURE_SETS["fitness+dispersion"]) == {"H", "dH_5"}


def _constant_risk_model(intercept: float) -> C.LogisticModel:
    names = FEATURE_SETS["fitness+entropy"]
    k = len(names)
    return C.LogisticModel("fitness+entropy", names, np.zeros(k), np.ones(k), np.zeros(k), intercept)


def test_hybrid_holds_the_rate_matched_base_when_risk_is_low():
    tr = run(C.HybridPredictive(_constant_risk_model(-10.0)))
    assert np.allclose(tr.p_mut, 0.8 / CFG.dim)


def test_hybrid_bursts_once_on_a_rising_edge_of_predicted_risk():
    tr = run(C.HybridPredictive(_constant_risk_model(10.0)))
    p = np.asarray(tr.p_mut)
    burst = C.HybridPredictive.BURST
    assert np.allclose(p[:burst], 4.0 / CFG.dim)  # risk crosses 0.5 at generation 0
    assert np.allclose(p[burst:], 0.8 / CFG.dim)  # no new rising edge while risk stays high


def test_hybrid_requires_a_model():
    with pytest.raises(ValueError):
        C.make_controller("B5_hybrid")
