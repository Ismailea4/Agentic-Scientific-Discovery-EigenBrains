"""Read-only HTTP/SSE bridge from the lab's files to the EigenBrains UI.

    python -m discolab.bridge --port 8765

Serves live labs (lab_home/<name>) and committed records (results/<name>).
Everything returned is read from the ledger, the Omnigent event log or the raw
trace artifacts; the bridge computes summaries (means over runs) but never
invents values. It writes nothing.

  GET /lab/sources                      available labs and records
  GET /lab/state?source=...             state, hypothesis trajectories, scoring rounds, decisions
  GET /lab/activity?source=...          agent handoffs, tool calls and messages (Omnigent stream)
  GET /lab/experiment?source=...&id=E#  compact result + per-generation curves from traces.npz
  GET /lab/stream?source=...            SSE: new ledger events ("ledger") and agent activity ("agent")
"""

from __future__ import annotations

import argparse
import json
import time
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

from .ledger import fold
from .views import result_summary, state_summary

ROOT = Path(__file__).resolve().parent.parent
ALLOWED = ("lab_home", "results")
POLL_SEC = 0.5


def resolve_source(source: str) -> Path:
    parts = Path(source).parts
    if len(parts) != 2 or parts[0] not in ALLOWED or parts[1] in ("..", "."):
        raise ValueError("source must be lab_home/<name> or results/<name>")
    p = (ROOT / source).resolve()
    if ROOT.resolve() not in p.parents or not (p / "ledger.jsonl").exists():
        raise ValueError(f"no ledger at {source}")
    return p


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def list_sources() -> list[dict]:
    out = []
    for kind, base in (("live", "lab_home"), ("record", "results")):
        d = ROOT / base
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if (p / "ledger.jsonl").exists():
                events = read_jsonl(p / "ledger.jsonl")
                out.append({"id": f"{base}/{p.name}", "kind": kind, "events": len(events),
                            "experiments": sum(e["type"] == "experiment_completed" for e in events),
                            "prereg_sha256": events[0]["prereg_sha256"] if events else None})
    return out


def lab_state(path: Path) -> dict:
    events = read_jsonl(path / "ledger.jsonl")
    s = fold(events)
    summary = state_summary(s)
    trajectories = {}
    for hid, h in s["hypotheses"].items():
        pts = [{"seq": 0, "posterior": float(h.get("prior", 0.5)), "label": "prior"}]
        for e in h["history"]:
            pts.append({"seq": e["seq"], "posterior": float(e["posterior"]), "verdict": e.get("verdict"),
                        "experiment": e.get("experiment"),
                        "label": e.get("experiment") or e.get("reason", "coupling")})
        trajectories[hid] = pts
    rounds = []
    selections = {d["seq"]: d for d in s["decisions"] if d["kind"] == "selection"}
    for r in s["scoring_rounds"]:
        chosen = next((d for seq, d in sorted(selections.items()) if seq > r["seq"]), None)
        rounds.append({"round": r["round"], "seq": r["seq"], "argmax": r["argmax"],
                       "selected": chosen["id"] if chosen else None,
                       "followed_argmax": chosen.get("followed_argmax") if chosen else None,
                       "justification": chosen.get("justification") if chosen else None,
                       "rows": [{"id": x["id"], "title": x["title"], "kind": x["kind"], "stage": x["stage"],
                                 "eig_bits": x["eig_bits"], "utility": x["utility"], "feasible": x["feasible"],
                                 "violations": x["violations"], "est_wall_seconds": x["cost"]["wall_seconds"],
                                 "hypotheses": list(x["hypotheses"])} for x in r["scores"]]})
    decisions = [{"seq": d["seq"], "by": d["by"], "decision": d.get("decision"), "rationale": d.get("rationale"),
                  "next_experiment": d.get("next_experiment")} for d in s["decisions"] if d["kind"] == "next_step"]
    analyses = {eid: {"by": c["analysis"]["by"], "interpretation": c["analysis"]["interpretation"],
                      "threats_to_validity": c["analysis"]["threats_to_validity"]}
                for eid, c in s["candidates"].items() if c.get("analysis")}
    return {**summary, "events": len(events), "prereg_sha256": s["prereg_sha256"],
            "trajectories": trajectories, "rounds": rounds, "decisions": decisions, "analyses": analyses,
            "completed": s["completed"]}


# ----------------------------------------------------------------- activity
def _short(x, n=160) -> str:
    s = x if isinstance(x, str) else json.dumps(x, default=str)
    return s if len(s) <= n else s[: n - 1] + "…"


