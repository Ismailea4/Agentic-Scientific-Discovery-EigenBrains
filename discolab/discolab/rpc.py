"""Versioned JSON-lines bridge used by the Rust and Julia SDKs.

Run ``python -m discolab.rpc --root PATH --actor NAME`` and send one request per
line on stdin.  Exactly one response is emitted for each request.  The bridge
contains no scientific logic; it delegates to :class:`DiscoveryLab`.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .sdk import DiscoveryLab, PROTOCOL_VERSION


def dispatch(client: DiscoveryLab, method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return client.initialize()
    if method == "state":
        return client.state()
    if method == "events":
        return client.events()
    if method == "propose":
        return client.propose(params["experiment"])
    if method == "score":
        return client.score()
    if method == "select":
        return client.select(params["experiment_id"], params["justification"])
    if method == "run":
        return client.run(confirm_heldout=bool(params.get("confirm_heldout", False)))
    if method == "abort":
        return client.abort(params["experiment_id"], params["reason"])
    if method == "result":
        return client.result(params["experiment_id"])
    if method == "analyze":
        return client.analyze(params["experiment_id"], params["interpretation"],
                              params.get("threats_to_validity", []))
    if method == "decide":
        return client.decide(params["decision"], params["rationale"], params.get("next_experiment"))
    if method == "register_hypothesis":
        return client.register_hypothesis(**params)
    raise ValueError(f"unknown SDK method {method!r}")


def handle_request(client: DiscoveryLab, request: dict[str, Any]) -> dict[str, Any]:
    request_id = request.get("id")
    try:
        if request.get("version") != PROTOCOL_VERSION:
            raise ValueError(f"protocol version must be {PROTOCOL_VERSION!r}")
        method = request.get("method")
        if not isinstance(method, str):
            raise ValueError("method must be a string")
        params = request.get("params", {})
        if not isinstance(params, dict):
            raise ValueError("params must be an object")
        return {"id": request_id, "version": PROTOCOL_VERSION, "ok": True,
                "result": dispatch(client, method, params)}
    except Exception as exc:
        return {"id": request_id, "version": PROTOCOL_VERSION, "ok": False,
                "error": {"code": type(exc).__name__, "message": str(exc)}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--actor", default="rpc-sdk")
    args = parser.parse_args(argv)
    client = DiscoveryLab(args.root, actor=args.actor)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = handle_request(client, request)
        except Exception as exc:
            response = {"id": None, "version": PROTOCOL_VERSION, "ok": False,
                        "error": {"code": type(exc).__name__, "message": str(exc)}}
        sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
