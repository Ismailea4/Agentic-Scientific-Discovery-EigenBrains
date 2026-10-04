import numpy as np
import pytest

from discolab.stats import auroc, bootstrap_mean_diff, cvar, hodges_lehmann, holm, mcnemar_exact, wilson


def test_auroc_bounds_and_ties():
    assert auroc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]) == 1.0
    assert auroc([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1]) == 0.0
    assert auroc([0.5, 0.5, 0.5, 0.5], [0, 1, 0, 1]) == 0.5


def test_wilson_contains_point_and_is_bounded():
    iv = wilson(3, 10)
    assert 0 <= iv.low < 0.3 < iv.high <= 1


def test_bootstrap_detects_clear_shift_and_stratifies():
    d = np.random.default_rng(0).normal(2.0, 1.0, 60)
    assert bootstrap_mean_diff(d).low > 0
    assert bootstrap_mean_diff(d, strata=np.repeat(["a", "b"], 30)).low > 0


def test_holm_mcnemar_hodges_lehmann():
    assert holm({"a": 0.001, "b": 0.04, "c": 0.5}) == {"a": True, "b": False, "c": False}
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(10, 0) < 0.01
    assert hodges_lehmann([1.0, 2.0, 3.0]) == pytest.approx(2.0)


def test_cvar_is_tail_mean():
    assert cvar(list(range(1, 11)), 0.9) == pytest.approx(10.0)
