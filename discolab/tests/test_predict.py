import numpy as np
import pytest

from discolab.predict import RunPoints, evaluate_feature_sets, fit_logistic


def _synthetic_runs(n_runs, informative, rng, function):
    runs = []
    for i in range(n_runs):
        y = rng.random(40) < 0.4
        base = rng.normal(size=(40, 6))
        extra = np.column_stack([y * 1.5 + rng.normal(size=40), rng.normal(size=40)]) if informative \
            else rng.normal(size=(40, 2))
        runs.append(RunPoints(f"{function}{i}", function,
                              {"fitness": base, "fitness+entropy": np.hstack([base, extra])}, y))
    return runs


def test_fit_logistic_rejects_single_class():
    with pytest.raises(ValueError):
        fit_logistic(np.zeros((10, 6)), np.zeros(10, dtype=bool), "fitness")


def test_informative_features_raise_auroc_and_ci_excludes_zero():
    rng = np.random.default_rng(0)
    train = _synthetic_runs(20, True, rng, "a")
    test = _synthetic_runs(20, True, rng, "b")
    res = evaluate_feature_sets([(train, test)], ["fitness", "fitness+entropy"], "fitness", n_boot=300)
    d = res["comparisons"]["fitness+entropy"]["delta_auroc"]
    assert d["estimate"] > 0.15 and d["low"] > 0


def test_uninformative_features_do_not_manufacture_an_effect():
    rng = np.random.default_rng(1)
    train = _synthetic_runs(20, False, rng, "a")
    test = _synthetic_runs(20, False, rng, "b")
    res = evaluate_feature_sets([(train, test)], ["fitness", "fitness+entropy"], "fitness", n_boot=300)
    d = res["comparisons"]["fitness+entropy"]["delta_auroc"]
    assert d["low"] < 0 < d["high"] or abs(d["estimate"]) < 0.05
