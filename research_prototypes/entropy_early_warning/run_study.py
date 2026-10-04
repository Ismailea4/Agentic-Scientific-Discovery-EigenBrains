"""Execute the frozen entropy early-warning study without tuning on held-out data.

The default command runs the development stage only.  The confirmatory stage
requires the explicit ``--confirm`` flag and uses exactly the design recorded in
``protocol.yaml``.  Generated evidence is written below the ignored ``output/``
directory; this module never edits the frozen protocol.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

import yaml


STUDY_DIR = Path(__file__).resolve().parent
REPOSITORY = STUDY_DIR.parents[1]
DISCOLAB_SOURCE = REPOSITORY / "discolab"
PROTOCOL_PATH = STUDY_DIR / "protocol.yaml"
FROZEN_PROTOCOL_SHA256 = "ba0e3e0ad771233ba5a7f5575170ed7e1a05a074fd4597c3c98e9d2882f43e2d"
INVOCATION_CWD = Path.cwd()

# Keep the protocol and runner references portable.  The evidence runtime hashes
# both files relative to the current working directory.
os.chdir(STUDY_DIR)
for source in (DISCOLAB_SOURCE, STUDY_DIR):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from discolab import EvidenceStore, ResourceBudget, ValidationError, verify_bundle  # noqa: E402
import ewstudy  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frozen_protocol() -> dict[str, Any]:
    actual = _sha256(PROTOCOL_PATH)
    if actual != FROZEN_PROTOCOL_SHA256:
        raise RuntimeError(
            "frozen protocol hash mismatch; refusing to run evidence "
            f"(expected {FROZEN_PROTOCOL_SHA256}, found {actual})"
        )
    protocol = yaml.safe_load(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if protocol.get("status") != "frozen" or protocol.get("protocol_version") != 1:
        raise RuntimeError("protocol must be frozen at version 1")
    return protocol


def _inclusive_range(raw: list[int]) -> list[int]:
    if len(raw) != 2 or raw[0] > raw[1]:
        raise RuntimeError(f"invalid inclusive seed range: {raw!r}")
    return [int(raw[0]), int(raw[1])]


def _simulation_parameters(protocol: dict[str, Any], partition: str) -> dict[str, Any]:
    design = protocol["design"]
    ga = design["ga"]
    return {
        "protocol_sha256": FROZEN_PROTOCOL_SHA256,
        "status": "exploratory" if partition == "development" else "confirmatory",
        "partition": partition,
        "landscapes": list(design["landscapes"][partition]),
        "seeds": _inclusive_range(design["seeds"][partition]),
        "snapshot_seeds": [700000, 700004] if partition == "development" else [],
        "snapshot_every": 10,
        "data_policies": dict(design["data_policies"]),
        "pop_size": int(ga["pop_size"]),
        "dim": int(ga["dim"]),
        "generations": int(design["generations"]),
    }


def _analysis_parameters(protocol: dict[str, Any], stage: str) -> dict[str, Any]:
    design = protocol["design"]
    return {
        "protocol_sha256": FROZEN_PROTOCOL_SHA256,
        "status": "exploratory" if stage == "development" else "confirmatory",
        "development_landscapes": list(design["landscapes"]["development"]),
        "held_out_landscapes": list(design["landscapes"]["held_out"]),
        "horizon": int(design["label"]["horizon_K"]),
        "n_boot": 2000,
        "sesoi": float(protocol["hypotheses"]["primary"]["sesoi"]),
    }


def _simulation_budget(parameters: dict[str, Any]) -> ResourceBudget:
    seeds = parameters["seeds"][1] - parameters["seeds"][0] + 1
    evaluations = (
        len(parameters["landscapes"])
        * seeds
        * len(parameters["data_policies"])
        * parameters["pop_size"]
        * parameters["generations"]
    )
    return ResourceBudget(max_evaluations=evaluations, max_seconds=900)


def _artifact(store: EvidenceStore, run_id: str, name: str) -> Path:
    snapshot = store.inspect(run_id)
    try:
        descriptor = next(item for item in snapshot["artifacts"] if item["name"] == name)
    except StopIteration as exc:
        raise RuntimeError(f"run {run_id} omitted artifact {name!r}") from exc
    path = store.root / "research-runs" / run_id / descriptor["path"]
    if not path.is_file():
        raise RuntimeError(f"artifact is missing: {path}")
    return path.resolve()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a JSON object in {path}")
    return value


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
        cwd=STUDY_DIR,
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


@contextmanager
def _timed(stages: dict[str, float], label: str) -> Iterator[None]:
    started = time.perf_counter()
    print(f"[{label}] starting", flush=True)
    try:
        yield
    finally:
        stages[label] = time.perf_counter() - started
        print(f"[{label}] {stages[label]:.3f}s", flush=True)


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    prefixes = [str(DISCOLAB_SOURCE), str(STUDY_DIR)]
    if environment.get("PYTHONPATH"):
        prefixes.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(prefixes)
    environment["PYTHON"] = sys.executable
    return environment


def _run_development(root: Path, protocol: dict[str, Any], stages: dict[str, float]) -> dict[str, Any]:
    store = EvidenceStore(root)
    parameters = _simulation_parameters(protocol, "development")
    with _timed(stages, "development_simulation"):
        simulation = ewstudy.simulate_development.run(
            root,
            parameters=parameters,
            seed=2026100401,
            budget=_simulation_budget(parameters),
        )
    simulation_id = simulation["run_id"]
    traces = _artifact(store, simulation_id, "traces")
    with _timed(stages, "development_analysis"):
        analysis = ewstudy.analyze_development.run(
            root,
            parameters=_analysis_parameters(protocol, "development"),
            seed=2026100402,
            budget=ResourceBudget(max_seconds=900),
            inputs={"development_traces": str(traces)},
        )
    result = _read_json(_artifact(store, analysis["run_id"], "result"))
    return {
        "simulation": simulation_id,
        "analysis": analysis["run_id"],
        "exploratory_result": result,
    }


def _corruption_controls(
    store: EvidenceStore,
    bundle_path: Path,
    source_run_id: str,
) -> dict[str, Any]:
    # Bundle control: unpack an exact copy, alter one artifact byte, and require
    # independent verification to fail.
    corrupt_bundle = store.root / "corruption-control-bundle"
    shutil.unpack_archive(str(bundle_path), str(corrupt_bundle), "zip")
    candidates = sorted(corrupt_bundle.glob("research-runs/*/artifacts/raw/*"))
    if not candidates:
        raise RuntimeError("corruption control found no raw bundle artifact")
    target = candidates[0]
    payload = bytearray(target.read_bytes())
    if not payload:
        raise RuntimeError("corruption control selected an empty artifact")
    payload[len(payload) // 2] ^= 0x01
    target.write_bytes(payload)
    bundle_rejected = False
    bundle_error = ""
    try:
        verify_bundle(corrupt_bundle)
    except ValidationError as error:
        bundle_rejected = True
        bundle_error = str(error)
    if not bundle_rejected:
        raise RuntimeError("corrupted bundle was incorrectly accepted")

    # Run control: clone a finished run, alter one artifact, require validation
    # to fail, then record an auditable evidence rejection.
    corrupt_id = f"RUN-CORRUPT-{uuid.uuid4().hex[:8].upper()}"
    source = store.root / "research-runs" / source_run_id
    destination = store.root / "research-runs" / corrupt_id
    shutil.copytree(source, destination)
    artifact = sorted((destination / "artifacts").rglob("*.*"))[0]
    payload = bytearray(artifact.read_bytes())
    payload[0] ^= 0x01
    artifact.write_bytes(payload)
    run_rejected = False
    run_error = ""
    try:
        store.validate(corrupt_id)
    except ValidationError as error:
        run_rejected = True
        run_error = str(error)
    if not run_rejected:
        raise RuntimeError("corrupted run was incorrectly accepted")
    decision = store.reject(
        corrupt_id,
        "Intentional corruption control: one artifact byte was changed and validation failed as required.",
    )
    return {
        "bundle_corruption_detected": bundle_rejected,
        "bundle_error": bundle_error,
        "run_corruption_detected": run_rejected,
        "run_error": run_error,
        "rejected_control_run": corrupt_id,
        "rejected_control_status": decision["status"],
    }


def _run_confirmatory(
    root: Path,
    protocol: dict[str, Any],
    development: dict[str, Any],
    stages: dict[str, float],
    *,
    cargo: str,
    julia: str,
) -> dict[str, Any]:
    store = EvidenceStore(root)
    environment = _environment()
    dev_traces = _artifact(store, development["simulation"], "traces")

    held_parameters = _simulation_parameters(protocol, "held_out")
    with _timed(stages, "held_out_simulation"):
        held = ewstudy.simulate_held_out.run(
            root,
            parameters=held_parameters,
            seed=2026100403,
            budget=_simulation_budget(held_parameters),
        )
    held_id = held["run_id"]
    held_traces = _artifact(store, held_id, "traces")

    with _timed(stages, "confirmatory_analysis"):
        confirmation = ewstudy.analyze_confirmatory.run(
            root,
            parameters=_analysis_parameters(protocol, "confirmatory"),
            seed=2026100404,
            budget=ResourceBudget(max_seconds=1200),
            inputs={
                "development_traces": str(dev_traces),
                "held_out_traces": str(held_traces),
            },
        )
    confirmation_id = confirmation["run_id"]
    result_path = _artifact(store, confirmation_id, "result")
    result = _read_json(result_path)

    snapshots = _artifact(store, development["simulation"], "population_snapshots")
    bounds = _artifact(store, development["simulation"], "snapshot_bounds")
    snapshot_index = _artifact(store, development["simulation"], "snapshot_index")
    benchmark_parameters = {
        "protocol_sha256": FROZEN_PROTOCOL_SHA256,
        "bins": 10,
        "warmup": 3,
        "repeats": 30,
    }
    with _timed(stages, "python_entropy_benchmark"):
        python_benchmark = ewstudy.benchmark_python_entropy.run(
            root,
            parameters=benchmark_parameters,
            seed=2026100405,
            budget=ResourceBudget(max_evaluations=18_000, max_seconds=300),
            inputs={
                "population_snapshots": str(snapshots),
                "snapshot_bounds": str(bounds),
            },
        )

    with _timed(stages, "rust_entropy_audit"):
        rust = _run_json(
            [
                cargo,
                "run",
                "--quiet",
                "--release",
                "--manifest-path",
                str(STUDY_DIR / "rust" / "Cargo.toml"),
                "--",
                "--root",
                str(root),
                "--snapshots",
                str(snapshots),
                "--bounds",
                str(bounds),
                "--bins",
                "10",
                "--warmup",
                "3",
                "--repeats",
                "30",
                "--seed",
                "2026100406",
                "--protocol",
                "protocol.yaml",
                "--python-path",
                str(DISCOLAB_SOURCE),
            ],
            env=environment,
            label="Rust entropy audit",
        )
    rust_id = rust["run_id"]

    predictions = _artifact(store, confirmation_id, "predictions")
    with _timed(stages, "julia_statistics_audit"):
        julia_result = _run_json(
            [
                julia,
                f"--project={REPOSITORY / 'sdk' / 'julia'}",
                str(STUDY_DIR / "julia" / "analysis.jl"),
                str(root),
                str(predictions),
                "protocol.yaml",
                "2026100407",
            ],
            env=environment,
            label="Julia statistics audit",
        )
    julia_id = julia_result["run_id"]

    with _timed(stages, "cross_language_check"):
        parity = ewstudy.cross_language_check.run(
            root,
            parameters={"protocol_sha256": FROZEN_PROTOCOL_SHA256, "tolerance": 1e-12},
            seed=2026100408,
            budget=ResourceBudget(max_seconds=300),
            inputs={
                "snapshot_index": str(snapshot_index),
                "rust_entropy": str(_artifact(store, rust_id, "rust_entropy")),
                "confirmatory_result": str(result_path),
                "julia_auroc": str(_artifact(store, julia_id, "julia_auroc")),
            },
        )
    parity_id = parity["run_id"]
    parity_report = _read_json(_artifact(store, parity_id, "parity_report"))
    if not parity_report.get("passed"):
        raise RuntimeError(f"cross-language parity failed: {parity_report}")

    with _timed(stages, "confirmatory_reproduction"):
        reproduced = store.reproduce(confirmation_id)
    if not reproduced.get("identical_artifacts"):
        raise RuntimeError("confirmatory analysis did not reproduce byte-for-byte")
    reproduced_id = reproduced["run_id"]

    run_ids = [
        development["simulation"],
        development["analysis"],
        held_id,
        confirmation_id,
        python_benchmark["run_id"],
        rust_id,
        julia_id,
        parity_id,
        reproduced_id,
    ]
    for run_id in run_ids:
        store.validate(run_id)

    # The registered scientific verdict is not altered by the engineering
    # checks.  Acceptance means only that the result is valid evidence under the
    # frozen protocol, regardless of whether EW1 is supported.
    acceptance = store.accept(
        confirmation_id,
        "Frozen confirmatory analysis passed leakage, parity, reproduction, and integrity checks.",
    )

    bundle_path = root / "bundles" / "entropy-early-warning-v1.zip"
    with _timed(stages, "bundle_and_corruption_checks"):
        manifest = store.export_bundle(run_ids, bundle_path)
        verified = verify_bundle(bundle_path)
        if verified["content_sha256"] != manifest["content_sha256"]:
            raise RuntimeError("bundle identity changed during verification")
        corruption = _corruption_controls(store, bundle_path, reproduced_id)

    python_timing = _read_json(_artifact(store, python_benchmark["run_id"], "python_timing"))
    rust_timing = _read_json(_artifact(store, rust_id, "rust_timing"))
    speed_ratio = python_timing["median"] / rust_timing["median"] if rust_timing["median"] else None
    return {
        "runs": {
            "held_out_simulation": held_id,
            "confirmatory_analysis": confirmation_id,
            "python_benchmark": python_benchmark["run_id"],
            "rust_audit": rust_id,
            "julia_audit": julia_id,
            "parity": parity_id,
            "reproduction": reproduced_id,
        },
        "registered_result": result,
        "acceptance_status": acceptance["status"],
        "parity": parity_report,
        "reproduction_byte_identical": True,
        "timing": {
            "python_entropy_batch_median_seconds": python_timing["median"],
            "rust_entropy_batch_median_seconds": rust_timing["median"],
            "python_over_rust_ratio": speed_ratio,
            "benchmark_scope": "600 snapshots, in-memory computation only",
        },
        "bundle": {
            "path": str(bundle_path),
            "content_sha256": manifest["content_sha256"],
            "verified": True,
        },
        "corruption_controls": corruption,
    }


def execute(root: Path, *, confirm: bool, cargo: str, julia: str) -> dict[str, Any]:
    if root.exists() and any(root.iterdir()):
        raise RuntimeError(f"refusing to mix a new study with existing files: {root}")
    root.mkdir(parents=True, exist_ok=True)
    protocol = _frozen_protocol()
    started = datetime.now(UTC)
    stages: dict[str, float] = {}
    development = _run_development(root, protocol, stages)
    summary: dict[str, Any] = {
        "study_id": protocol["study_id"],
        "protocol_sha256": FROZEN_PROTOCOL_SHA256,
        "started_at": started.isoformat(),
        "mode": "confirmatory" if confirm else "development-only",
        "root": str(root),
        "development": development,
        "stages_seconds": stages,
    }
    if confirm:
        summary["confirmation"] = _run_confirmatory(
            root,
            protocol,
            development,
            stages,
            cargo=_tool(cargo, "Cargo"),
            julia=_tool(julia, "Julia"),
        )
    summary["finished_at"] = datetime.now(UTC).isoformat()
    summary["elapsed_seconds"] = (datetime.now(UTC) - started).total_seconds()
    summary["stages_seconds"] = stages
    (root / "study-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def _print_summary(summary: dict[str, Any]) -> None:
    print("\nEntropy early-warning study")
    print("=" * 42)
    print(f"Protocol SHA-256 : {summary['protocol_sha256']}")
    print(f"Mode             : {summary['mode']}")
    exploratory = summary["development"]["exploratory_result"]["contrasts"]["EW1"]
    print(
        "Development EW1  : "
        f"delta AUROC {exploratory['estimate']:+.4f} "
        f"[{exploratory['low']:+.4f}, {exploratory['high']:+.4f}] (exploratory only)"
    )
    if "confirmation" in summary:
        confirmation = summary["confirmation"]
        result = confirmation["registered_result"]
        primary = result["contrasts"]["EW1"]
        print(
            "Held-out EW1     : "
            f"delta AUROC {primary['estimate']:+.4f} "
            f"[{primary['low']:+.4f}, {primary['high']:+.4f}]"
        )
        print(f"Registered verdict: {result['decision']}")
        print(f"Evidence status    : {confirmation['acceptance_status']}")
        print(f"Language parity    : {confirmation['parity']['passed']}")
        print(f"Byte reproduction  : {confirmation['reproduction_byte_identical']}")
        print(f"Bundle identity    : {confirmation['bundle']['content_sha256']}")
    print(f"Elapsed seconds    : {summary['elapsed_seconds']:.3f}")
    print(f"Evidence root      : {summary['root']}")


def main() -> int:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=STUDY_DIR / "output" / timestamp)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="spend the sealed held-out landscapes exactly once after development validation",
    )
    parser.add_argument("--cargo", default=os.environ.get("CARGO", "cargo"))
    parser.add_argument("--julia", default=os.environ.get("JULIA", "julia"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = args.root if args.root.is_absolute() else INVOCATION_CWD / args.root
    try:
        summary = execute(
            root.resolve(),
            confirm=args.confirm,
            cargo=args.cargo,
            julia=args.julia,
        )
    except (OSError, RuntimeError, ValueError, ValidationError) as error:
        print(f"STUDY FAILED CLOSED: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
