"""Append-only research ledger and the materialised research state.

Every scientific transition is one JSON line in ``ledger.jsonl``. The research
state is a pure fold over those events, so any decision can be reconstructed
by replaying the file. Events are validated against the current state before
they are written; invalid transitions raise ``LedgerError`` and nothing is
appended. Several MCP server processes (one per agent) may write concurrently,
so appends are serialised with a lock file.

Provenance classes (kept separate on purpose):
  FACT        literature evidence with a verified OpenAlex id
  HYPOTHESIS  pre-registered or agent-proposed statements
  RESULT      numbers produced by discolab tools (never by an agent)
  INTERPRETATION / DECISION  agent text, always attributed to its author
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVENT_TYPES = (
    "lab_initialized",
    "evidence_recorded",
    "hypothesis_registered",
    "experiment_proposed",
    "experiments_scored",
    "experiment_selected",
    "experiment_completed",
    "experiment_failed",
    "analysis_recorded",
    "hypothesis_updated",
    "decision_recorded",
)


class LedgerError(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    """SHA-256 of a text file with line endings normalised to LF, so the same
    committed file hashes identically on Windows (CRLF checkout) and POSIX."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@contextmanager
def _locked(lock_path: Path, timeout: float = 30.0):
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() > deadline:
                raise LedgerError(f"could not acquire ledger lock {lock_path}")
            time.sleep(0.02)
    try:
        yield
    finally:
        os.close(fd)
        os.unlink(lock_path)


class Ledger:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "ledger.jsonl"
        self.lock = self.root / ".ledger.lock"

    # ---------------------------------------------------------------- reading
    def events(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def state(self) -> dict:
        return fold(self.events())

    # ---------------------------------------------------------------- writing
    def append(self, etype: str, payload: dict, actor: str) -> dict:
        if etype not in EVENT_TYPES:
            raise LedgerError(f"unknown event type {etype!r}")
        with _locked(self.lock):
            events = self.events()
            state = fold(events)
            event = {
                "seq": len(events) + 1,
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "type": etype,
                "actor": actor,
                "prereg_sha256": state.get("prereg_sha256") or payload.get("prereg_sha256"),
                "payload": payload,
            }
            fold(events + [event])  # validates the transition; raises on error
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, sort_keys=True) + "\n")
        return event


# --------------------------------------------------------------------- fold
def _empty_state() -> dict[str, Any]:
    return {
        "initialized": False,
        "question": None,
        "prereg_sha256": None,
        "hypotheses": {},
        "evidence": [],
        "candidates": {},
        "scoring_rounds": [],
        "selected": None,
        "completed": [],
        "decisions": [],
        "compute_budget_sec": 0.0,
        "compute_used_sec": 0.0,
        "sec_per_generation": None,
        "calibration": {},
        "experiment_counter": 0,
        "next_decision": None,
    }


def _need(cond: bool, msg: str):
    if not cond:
        raise LedgerError(msg)


def fold(events: list[dict]) -> dict:
    s = _empty_state()
    for ev in events:
        _apply(s, ev)
    return s


