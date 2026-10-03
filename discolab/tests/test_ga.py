import numpy as np
import pytest

from discolab.ga import Action, GAConfig, run_ga
from discolab.landscapes import get_landscape, make_shift_schedule

CFG = GAConfig(pop_size=20, dim=5)


class FixedRate:
    """Minimal controller so GA tests do not depend on the controllers module."""

    name = "fixed"

    def __init__(self, p=0.2):
        self.p = p

    def reset(self, cfg, landscape):
        pass

    def act(self, obs):
        return Action(p_mut=self.p)


def run(ctrl, seed=1, epochs=3, period=15, name="rastrigin"):
    L = get_landscape(name)
    sch = make_shift_schedule(L, CFG.dim, epochs, period, 0.2, seed)
    return run_ga(L, sch, ctrl, CFG, epochs * period, seed)


def test_common_random_numbers_across_controllers():
    a, b = run(FixedRate(0.1)), run(FixedRate(0.9))
    assert a.best_err[0] == b.best_err[0] and a.H[0] == b.H[0]
    assert a.best_err != b.best_err  # the controllers did change the trajectory


def test_run_is_deterministic():
    assert run(FixedRate()).best_err == run(FixedRate()).best_err


def test_elitism_makes_best_monotone_within_epoch_and_shift_can_raise_it():
    tr = run(FixedRate(), epochs=4, period=20)
    b, e = np.asarray(tr.best_err), np.asarray(tr.epoch)
    for k in range(4):
        assert np.all(np.diff(b[e == k]) <= 1e-12)
    assert any(b[e == k][0] > b[e == k - 1][-1] for k in range(1, 4))


def test_controllers_cannot_see_epochs_or_write_history():
    seen = {}

    class Spy(FixedRate):
        def act(self, obs):
            seen["has_epoch"] = hasattr(obs, "epoch")
            with pytest.raises(AttributeError):
                obs.best_err = []
            return super().act(obs)

    run(Spy())
    assert seen["has_epoch"] is False


def test_invalid_action_fails_loudly():
    with pytest.raises(ValueError):
        run(FixedRate(1.5))
