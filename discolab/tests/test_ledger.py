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