def _apply(s: dict, ev: dict) -> None:
    t, p = ev["type"], ev["payload"]
    if t != "lab_initialized":
        _need(s["initialized"], "lab must be initialised first")
    if t == "lab_initialized":
        _need(not s["initialized"], "lab already initialised")
        s["initialized"] = True
        s["question"] = p["question"]
        s["prereg_sha256"] = p["prereg_sha256"]
        s["compute_budget_sec"] = float(p["compute_budget_sec"])
        s["sec_per_generation"] = float(p["sec_per_generation"])
        for h in p["hypotheses"]:
            s["hypotheses"][h["id"]] = {**h, "status": "open", "posterior": h["prior"], "history": []}
    elif t == "evidence_recorded":
        _need(bool(p.get("openalex_id") or p.get("arxiv_id")), "evidence requires a verified OpenAlex or arXiv id")
        s["evidence"].append({**p, "seq": ev["seq"], "recorded_by": ev["actor"]})
    elif t == "hypothesis_registered":
        _need(p["id"] not in s["hypotheses"], f"hypothesis {p['id']} already exists")
        s["hypotheses"][p["id"]] = {**p, "status": "open", "posterior": p["prior"], "history": [], "origin": "agent"}
    elif t == "experiment_proposed":
        eid = p["id"]
        _need(eid not in s["candidates"], f"experiment {eid} already proposed")
        for h in p["spec"]["hypotheses"]:
            _need(h in s["hypotheses"], f"experiment targets unknown hypothesis {h}")
        s["experiment_counter"] += 1
        s["candidates"][eid] = {"id": eid, "spec": p["spec"], "status": "proposed",
                                "proposed_by": ev["actor"], "derived": p.get("derived", {})}
    elif t == "experiments_scored":
        for row in p["scores"]:
            _need(row["id"] in s["candidates"], f"scored unknown experiment {row['id']}")
            _need(s["candidates"][row["id"]]["status"] in ("proposed", "scored"),
                  f"experiment {row['id']} is not open for scoring")
            s["candidates"][row["id"]]["status"] = "scored"
            s["candidates"][row["id"]]["score"] = row
        s["scoring_rounds"].append({"round": len(s["scoring_rounds"]) + 1, "seq": ev["seq"], **p})
    elif t == "experiment_selected":
        eid = p["id"]
        _need(s["selected"] is None, f"experiment {s['selected']} is still selected/running")
        _need(bool(s["scoring_rounds"]), "no scoring round exists")
        last = s["scoring_rounds"][-1]
        row = next((r for r in last["scores"] if r["id"] == eid), None)
        _need(row is not None, f"{eid} was not scored in the latest round")
        _need(row["feasible"], f"{eid} is infeasible: {row.get('violations')}")
        _need(s["candidates"][eid]["status"] == "scored",
              f"{eid} is {s['candidates'][eid]['status']}; only scored candidates can be selected")
        s["selected"] = eid
        s["candidates"][eid]["status"] = "selected"
        s["decisions"].append({"kind": "selection", "seq": ev["seq"], "by": ev["actor"], **p})
    elif t == "experiment_completed":
        eid = p["id"]
        _need(s["selected"] == eid, f"{eid} is not the selected experiment")
        c = s["candidates"][eid]
        c["status"] = "completed"
        c["result"] = p["summary"]
        c["artifacts"] = p["artifacts"]
        c["runtime_sec"] = p["runtime_sec"]
        s["compute_used_sec"] += float(p["runtime_sec"])
        s["calibration"].update(p.get("calibration", {}))
        s["selected"] = None
        s["completed"].append(eid)
    elif t == "experiment_failed":
        # A crashed or aborted run releases the selection; its id is never reused
        # (artifacts are immutable), so a retry must be proposed afresh.
        eid = p["id"]
        _need(s["selected"] == eid, f"{eid} is not the selected experiment")
        c = s["candidates"][eid]
        c["status"] = "failed"
        c["error"] = p["error"]
        s["selected"] = None
    elif t == "analysis_recorded":
        eid = p["id"]
        _need(eid in s["completed"], f"{eid} has not completed")
        _need(s["candidates"][eid]["status"] == "completed", f"{eid} already analysed")
        s["candidates"][eid]["status"] = "analyzed"
        s["candidates"][eid]["analysis"] = {**p, "by": ev["actor"]}
    elif t == "hypothesis_updated":
        hid = p["id"]
        _need(hid in s["hypotheses"], f"unknown hypothesis {hid}")
        src = p.get("experiment")
        if src is not None:
            _need(s["candidates"].get(src, {}).get("status") == "analyzed",
                  f"hypothesis update cites {src}, which has no recorded analysis")
        h = s["hypotheses"][hid]
        h["history"].append({"seq": ev["seq"], "from": h["posterior"], **p})
        h["posterior"] = float(p["posterior"])
        h["status"] = p["status"]
        if "effect" in p:
            h["latest_effect"] = p["effect"]
    elif t == "decision_recorded":
        s["decisions"].append({"kind": "next_step", "seq": ev["seq"], "by": ev["actor"], **p})
        s["next_decision"] = p
    else:  # pragma: no cover
        raise LedgerError(f"unhandled event {t}")


def public_state(state: dict) -> dict:
    """Compact view for agents (drops bulky fields such as fitted model weights)."""
    s = copy.deepcopy(state)
    for c in s["candidates"].values():
        res = c.get("result")
        if isinstance(res, dict):
            res.pop("models", None)
    return s
