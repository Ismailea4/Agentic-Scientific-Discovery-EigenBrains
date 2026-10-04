"""Phase-1 evidence runtime: context manager, decisions, listing, checkpoint/resume,
tamper evidence, portable provenance, bundles, lineage, CLI errors, RPC policy."""

import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

from discolab import (
    ArtifactSchema,
    DiscoveryLab,
    EvidenceError,
    EvidenceStore,
    ExperimentSpecV2,
    FieldSchema,
    MetricSpec,
    ResourceBudget,
    ValidationError,
    experiment,
    export_bundle,
    verify_bundle,
)
from discolab.rpc import handle_request
from discolab.sdk_cli import main as cli_main

STEPS = ArtifactSchema(
    name="steps", version=1, kind="table",
    fields=(FieldSchema("step", "integer", unit="count", role="index", minimum=0),
            FieldSchema("draw", "number", unit="dimensionless", role="observation")),
)
TOTAL = MetricSpec("total", unit="dimensionless", role="primary")
CRASH = {"after_step": None}


class SimulatedCrash(BaseException):
    """Stands in for the process dying: nothing is recorded by the SDK."""


@experiment(capability="resumable", hypothesis="Checkpointed loops resume exactly.", protocol=__file__,
            outputs=(STEPS,), primary_metric=TOTAL)
def resumable(run):
    state = run.restored_state or {"step": 0, "rows": []}
    noise = run.child_rng("noise")
    for step in range(state["step"], run.params["steps"]):
        state["rows"].append({"step": step, "draw": float(noise.normal())})
        state["step"] = step + 1
        run.consume(1)
        run.checkpoint(state)
        if CRASH["after_step"] == step:
            raise SimulatedCrash()
    run.emit.table("steps", state["rows"], schema=STEPS.id)
    run.metric("total", sum(r["draw"] for r in state["rows"]))


def _spec(seed=3, **overrides):
    fields = dict(capability="optimization", hypothesis="h", protocol=__file__, parameters={"n": 1}, seed=seed,
                  outputs=(STEPS,), primary_metric=TOTAL, budget=ResourceBudget(max_evaluations=100))
    return ExperimentSpecV2(**{**fields, **overrides})


def _finished(root, seed=3, value=1.0):
    with EvidenceStore(root).begin(_spec(seed)) as run:
        run.emit.table("steps", [{"step": 0, "draw": value}], schema=STEPS.id)
        run.metric("total", value)
    return run.run_id


def _crashed_resumable(root, steps=6, crash_after=2):
    spec = resumable.spec(parameters={"steps": steps}, seed=11)
    context = EvidenceStore(root).begin(spec)
    CRASH["after_step"] = crash_after
    try:
        with pytest.raises(SimulatedCrash):
            resumable.function(context)  # no context manager: a hard crash records nothing
    finally:
        CRASH["after_step"] = None
    return context.run_id


# ------------------------------------------------------------------ context manager

def test_context_manager_finalizes_and_records_failures(tmp_path):
    run_id = _finished(tmp_path)
    assert EvidenceStore(tmp_path).inspect(run_id)["status"] == "validated"

    with pytest.raises(RuntimeError, match="boom"):
        with EvidenceStore(tmp_path).begin(_spec()) as run:
            raise RuntimeError("boom")
    failed = EvidenceStore(tmp_path).inspect(run.run_id)
    assert failed["status"] == "failed"
    assert failed["events"][-1]["payload"]["error_type"] == "RuntimeError"

    with pytest.raises(ValidationError, match="omitted declared output"):
        with EvidenceStore(tmp_path).begin(_spec()) as run:
            run.metric("total", 1.0)  # forgot the declared table
    assert EvidenceStore(tmp_path).inspect(run.run_id)["status"] == "failed"


# ------------------------------------------------------------------ decisions

