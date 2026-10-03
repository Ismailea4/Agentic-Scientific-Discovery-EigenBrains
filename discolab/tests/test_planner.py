from discolab.planner import eig_bits, entropy_bits, likelihood_table, posterior, power

LIK = {"supported_given_H0": 0.025, "refuted_given_H1": 0.02}


def test_eig_properties():
    t = likelihood_table(power(60, 0.5, 0.05), LIK)
    assert eig_bits(0.0, t) == 0.0 and eig_bits(1.0, t) == 0.0
    assert 0 < eig_bits(0.5, t) <= entropy_bits(0.5)
    assert eig_bits(0.5, t) > eig_bits(0.1, t)  # settled questions are worth less
    weak = likelihood_table(power(4, 0.1, 0.05), LIK)
    assert eig_bits(0.5, weak) < eig_bits(0.5, t)  # underpowered designs are worth less


def test_posterior_direction():
    t = likelihood_table(0.8, LIK)
    assert posterior(0.5, "supported", t) > 0.9
    assert posterior(0.5, "refuted", t) < 0.1
    assert 0.1 < posterior(0.5, "inconclusive", t) < 0.9
