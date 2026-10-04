"""Run the judge-facing Python -> Rust -> Julia interoperability proof."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPOSITORY = Path(__file__).resolve().parents[2]
DISCOLAB_SOURCE = REPOSITORY / "discolab"
if str(DISCOLAB_SOURCE) not in sys.path:
    sys.path.insert(0, str(DISCOLAB_SOURCE))

from discolab import EvidenceStore, ResourceBudget, verify_bundle  # noqa: E402
from sdk.interop.study import (  # noqa: E402
    DEFAULT_BUDGET,
    DEFAULT_PARAMETERS,
    PROTOCOL,
    TOLERANCE,
    produce_fixture,
    verify_languages,
)


def _tool(value: str, label: str) -> str:
    candidate = Path(value)
    if candidate.is_file():
        return str(candidate.resolve())
    resolved = shutil.which(value)
    if resolved:
        return resolved
    raise RuntimeError(f"{label} executable not found: {value!r}")


def _run_json(command: list[str], *, env: dict[str, str], label: str) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=REPOSITORY,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"{label} failed with exit code {completed.returncode}:\n{detail}")
    for line in reversed(completed.stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError(f"{label} produced no JSON result:\n{completed.stdout}")


def _artifact(root: Path, run_id: str, stage: str, filename: str) -> Path:
    path = root / "research-runs" / run_id / "artifacts" / stage / filename
    if not path.is_file():
        raise RuntimeError(f"expected artifact is missing: {path}")
    return path.resolve()


def execute(root: Path, *, cargo: str, julia: str) -> dict[str, Any]:
    if root.exists() and any(root.iterdir()):
        raise RuntimeError(f"refusing to mix a new proof with existing files: {root}")
    root.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(DISCOLAB_SOURCE) + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    environment["PYTHON"] = sys.executable

    python_report = produce_fixture.run(
        root,
        parameters=DEFAULT_PARAMETERS,
        seed=2026,
        budget=DEFAULT_BUDGET,
    )
    python_run = python_report["run_id"]
    population = _artifact(root, python_run, "raw", "population.npy")
    predictions = _artifact(root, python_run, "raw", "predictions.jsonl")
    reference = _artifact(root, python_run, "raw", "python_reference.json")

    rust = _run_json(
        [
            cargo,
            "run",
            "--quiet",
            "--release",
            "--manifest-path",
            str(REPOSITORY / "sdk" / "rust" / "eigenbrains-sdk" / "Cargo.toml"),
            "--example",
            "interop_audit",
            "--",
            str(root),
            str(population),
            str(reference),
            str(Path(PROTOCOL).resolve()),
            str(DISCOLAB_SOURCE),
        ],
        env=environment,
        label="Rust interoperability audit",
    )

    julia_result = _run_json(
        [
            julia,
            f"--project={REPOSITORY / 'sdk' / 'julia'}",
            str(REPOSITORY / "sdk" / "julia" / "examples" / "interop_audit.jl"),
            str(root),
            str(predictions),
            str(reference),
            str(Path(PROTOCOL).resolve()),
        ],
        env=environment,
        label="Julia interoperability audit",
    )

    rust_artifact = _artifact(root, rust["run_id"], "raw", "rust_entropy.json")
    julia_artifact = _artifact(root, julia_result["run_id"], "raw", "julia_statistics.json")
    verifier_report = verify_languages.run(
        root,
        parameters={
            "tolerance": TOLERANCE,
            "python_run_id": python_run,
            "rust_run_id": rust["run_id"],
            "julia_run_id": julia_result["run_id"],
        },
        seed=2026,
        budget=ResourceBudget(max_evaluations=1, max_seconds=30),
        inputs={
            "python_reference": str(reference),
            "rust_entropy": str(rust_artifact),
            "julia_statistics": str(julia_artifact),
        },
    )
    verifier_run = verifier_report["run_id"]

    store = EvidenceStore(root)
    reproduced = store.reproduce(python_run)
    reproduction = store.compare(python_run, reproduced["run_id"])
    identical = bool(reproduction["artifacts"]) and all(
        item["identical"] for item in reproduction["artifacts"].values()
    )
    if not identical:
        raise RuntimeError("Python source artifacts did not reproduce byte-for-byte")
    accepted = store.accept(verifier_run, "Rust and Julia matched the Python references within 1e-12.")
    run_ids = [python_run, rust["run_id"], julia_result["run_id"], verifier_run, reproduced["run_id"]]
    for run_id in run_ids:
        store.validate(run_id)

    bundle_path = root / "bundles" / "interoperability-proof.zip"
    manifest = store.export_bundle(run_ids, bundle_path)
    verified = verify_bundle(bundle_path)
    if verified["content_sha256"] != manifest["content_sha256"]:
        raise RuntimeError("bundle identity changed during verification")

    reference_value = json.loads(reference.read_text(encoding="utf-8"))
    report_path = _artifact(root, verifier_run, "raw", "interop_report.json")
    parity = json.loads(report_path.read_text(encoding="utf-8"))["parity"]
    summary = {
        "passed": True,
        "protocol": "1.0",
        "elapsed_seconds": (datetime.now(UTC) - started).total_seconds(),
        "root": str(root),
        "runs": {
            "python": python_run,
            "rust": rust["run_id"],
            "julia": julia_result["run_id"],
            "verification": verifier_run,
            "reproduction": reproduced["run_id"],
        },
        "reference": {"entropy": reference_value["entropy"], "auroc": reference_value["auroc"]},
        "parity": parity,
        "reproduction_byte_identical": identical,
        "verification_status": accepted["status"],
        "bundle": str(bundle_path.resolve()),
        "bundle_content_sha256": manifest["content_sha256"],
    }
    (root / "interop-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def _print_summary(summary: dict[str, Any]) -> None:
    print("\nEigenBrains SDK interoperability proof")
    print("=" * 42)
    print(f"Python  produced hashed NumPy + JSONL evidence   {summary['runs']['python']}")
    print(f"Rust    audited native entropy                  {summary['runs']['rust']}")
    print(f"Julia   audited AUROC + clustered uncertainty   {summary['runs']['julia']}")
    print(f"Python  verified and accepted combined evidence {summary['runs']['verification']}")
    print("-" * 42)
    print(f"Rust/Python entropy difference : {summary['parity']['entropy_rust_vs_python']:.3e}")
    print(f"Julia/Python AUROC difference  : {summary['parity']['auroc_julia_vs_python']:.3e}")
    print(f"Reproduction byte-identical    : {summary['reproduction_byte_identical']}")
    print(f"Bundle identity                : {summary['bundle_content_sha256']}")
    print(f"Evidence root                  : {summary['root']}")
    print("PASS: three languages, one protocol, one evidence graph, one verified bundle")


def main() -> int:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY / ".interop-demo" / timestamp)
    parser.add_argument("--cargo", default=os.environ.get("CARGO", "cargo"))
    parser.add_argument("--julia", default=os.environ.get("JULIA", "julia"))
    parser.add_argument("--json", action="store_true", help="print the final summary as JSON")
    args = parser.parse_args()
    try:
        summary = execute(args.root.resolve(), cargo=_tool(args.cargo, "Cargo"), julia=_tool(args.julia, "Julia"))
    except (OSError, RuntimeError, ValueError) as error:
        print(f"INTEROPERABILITY DEMO FAILED: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