def test_accept_and_reject_are_terminal_and_idempotent(tmp_path):
    store = EvidenceStore(tmp_path)
    a, b = _finished(tmp_path, 1), _finished(tmp_path, 2)
    with pytest.raises(ValueError):
        store.reject(a, "  ")
    first = store.reject(a, "pilot run, not part of the protocol")
    assert first["status"] == "rejected_as_evidence" and first["integrity"] == "valid"
    again = store.reject(a, "pilot run, not part of the protocol")
    assert again["idempotent"] is True
    with pytest.raises(EvidenceError, match="terminal"):
        store.reject(a, "a different reason")
    with pytest.raises(EvidenceError, match="terminal"):
        store.accept(a, "changed my mind")
    store.accept(b, "registered checks passed")
    assert store.accept(b, "registered checks passed")["idempotent"] is True
    with pytest.raises(EvidenceError):
        store.reject(b, "too late")
    events = [e["type"] for e in store.inspect(b)["events"]]
    assert events.count("run_accepted") == 1


def test_running_or_failed_runs_cannot_be_decided(tmp_path):
    store = EvidenceStore(tmp_path)
    open_run = store.begin(_spec())
    with pytest.raises(EvidenceError):
        store.accept(open_run.run_id, "x")
    open_run.record_failure("Crash", "x")
    with pytest.raises(EvidenceError):
        store.reject(open_run.run_id, "x")


def test_invalid_run_can_be_rejected_but_not_accepted(tmp_path):
    store = EvidenceStore(tmp_path)
    run_id = _finished(tmp_path)
    path = tmp_path / "research-runs" / run_id / "artifacts" / "raw" / "steps.jsonl"
    path.write_bytes(path.read_bytes().replace(b"1.0", b"2.0"))
    with pytest.raises(ValidationError, match="hash mismatch"):
        store.accept(run_id, "x")
    decision = store.reject(run_id, "artifact failed its integrity check")
    assert decision["integrity"].startswith("invalid")


# ------------------------------------------------------------------ listing

def test_list_filters_by_capability_status_seed_and_time(tmp_path):
    store = EvidenceStore(tmp_path)
    a = _finished(tmp_path, seed=1)
    b = _finished(tmp_path, seed=2)
    store.accept(b, "ok")
    EvidenceStore(tmp_path).begin(_spec(seed=1, capability="other"))  # left running
    rows = store.list()
    assert [r["run_id"] for r in rows][:2] == [a, b]
    assert {r["run_id"] for r in store.list(seed=1, capability="optimization")} == {a}
    assert [r["run_id"] for r in store.list(status="accepted_as_evidence")] == [b]
    assert len(store.list(capability="other")) == 1
    created_b = rows[1]["created_at"]
    assert {r["run_id"] for r in store.list(created_after=created_b, capability="optimization")} == {b}
    assert {r["run_id"] for r in store.list(created_before=rows[0]["created_unix_ns"])} == {a}
    with pytest.raises(ValueError):
        store.list(status="almost_done")


# ------------------------------------------------------------------ tamper evidence and provenance

