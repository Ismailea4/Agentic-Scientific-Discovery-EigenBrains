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


def test_failed_run_releases_selection_and_is_recorded(tmp_path, monkeypatch):
    lab.init_lab(tmp_path)
    lab.propose_experiment(PRED, "designer", tmp_path)
    lab.score_experiments("designer", tmp_path)
    lab.select_experiment("E1", "highest utility", "pi", tmp_path)

    def boom(*a, **k):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(lab, "run_experiment", boom)
    with pytest.raises(RuntimeError):
        lab.run_selected_experiment("pi", tmp_path)
    st = Ledger(tmp_path).state()
    assert st["selected"] is None
    assert st["candidates"]["E1"]["status"] == "failed"
    assert "simulated crash" in st["candidates"]["E1"]["error"]
    with pytest.raises(LedgerError):  # a failed experiment cannot be re-selected
        lab.select_experiment("E1", "retry", "pi", tmp_path)


def test_operator_can_abort_an_interrupted_run(tmp_path):
    lab.init_lab(tmp_path)
    lab.propose_experiment(PRED, "designer", tmp_path)
    lab.score_experiments("designer", tmp_path)
    lab.select_experiment("E1", "highest utility", "pi", tmp_path)
    lab.abort_experiment("E1", "process killed", "operator", tmp_path)
    assert Ledger(tmp_path).state()["selected"] is None


def test_registered_hypotheses_must_be_testable(tmp_path):
    lab.init_lab(tmp_path)
    with pytest.raises(ValueError):  # run-1 failure mode: a feature set that does not exist
        lab.register_hypothesis("H9", "s", "n", "prediction", "fitness+magic", None, "critic", tmp_path)
    with pytest.raises(ValueError):
        lab.register_hypothesis("H9", "s", "n", "control", None, "B9_unknown", "critic", tmp_path)
    ok = lab.register_hypothesis("H9", "s", "n", "control", None, "B3_predictive", "critic", tmp_path,
                                 comparator="B0_fixed_x0.8")
    assert ok["comparator"] == "B0_fixed_x0.8"


def test_nested_contrast_requires_its_baseline(tmp_path):
    lab.init_lab(tmp_path)
    spec = {**PRED, "hypotheses": ["H5"], "feature_sets": ["fitness", "fitness+dispersion+entropy"]}
    with pytest.raises(ValueError):  # H5 is compared with fitness+dispersion, which is missing
        lab.propose_experiment(spec, "designer", tmp_path)
    spec["feature_sets"].append("fitness+dispersion")
    assert lab.propose_experiment(spec, "designer", tmp_path)["id"] == "E1"


def test_rate_matched_control_spec_validates(tmp_path):
    lab.init_lab(tmp_path)
    spec = {"kind": "control", "title": "H6 rate-matched control", "rationale": "timing vs rate",
            "hypotheses": ["H6"], "landscapes": ["rastrigin", "ackley"], "n_seeds": 4,
            "controllers": ["B0_fixed", "B3_predictive"]}
    with pytest.raises(ValueError):  # comparator B0_fixed_x0.8 missing
        lab.propose_experiment(spec, "designer", tmp_path)
    spec["controllers"].append("B0_fixed_x0.8")
    assert lab.propose_experiment(spec, "designer", tmp_path)["stage"] == "development"


def test_coupling_never_decides_status(tmp_path):
    lab.init_lab(tmp_path)
    lab.propose_experiment(PRED, "designer", tmp_path)
    lab.score_experiments("designer", tmp_path)
    lab.select_experiment("E1", "highest utility", "pi", tmp_path)
    lab.run_selected_experiment("pi", tmp_path)
    upd = lab.record_analysis("E1", "interpretation", [], "critic", tmp_path)
    coupled = [u for u in upd["updates"] if u["experiment"] is None]
    assert coupled and all(u["status"] == "open" for u in coupled)


def test_scoring_returns_a_portfolio_and_selection_records_membership(tmp_path):
    lab.init_lab(tmp_path)
    lab.propose_experiment(PRED, "designer", tmp_path)
    lab.propose_experiment({**PRED, "title": "Dev-stage dispersion prediction test", "hypotheses": ["H2"],
                            "feature_sets": ["fitness", "fitness+dispersion"]}, "designer", tmp_path)
    out = lab.score_experiments("designer", tmp_path)
    assert set(out["portfolio"]["ids"]) == {"E1", "E2"}  # different hypotheses: both worth running
    sel = lab.select_experiment(out["portfolio"]["ids"][1], "second portfolio item", "pi", tmp_path)
    assert sel["in_portfolio"] is True


def test_labs_get_independent_seed_blocks(tmp_path):
    from discolab.experiments import allocate_seeds
    from discolab.prereg import load_prereg
    pr = load_prereg()
    a = allocate_seeds(pr, "development", 1, 4, lab_block=1)
    b = allocate_seeds(pr, "development", 1, 4, lab_block=2)
    assert not set(a) & set(b)
    assert allocate_seeds(pr, "test", 1, 4, lab_block=2)[0] - allocate_seeds(pr, "test", 1, 4)[0] == \
        2 * pr["seeds"]["lab_block_stride"]
    import inspect
    from discolab import experiments
    assert "lab_block" not in inspect.getsource(experiments.calibrate_eps)  # shared metric definition
    lab.init_lab(tmp_path / "labA", seed_block=7)
    assert Ledger(tmp_path / "labA").state()["seed_block"] == 7
    with pytest.raises(LedgerError):  # another lab may not reuse block 7
        lab.init_lab(tmp_path / "labB", seed_block=7)
    lab.init_lab(tmp_path / "labB", seed_block=8)


def test_runs_record_and_use_their_lab_block(tmp_path):
    import json
    lab.init_lab(tmp_path / "lab", seed_block=3)
    root = tmp_path / "lab"
    lab.propose_experiment(PRED, "designer", root)
    lab.score_experiments("designer", root)
    lab.select_experiment("E1", "x", "pi", root)
    lab.run_selected_experiment("pi", root)
    manifest = json.loads((root / "runs" / "E1" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["derived"]["lab_block"] == 3
    assert min(manifest["seeds"]) >= 3_000_000
