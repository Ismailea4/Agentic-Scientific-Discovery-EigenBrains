import pytest

from discolab.metrics import burn_in_level, rescue_damage, run_outcome


def test_run_outcome_restricted_mean():
    best = [9, 5, 1, 8, 4, 3, 9, 9, 9]
    epoch = [0, 0, 0, 1, 1, 1, 2, 2, 2]
    o = run_outcome(best, epoch, eps=4.0, period=3)
    assert o.recovery_gens == [1, 3] and o.recovered == [True, False]
    assert o.rmst_gens == 2.0 and o.recovery_rate == 0.5
    assert burn_in_level(best, epoch) == 1


def test_run_outcome_rejects_ragged_epochs():
    with pytest.raises(ValueError):
        run_outcome([1, 2, 3, 4, 5], [0, 0, 1, 1, 1], eps=1.0, period=2)


def test_rescue_damage_counts():
    assert rescue_damage([True, False, False], [False, True, False]) == {
        "rescue": 1, "damage": 1, "both_recovered": 0, "neither": 1}