def test_event_chain_and_metadata_hashes_detect_edits(tmp_path):
    run_id = _finished(tmp_path)
    run_dir = tmp_path / "research-runs" / run_id
    events = run_dir / "events.jsonl"
    original = events.read_text(encoding="utf-8")
    lines = original.splitlines()
    edited = json.loads(lines[1])
    edited["time_unix_ns"] += 1
    events.write_text("\n".join([lines[0], json.dumps(edited, sort_keys=True, separators=(",", ":"))]
                                + lines[2:]) + "\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="chain broken"):
        EvidenceStore(tmp_path).validate(run_id)
    events.write_text(original, encoding="utf-8")
    spec = run_dir / "spec.json"
    spec.write_text(spec.read_text(encoding="utf-8").replace('"h"', '"H"'), encoding="utf-8")
    with pytest.raises(ValidationError, match="spec.json"):
        EvidenceStore(tmp_path).validate(run_id)


def test_provenance_contains_no_absolute_paths(tmp_path):
    run_id = _finished(tmp_path)
    text = (tmp_path / "research-runs" / run_id / "provenance.json").read_text(encoding="utf-8")
    home = str(Path.home())
    assert home not in text and home.replace("\\", "\\\\") not in text
    provenance = json.loads(text)
    assert not Path(provenance["runtime"]["executable"]).is_absolute()


# ------------------------------------------------------------------ checkpoint / resume

def test_resumed_run_matches_an_uninterrupted_run_exactly(tmp_path):
    reference = resumable.run(tmp_path / "ref", parameters={"steps": 6}, seed=11)
    run_id = _crashed_resumable(tmp_path / "crash")
    status = EvidenceStore(tmp_path / "crash").inspect(run_id)["status"]
    assert status == "running"
    report = resumable.resume(tmp_path / "crash", run_id)
    assert report["status"] == "validated"
    ref_rows = (tmp_path / "ref" / "research-runs" / reference["run_id"] / "artifacts" / "raw" / "steps.jsonl")
    res_rows = (tmp_path / "crash" / "research-runs" / run_id / "artifacts" / "raw" / "steps.jsonl")
    assert ref_rows.read_bytes() == res_rows.read_bytes()  # RNG stream and loop state restored
    snapshot = EvidenceStore(tmp_path / "crash").inspect(run_id)
    resumed = [e for e in snapshot["events"] if e["type"] == "run_resumed"]
    assert resumed[0]["payload"]["checkpoint_sequence"] == 3
    assert snapshot["events"][-2]["payload"]["evaluations"] == 6  # finalized with cumulative accounting


def test_resume_refuses_finished_failed_and_checkpointless_runs(tmp_path):
    store = EvidenceStore(tmp_path)
    with pytest.raises(EvidenceError, match="validated"):
        store.resume(_finished(tmp_path))
    no_checkpoint = store.begin(_spec())
    with pytest.raises(EvidenceError, match="no checkpoint"):
        store.resume(no_checkpoint.run_id)
    no_checkpoint.record_failure("Crash", "x")
    with pytest.raises(EvidenceError, match="failed"):
        store.resume(no_checkpoint.run_id)


def test_resume_refuses_incompatible_or_corrupted_state(tmp_path):
    store = EvidenceStore(tmp_path)
    run_id = _crashed_resumable(tmp_path)
    other = resumable.spec(parameters={"steps": 7}, seed=11)
    with pytest.raises(EvidenceError, match="incompatible spec"):
        store.resume(run_id, other)
    checkpoint = tmp_path / "research-runs" / run_id / "checkpoints" / "ckpt-000003.json"
    original = checkpoint.read_bytes()
    checkpoint.write_bytes(original.replace(b'"step":3', b'"step":4'))
    with pytest.raises(ValidationError, match="checkpoint 3 hash mismatch"):
        store.resume(run_id)
    checkpoint.write_bytes(original)
    assert store.resume(run_id).resumed_from == 3


def test_resume_refuses_evidence_emitted_after_the_last_checkpoint(tmp_path):
    store = EvidenceStore(tmp_path)
    context = store.begin(_spec())
    context.checkpoint({"i": 1})
    context.metric("total", 1.0)  # then the process dies
    with pytest.raises(EvidenceError, match="after its last checkpoint"):
        store.resume(context.run_id)


def test_resume_refuses_a_changed_input(tmp_path):
    data = tmp_path / "input.txt"
    data.write_text("v1", encoding="utf-8")
    store = EvidenceStore(tmp_path / "store")
    context = store.begin(_spec(inputs={"data": str(data)}))
    context.checkpoint()
    data.write_text("v2", encoding="utf-8")
    with pytest.raises(EvidenceError, match="input changed"):
        store.resume(context.run_id)


# ------------------------------------------------------------------ bundles and lineage

def test_bundle_round_trip_is_content_addressed(tmp_path):
    store = EvidenceStore(tmp_path / "store")
    a, b = _finished(store.root, 1), _finished(store.root, 2)
    store.accept(a, "ok")
    manifest = export_bundle(store.root, [a, b], tmp_path / "one.zip")
    again = export_bundle(store.root, [b, a], tmp_path / "two.zip")
    assert manifest["content_sha256"] == again["content_sha256"]
    assert (tmp_path / "one.zip").read_bytes() == (tmp_path / "two.zip").read_bytes()
    report = verify_bundle(tmp_path / "one.zip")
    assert report["valid"] and report["content_sha256"] == manifest["content_sha256"]
    export_bundle(store.root, [a], tmp_path / "unpacked", archive=False)
    assert verify_bundle(tmp_path / "unpacked")["valid"]


def test_corrupted_bundle_fails_closed(tmp_path):
    store = EvidenceStore(tmp_path / "store")
    run_id = _finished(store.root)
    export_bundle(store.root, [run_id], tmp_path / "b", archive=False)
    target = tmp_path / "b" / "research-runs" / run_id / "artifacts" / "raw" / "steps.jsonl"
    target.write_bytes(target.read_bytes().replace(b"1.0", b"9.0"))
    with pytest.raises(ValidationError, match="does not match its manifest hash"):
        verify_bundle(tmp_path / "b")
    (tmp_path / "b" / "extra.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValidationError, match="unlisted file extra.txt"):
        verify_bundle(tmp_path / "b")

    export_bundle(store.root, [run_id], tmp_path / "ok.zip")
    data = bytearray((tmp_path / "ok.zip").read_bytes())
    data[len(data) // 2] ^= 0xFF
    (tmp_path / "flipped.zip").write_bytes(bytes(data))
    with pytest.raises(ValidationError):
        verify_bundle(tmp_path / "flipped.zip")


def test_bundle_refuses_open_runs_and_unsafe_archives(tmp_path):
    store = EvidenceStore(tmp_path / "store")
    open_run = store.begin(_spec())
    with pytest.raises(EvidenceError, match="running"):
        export_bundle(store.root, [open_run.run_id], tmp_path / "x.zip")
    with zipfile.ZipFile(tmp_path / "evil.zip", "w") as zf:
        zf.writestr("bundle.json", "{}")
        zf.writestr("../escape.txt", "x")
    with pytest.raises(ValidationError, match="unsafe bundle member"):
        verify_bundle(tmp_path / "evil.zip")
    assert not (tmp_path / "escape.txt").exists()


def test_lineage_links_runs_through_input_hashes(tmp_path):
    store = EvidenceStore(tmp_path / "store")
    upstream = _finished(store.root)
    artifact = store.root / "research-runs" / upstream / "artifacts" / "raw" / "steps.jsonl"
    with store.begin(_spec(inputs={"steps_in": str(artifact)})) as run:
        raw = run.emit.table("steps", [{"step": 0, "draw": 2.0}], schema=STEPS.id)
        run.metric("total", 2.0)
    graph = store.lineage()
    edge = next(e for e in graph["edges"] if e["kind"] == "input")
    assert (edge["from_run"], edge["from_artifact"], edge["to_run"]) == (upstream, "steps", run.run_id)
    assert raw["sha256"] != edge["sha256"]


# ------------------------------------------------------------------ CLI

def test_cli_reports_structured_errors_with_exit_codes(tmp_path, capsys):
    run_id = _finished(tmp_path)
    assert cli_main(["--root", str(tmp_path), "list", "--status", "validated"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["run_id"] == run_id
    assert cli_main(["--root", str(tmp_path), "inspect", "RUN-MISSING"]) == 4
    err = json.loads(capsys.readouterr().err.strip())
    assert err["ok"] is False and err["error"]["code"] == "FileNotFoundError" and err["exit_code"] == 4
    assert cli_main(["--root", str(tmp_path), "reject", run_id]) == 2  # --reason is required
    assert "usage" in json.loads(capsys.readouterr().err)["error"]["message"]
    assert cli_main(["--root", str(tmp_path), "reject", run_id, "--reason", "pilot"]) == 0
    capsys.readouterr()
    assert cli_main(["--root", str(tmp_path), "accept", run_id, "--rationale", "x"]) == 5
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "EvidenceError"
    (tmp_path / "research-runs" / run_id / "metrics.json").write_text("{}\n", encoding="utf-8")
    assert cli_main(["--root", str(tmp_path), "validate", run_id]) == 3
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "ValidationError"


# ------------------------------------------------------------------ RPC policy

def _rpc(client, method, **params):
    return handle_request(client, {"id": 1, "version": "1.0", "method": method, "params": params})


def test_rpc_never_imports_a_runner_that_is_not_allow_listed(tmp_path):
    probe = tmp_path / "probe_pkg"
    probe.mkdir()
    (probe / "__init__.py").write_text("raise SystemExit('imported')\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        client = DiscoveryLab(tmp_path / "lab", allowed_runner_modules=())
        spec = {**_spec().to_dict(), "runner": "probe_pkg:anything"}
        out = _rpc(client, "research.begin", spec=spec)
        assert out["ok"] is False and out["error"]["code"] == "PermissionError"
        assert "probe_pkg" not in sys.modules
        assert _rpc(client, "research.list")["result"] == []  # refused before a run was created
        allowed = DiscoveryLab(tmp_path / "lab", allowed_runner_modules=("test_evidence_lifecycle",))
        ok_spec = resumable.spec(parameters={"steps": 1}, seed=1).to_dict()
        assert _rpc(allowed, "research.begin", spec=ok_spec)["ok"] is True
    finally:
        sys.path.remove(str(tmp_path))


def test_rpc_bundle_names_cannot_escape_the_lab(tmp_path):
    client = DiscoveryLab(tmp_path / "lab", allowed_runner_modules=())
    run_id = _finished(tmp_path / "lab")
    bad = _rpc(client, "research.export_bundle", run_ids=[run_id], name="../outside")
    assert bad["ok"] is False and bad["error"]["code"] == "ValueError"
    good = _rpc(client, "research.export_bundle", run_ids=[run_id], name="study-1")
    assert good["ok"] is True and good["result"]["path"] == "bundles/study-1.zip"
    assert _rpc(client, "research.verify_bundle", name="study-1")["result"]["valid"] is True


def test_rpc_checkpoint_resume_across_bridge_processes_and_client_failure(tmp_path):
    first = DiscoveryLab(tmp_path, allowed_runner_modules=())
    run_id = _rpc(first, "research.begin", spec=_spec().to_dict())["result"]["run_id"]
    assert _rpc(first, "research.consume", run_id=run_id, evaluations=2)["ok"]
    assert _rpc(first, "research.checkpoint", run_id=run_id, state={"cursor": 2})["ok"]
    second = DiscoveryLab(tmp_path, allowed_runner_modules=())  # the first bridge died
    resumed = _rpc(second, "research.resume", run_id=run_id)["result"]
    assert resumed["state"] == {"cursor": 2} and resumed["evaluations"] == 2
    _rpc(second, "research.emit", run_id=run_id, name="steps", kind="table",
         value=[{"step": 0, "draw": 0.5}], schema=STEPS.id)
    _rpc(second, "research.metric", run_id=run_id, name="total", value=0.5)
    assert _rpc(second, "research.finalize", run_id=run_id)["result"]["valid"] is True

    other = _rpc(second, "research.begin", spec=_spec(seed=9).to_dict())["result"]["run_id"]
    failed = _rpc(second, "research.fail", run_id=other, error_type="RustPanic", message="index out of bounds")
    assert failed["result"]["status"] == "failed"
    assert _rpc(second, "research.emit", run_id=other, name="steps", kind="table", value=[],
                schema=STEPS.id)["error"]["code"] == "KeyError"
    assert np.isclose(EvidenceStore(tmp_path).inspect(run_id)["metrics"]["total"]["value"], 0.5)


def test_absolute_input_paths_inside_the_working_directory_are_recorded_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "inputs" / "data.txt"
    data.parent.mkdir()
    data.write_text("v1", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("x", encoding="utf-8")
    try:
        spec = _spec(inputs={"inside": str(data.resolve()), "outside": str(outside.resolve())})
        assert spec.inputs["inside"] == "inputs/data.txt"
        assert spec.inputs["outside"] == str(outside.resolve())  # kept: it must stay locatable
        context = EvidenceStore(tmp_path / "store").begin(_spec(inputs={"inside": str(data.resolve())}))
        recorded = json.loads((context.run_dir / "spec.json").read_text(encoding="utf-8"))
        assert recorded["inputs"] == {"inside": "inputs/data.txt"}
        context.checkpoint()
        assert EvidenceStore(tmp_path / "store").resume(context.run_id).resumed_from == 1
    finally:
        outside.unlink()
