"""Command line for the lab:  python -m discolab.cli <command>

  init              create the ledger in $DISCOLAB_HOME (fails if one exists)
  state             compact research state
  result <E#>       compact result of one experiment
  trace             one line per ledger event (who did what, when)
  abort <E#> <why>  release a selected experiment whose run was interrupted
  run-selected <actor>  run the selected experiment (used by the MCP server's worker process)
"""

from __future__ import annotations

import json
import sys

from . import lab
from .ledger import Ledger
from .views import result_summary, state_summary


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    cmd, *rest = argv
    if cmd == "init":
        s = lab.init_lab()
        print(json.dumps({"initialised": str(lab.lab_root()), "hypotheses": list(s["hypotheses"])}, indent=2))
    elif cmd == "state":
        print(json.dumps(state_summary(Ledger(lab.lab_root()).state()), indent=2))
    elif cmd == "result":
        s = Ledger(lab.lab_root()).state()
        print(json.dumps(result_summary(s["candidates"][rest[0]]), indent=2))
    elif cmd == "run-selected":
        out = lab.run_selected_experiment(rest[0] if rest else "operator")
        print(json.dumps({"id": out["id"], "runtime_sec": out["runtime_sec"]}))
    elif cmd == "abort":
        print(json.dumps(lab.abort_experiment(rest[0], " ".join(rest[1:]) or "operator abort", "operator")))
    elif cmd == "trace":
        for e in Ledger(lab.lab_root()).events():
            p = e["payload"]
            what = p.get("id") or p.get("decision") or p.get("openalex_id") or ""
            extra = ""
            if e["type"] == "experiments_scored":
                extra = "argmax=" + str(p["argmax"]) + " " + ", ".join(
                    f"{r['id']}:U={r['utility']}{'' if r['feasible'] else '(infeasible)'}" for r in p["scores"])
            elif e["type"] == "hypothesis_updated":
                extra = f"{p.get('verdict')} -> posterior {p['posterior']:.3f} ({p['status']})"
            elif e["type"] == "experiment_selected":
                extra = f"followed_argmax={p['followed_argmax']}"
            print(f"{e['seq']:>3} {e['ts'][11:19]} {e['actor']:<16} {e['type']:<22} {str(what)[:60]} {extra}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
