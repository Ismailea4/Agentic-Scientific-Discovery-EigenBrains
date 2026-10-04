"""Versioned JSON-lines bridge used by the Rust and Julia SDKs.

Run ``python -m discolab.rpc --root PATH --actor NAME`` and send one request per
line on stdin.  Exactly one response is emitted for each request.  The bridge
contains no scientific logic; it delegates to :class:`DiscoveryLab`.

Security boundary: the bridge never executes caller-supplied code or shell
commands. The method table below is closed (no attribute lookup by name),
unknown parameters are rejected, bundle paths are names inside the lab root,
and a run may name an importable Python runner only when the bridge was started
with ``--allow-runner-module`` for that module (reproduce/resume would import it).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any, Callable

from .sdk import DiscoveryLab, PROTOCOL_VERSION


@dataclass(frozen=True)
class Method:
    call: Callable[[DiscoveryLab, dict[str, Any]], Any]
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    mutating: bool = False


def _filters(p: dict[str, Any]) -> dict[str, Any]:
    return {k: p.get(k) for k in ("capability", "status", "seed", "created_after", "created_before")}


METHODS: dict[str, Method] = {
    "describe": Method(lambda c, p: c.describe()),
    "initialize": Method(lambda c, p: c.initialize(), mutating=True),
    "state": Method(lambda c, p: c.state()),
    "events": Method(lambda c, p: c.events()),
    "propose": Method(lambda c, p: c.propose(p["experiment"]), ("experiment",), mutating=True),
    "score": Method(lambda c, p: c.score(), mutating=True),
    "select": Method(lambda c, p: c.select(p["experiment_id"], p["justification"]),
                     ("experiment_id", "justification"), mutating=True),
    "run": Method(lambda c, p: c.run(confirm_heldout=bool(p.get("confirm_heldout", False))),
                  optional=("confirm_heldout",), mutating=True),
    "abort": Method(lambda c, p: c.abort(p["experiment_id"], p["reason"]), ("experiment_id", "reason"),
                    mutating=True),
    "result": Method(lambda c, p: c.result(p["experiment_id"]), ("experiment_id",)),
    "analyze": Method(lambda c, p: c.analyze(p["experiment_id"], p["interpretation"],
                                             p.get("threats_to_validity", [])),
                      ("experiment_id", "interpretation"), ("threats_to_validity",), mutating=True),
    "decide": Method(lambda c, p: c.decide(p["decision"], p["rationale"], p.get("next_experiment")),
                     ("decision", "rationale"), ("next_experiment",), mutating=True),
    "register_hypothesis": Method(lambda c, p: c.register_hypothesis(**p),
                                  ("hypothesis_id", "statement", "h0", "family"),
                                  ("feature_set", "baseline_feature_set", "controller", "comparator"),
                                  mutating=True),
    "research.begin": Method(lambda c, p: c.begin_research_run(p["spec"]), ("spec",), mutating=True),
    "research.emit": Method(lambda c, p: c.emit_research_artifact(**p), ("run_id", "name", "kind", "value", "schema"),
                            ("stage", "parents"), mutating=True),
    "research.metric": Method(lambda c, p: c.record_research_metric(**p), ("run_id", "name", "value"), ("spec",),
                              mutating=True),
    "research.consume": Method(lambda c, p: c.consume_research_budget(**p), ("run_id",), ("evaluations",),
                               mutating=True),
    "research.checkpoint": Method(lambda c, p: c.checkpoint_research_run(p["run_id"], p.get("state")),
                                  ("run_id",), ("state",), mutating=True),
    "research.resume": Method(lambda c, p: c.resume_research_run(p["run_id"]), ("run_id",), mutating=True),
    "research.fail": Method(lambda c, p: c.fail_research_run(p["run_id"], p["error_type"], p["message"]),
                            ("run_id", "error_type", "message"), mutating=True),
    "research.finalize": Method(lambda c, p: c.finalize_research_run(p["run_id"]), ("run_id",), mutating=True),
    "research.inspect": Method(lambda c, p: c.inspect_research_run(p["run_id"]), ("run_id",)),
    "research.validate": Method(lambda c, p: c.validate_research_run(p["run_id"]), ("run_id",), mutating=True),
    "research.list": Method(lambda c, p: c.list_research_runs(**_filters(p)),
                            optional=("capability", "status", "seed", "created_after", "created_before")),
    "research.compare": Method(lambda c, p: c.compare_research_runs(p["left"], p["right"]), ("left", "right")),
    "research.accept": Method(lambda c, p: c.accept_research_run(p["run_id"], p["rationale"]),
                              ("run_id", "rationale"), mutating=True),
    "research.reject": Method(lambda c, p: c.reject_research_run(p["run_id"], p["reason"]),
                              ("run_id", "reason"), mutating=True),
    "research.reproduce": Method(lambda c, p: c.reproduce_research_run(p["run_id"]), ("run_id",), mutating=True),
    "research.lineage": Method(lambda c, p: c.research_lineage()),
    "research.export_bundle": Method(lambda c, p: c.export_research_bundle(p["run_ids"], p["name"]),
                                     ("run_ids", "name"), mutating=True),
    "research.verify_bundle": Method(lambda c, p: c.verify_research_bundle(p["name"]), ("name",)),
}


def dispatch(client: DiscoveryLab, method: str, params: dict[str, Any]) -> Any:
    spec = METHODS.get(method)
    if spec is None:
        raise ValueError(f"unknown SDK method {method!r}")
    missing = [name for name in spec.required if name not in params]
    if missing:
        raise ValueError(f"{method}: missing required params {missing}")
    unknown = sorted(set(params) - set(spec.required) - set(spec.optional))
    if unknown:
        raise ValueError(f"{method}: unknown params {unknown}")
    return spec.call(client, params)


def handle_request(client: DiscoveryLab, request: dict[str, Any]) -> dict[str, Any]:
    request_id = request.get("id") if isinstance(request, dict) else None
    try:
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        if request.get("version") != PROTOCOL_VERSION:
            raise ValueError(f"protocol version must be {PROTOCOL_VERSION!r}")
        method = request.get("method")
        if not isinstance(method, str):
            raise ValueError("method must be a string")
        params = request.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ValueError("params must be an object")
        return {"id": request_id, "version": PROTOCOL_VERSION, "ok": True,
                "result": dispatch(client, method, params)}
    except Exception as exc:
        return {"id": request_id, "version": PROTOCOL_VERSION, "ok": False,
                "error": {"code": type(exc).__name__, "message": str(exc)}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True)
    parser.add_argument("--actor", default="rpc-sdk")
    parser.add_argument("--allow-runner-module", action="append", default=[], metavar="MODULE",
                        help="permit runs naming a Python runner in MODULE (repeatable; default: none)")
    args = parser.parse_args(argv)
    client = DiscoveryLab(args.root, actor=args.actor, allowed_runner_modules=args.allow_runner_module)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = handle_request(client, request)
            text = json.dumps(response, separators=(",", ":"), allow_nan=False)
        except Exception as exc:
            text = json.dumps({"id": None, "version": PROTOCOL_VERSION, "ok": False,
                               "error": {"code": type(exc).__name__, "message": str(exc)}},
                              separators=(",", ":"))
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
