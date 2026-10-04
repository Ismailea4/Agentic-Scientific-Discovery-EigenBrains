import numpy as np
import pytest

from discolab.landscapes import LANDSCAPES, get_landscape, make_shift_schedule, recovery_epsilon


@pytest.mark.parametrize("name", sorted(LANDSCAPES))
def test_centered_minimum_is_zero(name):
    L = LANDSCAPES[name]
    assert L.error(np.zeros((1, 7)))[0] == pytest.approx(0.0, abs=1e-9)
    z = np.random.default_rng(0).uniform(L.lo, L.hi, size=(500, 7))
    assert np.all(L.error(z) >= 0)


def test_shift_schedule_keeps_optimum_inside_box():
    L = get_landscape("rastrigin")
    sch = make_shift_schedule(L, 10, 50, 5, 0.9, seed=3)
    assert np.all(np.abs(sch.offsets) <= 0.5 * L.width / 2 + 1e-12)
    assert sch.epoch_of(0) == 0 and sch.epoch_of(5) == 1 and sch.epoch_of(10_000) == 49


def test_unknown_landscape_fails_loudly():
    with pytest.raises(ValueError):
        get_landscape("schwefel")


def test_recovery_epsilon_is_deterministic():
    L = get_landscape("ackley")
    assert recovery_epsilon(L, 10, 0.01) == recovery_epsilon(L, 10, 0.01)
