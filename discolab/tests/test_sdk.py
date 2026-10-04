import json
from pathlib import Path

import numpy as np

from discolab import DiscoveryLab, Experiment, PROTOCOL_VERSION
from discolab.planner import eig_bits, likelihood_table
from discolab.rpc import dispatch, handle_request
from discolab.stats import cvar, wilson
from discolab.telemetry import population_entropy


def _prediction():
    return Experiment.prediction(
        title="SDK entropy test",
        rationale="Exercise the public contract.",
        hypotheses=["H1"],
        landscapes=["rastrigin", "ackley"],
        n_seeds=4,
        feature_sets=["fitness", "fitness+entropy"],
    )


def test_python_sdk_uses_validated_lab_transitions(tmp_path):
    client = DiscoveryLab(tmp_path, actor="sdk-test")
    assert client.protocol_version == PROTOCOL_VERSION
    assert not client.initialized
    client.initialize()
    proposed = client.propose(_prediction())
    scored = client.score()
    selected = client.select(proposed["id"], "highest deterministic utility")
    assert scored["argmax"] == proposed["id"]
    assert selected["followed_argmax"] is True
    assert client.state()["selected"] == proposed["id"]
    assert {event["actor"] for event in client.events()} == {"sdk-test"}


def test_rpc_envelope_and_errors(tmp_path):
    client = DiscoveryLab(tmp_path, actor="rpc-test")
    init = handle_request(client, {"id": 1, "version": "1.0", "method": "initialize"})
    assert init["ok"] is True and init["id"] == 1
    state = handle_request(client, {"id": 2, "version": "1.0", "method": "state", "params": {}})
    json.dumps(state)  # the public bridge remains JSON serialisable
    assert state["result"]["initialized"] is True
    bad = handle_request(client, {"id": 3, "version": "9", "method": "state"})
    assert bad["ok"] is False and bad["error"]["code"] == "ValueError"


def test_cross_language_parity_fixture_matches_authoritative_python():
    path = Path(__file__).parents[2] / "sdk" / "protocol" / "v1" / "parity-fixtures.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    entropy = fixture["entropy"]
    points = np.array(entropy["points_row_major"]).reshape(entropy["rows"], entropy["cols"])
    assert population_entropy(points, entropy["lower"], entropy["upper"], entropy["bins"]) == entropy["expected"]
    tail = fixture["cvar_upper"]
    assert cvar(np.array(tail["values"]), tail["tail_probability"]) == tail["expected"]
    w = fixture["wilson"]
    interval = wilson(w["successes"], w["trials"])
    assert np.allclose([interval.estimate, interval.low, interval.high], w["expected"], atol=1e-12)
    d = fixture["decision_math"]
    table = likelihood_table(d["effect_scale"], d["n"], d["sesoi"], d["alpha"])
    assert all(np.allclose(table[k], v, atol=1e-12) for k, v in d["likelihood_table"].items())
    assert np.isclose(eig_bits(d["prior"], table), d["expected_information_gain_bits"], atol=1e-12)


def test_protocol_schema_and_rpc_dispatch_expose_the_same_methods():
    class RecordingClient:
        def __getattr__(self, name):
            return lambda *args, **kwargs: {"name": name, "args": args, "kwargs": kwargs}

    cases = {
        "initialize": {},
        "state": {},
        "events": {},
        "propose": {"experiment": {}},
        "score": {},
        "select": {"experiment_id": "E1", "justification": "test"},
        "run": {"confirm_heldout": False},
        "abort": {"experiment_id": "E1", "reason": "test"},
        "result": {"experiment_id": "E1"},
        "analyze": {"experiment_id": "E1", "interpretation": "test"},
        "decide": {"decision": "continue", "rationale": "test"},
        "register_hypothesis": {
            "hypothesis_id": "H1",
            "statement": "test",
            "h0": "null",
            "family": "prediction",
        },
    }
    schema_path = Path(__file__).parents[2] / "sdk" / "protocol" / "v1" / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    declared = set(schema["$defs"]["request"]["properties"]["method"]["enum"])
    assert set(cases) == declared

    client = RecordingClient()
    for method, params in cases.items():
        assert dispatch(client, method, params)["name"] == method
