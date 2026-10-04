import pytest

from discolab.ledger import Ledger, LedgerError, fold

INIT = {"question": "q", "prereg_sha256": "abc", "compute_budget_sec": 100, "sec_per_generation": 0.001,
        "hypotheses": [{"id": "H1", "family": "prediction", "prior": 0.5, "statement": "s", "h0": "n"}]}


def test_everything_requires_initialisation(tmp_path):
    with pytest.raises(LedgerError):
        Ledger(tmp_path).append("decision_recorded", {"decision": "x"}, "pi")


def test_invalid_transitions_append_nothing(tmp_path):
    led = Ledger(tmp_path)
    led.append("lab_initialized", INIT, "op")
    for etype, payload in [
        ("experiment_selected", {"id": "E1"}),
        ("experiment_completed", {"id": "E1", "summary": {}, "artifacts": "", "runtime_sec": 1}),
        ("analysis_recorded", {"id": "E1"}),
        ("hypothesis_updated", {"id": "H9", "posterior": 0.5, "status": "open"}),
        ("evidence_recorded", {"claim": "unsourced"}),
        ("not_an_event", {}),
    ]:
        with pytest.raises(LedgerError):
            led.append(etype, payload, "agent")
    assert len(led.events()) == 1


def test_fold_is_a_pure_replay(tmp_path):
    led = Ledger(tmp_path)
    led.append("lab_initialized", INIT, "op")
    led.append("evidence_recorded", {"openalex_id": "W1", "claim": "c"}, "lit")
    assert fold(led.events()) == led.state()
    assert led.state()["evidence"][0]["recorded_by"] == "lit"
    assert all(e["prereg_sha256"] == "abc" for e in led.events())


def test_completed_experiment_cannot_be_selected_again(tmp_path):
    led = Ledger(tmp_path)
    led.append("lab_initialized", INIT, "op")
    spec = {"hypotheses": ["H1"]}
    led.append("experiment_proposed", {"id": "E1", "spec": spec}, "designer")
    row = {"id": "E1", "feasible": True}
    led.append("experiments_scored", {"scores": [row], "argmax": "E1"}, "designer")
    led.append("experiment_selected", {"id": "E1", "argmax": "E1", "followed_argmax": True,
                                       "justification": "x"}, "pi")
    led.append("experiment_completed", {"id": "E1", "summary": {}, "artifacts": "a", "runtime_sec": 1.0}, "pi")
    with pytest.raises(LedgerError):
        led.append("experiment_selected", {"id": "E1", "argmax": "E1", "followed_argmax": True,
                                           "justification": "again"}, "pi")


def test_prereg_hash_ignores_line_endings(tmp_path):
    from discolab.ledger import file_sha256
    (tmp_path / "a.yaml").write_bytes(b"version: 2\nx: 1\n")
    (tmp_path / "b.yaml").write_bytes(b"version: 2\r\nx: 1\r\n")
    assert file_sha256(tmp_path / "a.yaml") == file_sha256(tmp_path / "b.yaml")
