"""State-transition guards and one real (small) end-to-end loop through the lab API."""

import pytest

from discolab import lab
from discolab.ledger import Ledger, LedgerError

PRED = {
    "kind": "prediction", "title": "Dev-stage entropy prediction test",
    "rationale": "Leave-one-landscape-out test of entropy features.",
    "hypotheses": ["H1"], "landscapes": ["rastrigin", "ackley"], "n_seeds": 4,
    "feature_sets": ["fitness", "fitness+entropy"],
}


def test_guards(tmp_path):
    lab.init_lab(tmp_path)
    with pytest.raises(LedgerError):
        lab.init_lab(tmp_path)
    with pytest.raises(LedgerError):
        lab.run_selected_experiment("pi", tmp_path)  # nothing selected
    with pytest.raises(LedgerError):
        lab.select_experiment("E1", "x", "pi", tmp_path)  # nothing scored
    with pytest.raises(LedgerError):
        Ledger(tmp_path).append("evidence_recorded", {"claim": "x"}, "lit")  # unverified evidence
    with pytest.raises(ValueError):  # mixing development and held-out landscapes
        lab.propose_experiment({**PRED, "landscapes": ["rastrigin", "levy"]}, "designer", tmp_path)
    with pytest.raises(ValueError):  # missing baseline features
        lab.propose_experiment({**PRED, "feature_sets": ["fitness+entropy"]}, "designer", tmp_path)


def test_confirmatory_is_infeasible_before_development(tmp_path):
    lab.init_lab(tmp_path)
    lab.propose_experiment({**PRED, "landscapes": ["griewank", "levy"]}, "designer", tmp_path)
    lab.propose_experiment(PRED, "designer", tmp_path)
    res = lab.score_experiments("designer", tmp_path)
    rows = {r["id"]: r for r in res["scores"]}
    assert rows["E1"]["feasible"] is False and rows["E2"]["feasible"] is True
    assert res["argmax"] == "E2"
    with pytest.raises(LedgerError):
        lab.select_experiment("E1", "want held-out", "pi", tmp_path)


def test_end_to_end_small_loop(tmp_path):
    lab.init_lab(tmp_path)
    lab.propose_experiment(PRED, "designer", tmp_path)
    lab.score_experiments("designer", tmp_path)
    lab.select_experiment("E1", "highest utility", "pi", tmp_path)
    out = lab.run_selected_experiment("pi", tmp_path)
    assert out["summary"]["verdicts"]["H1"]["verdict"] in ("supported", "inconclusive", "refuted")
    with pytest.raises(FileExistsError):  # raw artifacts are immutable
        from discolab.experiments import ExperimentSpec, run_experiment
        from discolab.prereg import load_prereg
        st = Ledger(tmp_path).state()
        run_experiment(ExperimentSpec(**PRED), "E1", 1, tmp_path, load_prereg(),
                       {"stage": "development", "dev_landscapes": ["rastrigin", "ackley"]}, {}, st["hypotheses"])
    upd = lab.record_analysis("E1", "interpretation", [], "critic", tmp_path)
    ids = [u["id"] for u in upd["updates"]]
    assert "H1" in ids and "H4" in ids  # H4's prior is coupled to H1
    st = lab.get_state(tmp_path)
    assert st["hypotheses"]["H1"]["history"]
    assert st["candidates"]["E1"]["status"] == "analyzed"
    replay = Ledger(tmp_path).state()  # fold is reproducible
    assert replay["hypotheses"]["H1"]["posterior"] == st["hypotheses"]["H1"]["posterior"]
