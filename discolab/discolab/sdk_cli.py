"""Inspect, validate, compare, accept, or reproduce SDK evidence runs."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .evidence import EvidenceStore


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="research project root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "validate", "reproduce"):
        child = subparsers.add_parser(command)
        child.add_argument("run_id")
    compare = subparsers.add_parser("compare")
    compare.add_argument("left")
    compare.add_argument("right")
    accept = subparsers.add_parser("accept")
    accept.add_argument("run_id")
    accept.add_argument("--rationale", required=True)
    args = parser.parse_args(argv)
    store = EvidenceStore(args.root)
    if args.command == "inspect":
        result = store.inspect(args.run_id)
    elif args.command == "validate":
        result = store.validate(args.run_id)
    elif args.command == "compare":
        result = store.compare(args.left, args.right)
    elif args.command == "accept":
        result = store.accept(args.run_id, args.rationale)
    else:
        result = store.reproduce(args.run_id)
    _print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