def activity(rows: list[dict], names: dict | None = None) -> tuple[list[dict], dict]:
    """Compact agent activity from Omnigent stream events (handoffs, tool calls, messages)."""
    names = dict(names or {})
    seen = set()
    out = []
    for r in rows:
        t, sid = r.get("type"), r.get("session")
        if t == "driver.session_created":
            names[sid] = "pi"
            continue
        if t == "session.child_session.updated":
            ch = r.get("child") or {}
            cid = r.get("child_session_id")
            if ch.get("tool"):
                names[cid] = ch["tool"]
            if ch.get("title") and ch.get("busy") is not None:
                key = (cid, bool(ch["busy"]))
                # a child reports busy=false while launching; only "finished" after "running" counts
                if key in seen or (not ch["busy"] and (cid, True) not in seen):
                    continue
                seen.add(key)
                out.append({"t": r["t"], "kind": "handoff", "from": names.get(sid, "pi"), "to": ch.get("tool"),
                            "title": ch["title"], "state": "running" if ch["busy"] else "finished"})
            continue
        if t == "response.elicitation_request":
            out.append({"t": r["t"], "kind": "approval", "agent": names.get(sid, "?"),
                        "text": _short((r.get("params") or {}).get("message", ""), 240)})
            continue
        if t != "response.output_item.done":
            continue
        item = r.get("item") or {}
        if item.get("type") == "function_call" and item.get("status") == "completed":
            cid = item.get("call_id")
            # the harness reports each call twice under different call ids: dedupe on content too
            sig = (sid, item.get("name"), item.get("arguments"), round(r["t"]))
            if cid in seen or sig in seen or item.get("name") == "ToolSearch":
                continue
            seen.update((cid, sig))
            out.append({"t": r["t"], "kind": "tool", "agent": names.get(sid, "?"),
                        "name": item.get("name", "").removeprefix("lab__"),
                        "args": _short(item.get("arguments", ""), 200)})
        elif item.get("type") == "message" and item.get("role") == "assistant":
            text = " ".join(c.get("text", "") for c in item.get("content", []) if isinstance(c, dict)).strip()
            if text:
                out.append({"t": r["t"], "kind": "say", "agent": names.get(sid, "?"), "text": _short(text, 600)})
    return out, names


# ------------------------------------------------------------------- curves
@lru_cache(maxsize=32)
def _curves(path_str: str, mtime: float) -> dict:
    path = Path(path_str)
    z = np.load(path)
    groups: dict[tuple[str, str], dict[str, list]] = {}
    for key in z.files:
        tag, land, seed, ctrl, col = key.split("|")
        if tag != "eval" or col not in ("best_err", "H", "p_mut", "epoch"):
            continue
        groups.setdefault((land, ctrl), {}).setdefault(col, []).append(z[key])
    out: dict[str, dict] = {}
    for (land, ctrl), cols in sorted(groups.items()):
        err = np.log10(np.vstack(cols["best_err"]) + 1e-12)
        epoch = cols["epoch"][0]
        shifts = [int(i) for i in np.flatnonzero(np.diff(epoch)) + 1]
        out.setdefault(land, {"shifts": shifts, "controllers": {}})["controllers"][ctrl] = {
            "n_runs": int(err.shape[0]),
            "log10_best_err_mean": np.round(err.mean(axis=0), 4).tolist(),
            "entropy_mean": np.round(np.vstack(cols["H"]).mean(axis=0), 4).tolist(),
            "p_mut_mean": np.round(np.vstack(cols["p_mut"]).mean(axis=0), 5).tolist(),
        }
    return out


def experiment(path: Path, eid: str) -> dict:
    s = fold(read_jsonl(path / "ledger.jsonl"))
    if eid not in s["candidates"]:
        raise ValueError(f"unknown experiment {eid}")
    cand = s["candidates"][eid]
    res = result_summary(cand)
    traces = path / "runs" / eid / "traces.npz"
    res["curves"] = _curves(str(traces), traces.stat().st_mtime) if traces.exists() else None
    res["spec"] = cand["spec"]
    res["score"] = {k: (cand.get("score") or {}).get(k) for k in ("eig_bits", "utility", "cost")}
    return res


# ------------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    server_version = "discolab-bridge/0.1"

    def log_message(self, fmt, *args):  # quiet: no request logging
        return

    def _json(self, obj, status=200):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path == "/lab/sources":
                return self._json({"sources": list_sources()})
            src = resolve_source(q.get("source", ""))
            if url.path == "/lab/state":
                return self._json(lab_state(src))
            if url.path == "/lab/activity":
                acts, _ = activity(read_jsonl(src / "omnigent_events.jsonl"))
                return self._json({"activity": acts})
            if url.path == "/lab/experiment":
                return self._json(experiment(src, q.get("id", "")))
            if url.path == "/lab/stream":
                return self._stream(src)
            return self._json({"error": {"code": "not_found", "message": url.path}}, 404)
        except ValueError as exc:
            return self._json({"error": {"code": "bad_request", "message": str(exc)}}, 400)

    def _stream(self, src: Path):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        ledger, events = src / "ledger.jsonl", src / "omnigent_events.jsonl"
        n_ledger = len(read_jsonl(ledger))
        n_events = len(read_jsonl(events))
        _, names = activity(read_jsonl(events))
        last_beat = 0.0
        try:
            while True:
                rows = read_jsonl(ledger)
                for e in rows[n_ledger:]:
                    self._sse("ledger", {"seq": e["seq"], "ts": e["ts"], "type": e["type"], "actor": e["actor"],
                                         "id": e["payload"].get("id")})
                n_ledger = len(rows)
                ev_rows = read_jsonl(events)
                acts, names = activity(ev_rows[n_events:], names)
                for a in acts:
                    self._sse("agent", a)
                n_events = len(ev_rows)
                if time.time() - last_beat > 5:
                    self._sse("heartbeat", {"t": time.time()})
                    last_beat = time.time()
                time.sleep(POLL_SEC)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def _sse(self, name: str, data: dict):
        self.wfile.write(f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n".encode("utf-8"))
        self.wfile.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"discolab bridge on http://127.0.0.1:{args.port}/lab/sources", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
