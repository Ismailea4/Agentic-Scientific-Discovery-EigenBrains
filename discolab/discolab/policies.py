"""Omnigent policy: a human must approve any run that spends held-out data.

Wired in the PI's config.yaml under guardrails.policies. Running a
confirmatory experiment is the consequential, irreversible action in this
lab (held-out landscapes can only be seen for the first time once), so it is
routed to a human through Omnigent's ASK mechanism instead of an agent.
"""

from __future__ import annotations

from .ledger import Ledger

_ALLOW = {"result": "ALLOW"}


def approve_confirmatory_runs(event: dict) -> dict:
    if event.get("type") != "tool_call":
        return _ALLOW
    data = event.get("data") or {}
    if not str(data.get("name", "")).endswith("run_experiment"):
        return _ALLOW
    try:
        from .lab import lab_root

        state = Ledger(lab_root()).state()
    except Exception as exc:  # fail closed: cannot see the state, so ask a human
        return {"result": "ASK", "reason": f"Cannot read lab state ({exc}); approve running the experiment?"}
    eid = state.get("selected")
    cand = state["candidates"].get(eid) if eid else None
    if cand and cand.get("derived", {}).get("stage") == "confirmatory":
        land = ", ".join(cand["spec"]["landscapes"])
        return {"result": "ASK",
                "reason": f"{eid} is a CONFIRMATORY run on held-out landscapes ({land}). "
                          "Held-out data can only be used once. Approve?"}
    return _ALLOW
