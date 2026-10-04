"""Drive one Omnigent PI session headlessly and record its event stream.

  python scripts/run_session.py --port 6810 --prompt "Run 2 discovery rounds."

Creates a session for the discolab-pi agent on the online host (workspace =
the discolab directory), posts the prompt, prints agent handoffs and lab tool
calls as they happen, and appends every stream event to
$DISCOLAB_HOME/omnigent_events.jsonl. Human-approval requests (Omnigent ASK
policies) are put to the operator on the terminal; with no terminal attached
they are declined (fail closed), never auto-approved.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx
from omnigent_client import OmnigentClient

ROOT = Path(__file__).resolve().parent.parent


def _short(obj, n=160) -> str:
    s = obj if isinstance(obj, str) else json.dumps(obj, default=str)
    return s if len(s) <= n else s[: n - 3] + "..."


class Recorder:
    def __init__(self, path: Path):
        self.fh = path.open("a", encoding="utf-8")

    def write(self, session_id: str, d: dict):
        self.fh.write(json.dumps({"t": time.time(), "session": session_id, **d}, default=str) + "\n")
        self.fh.flush()


async def approve(client, sid: str, d: dict) -> None:
    msg = (d.get("params") or {}).get("message") or "Approve?"
    print(f"\n*** HUMAN APPROVAL REQUESTED: {msg}", flush=True)
    if sys.stdin.isatty():
        ans = await asyncio.to_thread(input, "approve? [y/N] ")
        action = "accept" if ans.strip().lower() in ("y", "yes") else "decline"
    else:
        action = "decline"
        print("*** no terminal attached: declining (fail closed)", flush=True)
    await client.sessions.resolve_elicitation(sid, d["elicitation_id"], {"action": action})
    print(f"*** approval {action}ed", flush=True)


async def tail(client, sid: str, label: str, rec: Recorder, state: dict, children: set):
    try:
        await _tail(client, sid, label, rec, state, children)
    except (httpx.HTTPError, asyncio.CancelledError):
        return  # stream closed (session ended or driver shutting down)


async def _tail(client, sid: str, label: str, rec: Recorder, state: dict, children: set):
    seen_calls = set()
    async for ev in client.sessions.stream(sid):
        d = ev.model_dump() if hasattr(ev, "model_dump") else dict(ev)
        t = d.get("type", "")
        if "delta" in t or t.endswith("heartbeat") or t == "session.presence":
            continue
        rec.write(sid, d)
        if t == "session.status" and label == "pi":
            state["status"] = d.get("status")
            state["changed"] = time.time()
        elif t == "session.created" and d.get("child_session_id"):
            cid = d["child_session_id"]
            if cid not in children:
                children.add(cid)
                asyncio.create_task(tail(client, cid, f"child:{cid[:6]}", rec, state, children))
        elif t == "session.child_session.updated":
            ch = d.get("child") or {}
            busy = ch.get("busy")
            state.setdefault("busy", {})[d.get("child_session_id")] = bool(busy)
            state["changed"] = time.time()
            if ch.get("title") and busy is not None:
                print(f"[{label}] handoff {ch['title']}: {'running' if busy else 'finished'}", flush=True)
        elif t == "response.elicitation_request":
            await approve(client, sid, d)
        elif t == "response.output_item.done":
            item = d.get("item") or {}
            if item.get("type") == "function_call" and item.get("status") == "completed":
                cid = item.get("call_id")
                if cid in seen_calls or item.get("name") == "ToolSearch":
                    continue
                seen_calls.add(cid)
                print(f"[{label}] tool {item['name']}({_short(item.get('arguments', ''), 140)})", flush=True)
            elif item.get("type") == "message" and item.get("role") == "assistant":
                text = " ".join(c.get("text", "") for c in item.get("content", []) if isinstance(c, dict))
                if text.strip():
                    print(f"[{label}] says: {_short(text.strip(), 400)}", flush=True)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=6810)
    ap.add_argument("--agent", default="discolab-pi")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--idle-grace", type=int, default=30)
    args = ap.parse_args()
    url = f"http://127.0.0.1:{args.port}"
    home = Path(os.environ["DISCOLAB_HOME"])
    rec = Recorder(home / "omnigent_events.jsonl")
    async with OmnigentClient(base_url=url) as client:
        agent = await client.sessions.resolve_agent(args.agent)
        hosts = httpx.get(f"{url}/v1/hosts", timeout=10).json()["hosts"]
        host = next(h for h in hosts if h["status"] == "online")
        r = httpx.post(f"{url}/v1/sessions", timeout=60, json={
            "agent_id": agent.id, "host_id": host["host_id"], "workspace": str(ROOT),
            "title": "discolab discovery loop"})
        r.raise_for_status()
        sid = r.json().get("session_id") or r.json().get("id")
        print(f"PI session {sid}  (web UI: {url})", flush=True)
        rec.write(sid, {"type": "driver.session_created", "agent": args.agent, "prompt": args.prompt})
        state: dict = {"status": None, "changed": time.time()}
        children: set = set()
        task = asyncio.create_task(tail(client, sid, "pi", rec, state, children))
        await asyncio.sleep(1.0)
        await client.sessions.post_event(sid, {"type": "message", "data": {
            "role": "user", "content": [{"type": "input_text", "text": args.prompt}]}})
        t0 = time.time()
        while time.time() - t0 < args.timeout:
            await asyncio.sleep(5)
            busy = any(state.get("busy", {}).values())
            if state["status"] == "failed":
                print("\nPI session FAILED; see omnigent_events.jsonl for the error", flush=True)
                break
            if state["status"] == "idle" and not busy and time.time() - state["changed"] > args.idle_grace:
                break
        task.cancel()
        print(f"\nsession finished: status={state['status']} after {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
