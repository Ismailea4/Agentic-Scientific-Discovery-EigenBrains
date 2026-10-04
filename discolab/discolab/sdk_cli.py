"""Inspect, list, validate, compare, decide, reproduce, resume, and bundle SDK evidence runs.

Results are JSON on stdout (exit 0). Failures are one JSON line on stderr,
{"ok": false, "error": {"code": ..., "message": ...}, "exit_code": N}, with
exit codes: 2 invalid usage or value, 3 validation/integrity failure,
4 not found, 5 refused lifecycle transition, 6 budget exceeded,
7 refused by policy, 1 anything else.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .bundle import verify_bundle
from .evidence import BudgetExceeded, EvidenceError, EvidenceStore, ValidationError, resume_run

EXIT_CODES: tuple[tuple[type[BaseException], int], ...] = (
    (ValidationError, 3),
    (BudgetExceeded, 6),
    (EvidenceError, 5),
    (FileNotFoundError, 4),
    (KeyError, 4),
    (PermissionError, 7),
    (FileExistsError, 5),
    (ValueError, 2),
)
MAX_MESSAGE = 2000


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # structured usage errors too
        raise ValueError(f"usage: {message}")


def exit_code(error: BaseException) -> int:
    for kind, code in EXIT_CODES:
        if isinstance(error, kind):
            return code
    return 1


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="eigenbrains-sdk", description=__doc__,
                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="research project root")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    for command in ("inspect", "validate", "reproduce", "resume"):
        sub.add_parser(command).add_argument("run_id")
    listing = sub.add_parser("list")
    listing.add_argument("--capability")
    listing.add_argument("--status")
    listing.add_argument("--seed", type=int)
    listing.add_argument("--since", help="created at or after (ISO-8601)")
    listing.add_argument("--until", help="created at or before (ISO-8601)")
    compare = sub.add_parser("compare")
    compare.add_argument("left")
    compare.add_argument("right")
    accept = sub.add_parser("accept")
    accept.add_argument("run_id")
    accept.add_argument("--rationale", required=True)
    reject = sub.add_parser("reject")
    reject.add_argument("run_id")
    reject.add_argument("--reason", required=True)
    sub.add_parser("lineage")
    export = sub.add_parser("export")
    export.add_argument("run_ids", nargs="+")
    export.add_argument("--out", required=True, help="bundle path (.zip) or directory with --directory")
    export.add_argument("--directory", action="store_true", help="write an unpacked bundle directory")
    verify = sub.add_parser("verify-bundle")
    verify.add_argument("path")
    return parser


def run(argv: list[str] | None = None) -> Any:
    args = _parser().parse_args(argv)
    if args.command == "verify-bundle":
        return verify_bundle(args.path)
    store = EvidenceStore(args.root)
    if args.command == "list":
        return store.list(capability=args.capability, status=args.status, seed=args.seed,
                          created_after=args.since, created_before=args.until)
    if args.command == "inspect":
        return store.inspect(args.run_id)
    if args.command == "validate":
        return store.validate(args.run_id)
    if args.command == "compare":
        return store.compare(args.left, args.right)
    if args.command == "accept":
        return store.accept(args.run_id, args.rationale)
    if args.command == "reject":
        return store.reject(args.run_id, args.reason)
    if args.command == "lineage":
        return store.lineage()
    if args.command == "export":
        manifest = store.export_bundle(args.run_ids, args.out, archive=not args.directory)
        return {"content_sha256": manifest["content_sha256"], "runs": manifest["runs"],
                "files": len(manifest["files"])}
    if args.command == "resume":
        return resume_run(store.root, args.run_id)
    return store.reproduce(args.run_id)


def main(argv: list[str] | None = None) -> int:
    try:
        _print(run(argv))
        return 0
    except Exception as error:
        code = exit_code(error)
        message = str(error.args[0]) if isinstance(error, KeyError) and error.args else str(error)
        if len(message) > MAX_MESSAGE:
            message = message[:MAX_MESSAGE] + " ..."
        sys.stderr.write(json.dumps({"ok": False, "error": {"code": type(error).__name__, "message": message},
                                     "exit_code": code}) + "\n")
        return code


if __name__ == "__main__":
    raise SystemExit(main())
