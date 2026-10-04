import numpy as np
import pytest

from discolab.telemetry import fitness_dispersion, population_dispersion, population_entropy


def test_entropy_and_dispersion_extremes():
    collapsed = np.full((50, 4), 0.3)
    uniform = np.random.default_rng(0).uniform(-1, 1, size=(5000, 4))
    assert population_entropy(collapsed, -1, 1) == pytest.approx(0.0)
    assert population_entropy(uniform, -1, 1) > 0.99
    assert population_dispersion(collapsed, -1, 1) == pytest.approx(0.0)
    assert population_dispersion(uniform, -1, 1) == pytest.approx(1.0, abs=0.05)


def test_fitness_dispersion_is_scale_free():
    e = np.random.default_rng(1).lognormal(size=100)
    assert fitness_dispersion(e) == pytest.approx(fitness_dispersion(1000 * e))
