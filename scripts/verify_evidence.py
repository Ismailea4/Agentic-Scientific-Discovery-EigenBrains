"""Verify published evidence claims and perform a deterministic SDK reproduction.

This command is offline. It does not inspect environment variables or contact a
model provider. It intentionally derives headline values from machine-readable
artifacts instead of trusting prose reports.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
DISCOLAB = REPOSITORY / "discolab"
if str(DISCOLAB) not in sys.path:
    sys.path.insert(0, str(DISCOLAB))

from discolab import EvidenceStore, ValidationError, verify_bundle  # noqa: E402
from scripts.reproducibility_fixture import execute  # noqa: E402


class VerificationFailure(RuntimeError):
    """A published invariant did not match its evidence artifact."""


def _load(path: Path) -> dict:
    if not path.is_file():
        raise VerificationFailure(f"missing evidence artifact: {path.relative_to(REPOSITORY)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationFailure(message)


def _close(actual: float, expected: float, *, tolerance: float = 1e-12) -> None:
    if not math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance):
        raise VerificationFailure(f"expected {expected!r}, observed {actual!r}")


def verify_model_routing(root: Path) -> dict:
    path = root / "benchmark" / "artifacts" / "baseline_v0" / "baseline_v0_summary.json"
    summary = _load(path)
    rows = {row["architecture_id"]: row for row in summary["offline_replay"]["architecture_results"]}
    _require({"S1", "S2", "S3"}.issubset(rows), "baseline summary is missing S1, S2, or S3")

    first, always, selective = rows["S1"], rows["S2"], rows["S3"]
    _close(first["expected_quality"], 0.75)
    _close(always["expected_quality"], 0.75)
    _close(selective["expected_quality"], 0.75)
    cost_saving = 1.0 - selective["cost"] / always["cost"]
    latency_saving = 1.0 - selective["latency"] / always["latency"]
    _require(round(cost_saving, 3) == 0.160, f"published cost saving changed: {cost_saving:.6f}")
    _require(round(latency_saving, 3) == 0.352, f"published latency saving changed: {latency_saving:.6f}")

    confirmation = {
        row["architecture_id"]: row
        for row in summary["provider_backed_confirmation"]
    }
    _require("S3_PROVIDER_BACKED" in confirmation, "provider-backed S3 confirmation is missing")
    s3 = confirmation["S3_PROVIDER_BACKED"]
    _require(s3["rescues"] == 0 and s3["damage"] == 0, "S3 confirmation economics changed")
    return {
        "evidence": "REPLAY plus PROVIDER_BACKED confirmation",
        "held_out_cases": 12,
        "observed_quality": selective["expected_quality"],
        "cost_saving_fraction": cost_saving,
        "latency_saving_fraction": latency_saving,
        "provider_backed_rescues": s3["rescues"],
        "provider_backed_damages": s3["damage"],
    }


def verify_acceleration(root: Path, summary_path: Path | None = None) -> dict:
    recorded_path = root / "discolab" / "results" / "escalation" / "summary.json"
    recorded = _load(recorded_path)
    summary = recorded if summary_path is None else _load(summary_path)

    ratios = summary["acceleration"]["per_replicate"]
    _require(len(ratios) == 5 and len(summary["replicates"]) == 5, "acceleration study must have five replicates")
    _require(all(value > 1 for value in ratios), "every acceleration replicate must save compute")
    _close(summary["acceleration"]["mean_ratio"], sum(ratios) / len(ratios))
    _close(summary["acceleration"]["mean_cost_saving"], 1 - 1 / summary["acceleration"]["mean_ratio"])

    full_agreement = sum(summary["agreement"]["always_large"])
    selective_agreement = sum(summary["agreement"]["escalate"])
    _require(full_agreement == 29, f"full-size agreement changed: {full_agreement}/35")
    _require(selective_agreement == 28, f"selective agreement changed: {selective_agreement}/35")
    _require(summary["economics"]["rescues"] == 5, "selective-escalation rescue count changed")
    _require(summary["economics"]["damages"] == 0, "selective-escalation damage count changed")
    _require(summary["economics"]["hypothesis_replicates"] == 35, "unexpected acceleration denominator")

    if summary_path is not None:
        _require(summary["protocol"] == recorded["protocol"], "reproduction used a different frozen protocol")
        _require(summary["agreement"] == recorded["agreement"], "reproduced agreement differs from recorded evidence")
        _require(summary["economics"] == recorded["economics"], "reproduced rescue/damage economics differ")
        for actual, expected in zip(ratios, recorded["acceleration"]["per_replicate"], strict=True):
            _close(actual, expected)

    ci = summary["acceleration"]["ci95"]
    return {
        "evidence": "BENCHMARK development-stage experiment",
        "replicates": len(ratios),
        "hypothesis_replicates": summary["economics"]["hypothesis_replicates"],
        "compute_ratio": summary["acceleration"]["mean_ratio"],
        "compute_ratio_ci95": [ci["low"], ci["high"]],
        "compute_saving_fraction": summary["acceleration"]["mean_cost_saving"],
        "agreement_selective": selective_agreement,
        "agreement_full_size": full_agreement,
        "rescues": summary["economics"]["rescues"],
        "damages": summary["economics"]["damages"],
    }


def reproduce_sdk(root: Path) -> dict:
    study = root / "sdk-reproduction"
    original = execute(study)
    store = EvidenceStore(study)
    original_id = original["run_id"]
    store.validate(original_id)
    reproduced = store.reproduce(original_id)
    reproduced_id = reproduced["run_id"]
    store.validate(reproduced_id)
    comparison = store.compare(original_id, reproduced_id)
    artifacts = comparison["artifacts"]
    _require(
        artifacts and all(row["identical"] for row in artifacts.values()),
        "SDK artifacts did not reproduce byte-for-byte",
    )

    bundle = root / "verification-evidence.zip"
    manifest = store.export_bundle([original_id, reproduced_id], bundle)
    verified = verify_bundle(bundle)
    _require(verified["content_sha256"] == manifest["content_sha256"], "bundle identity changed during verification")

    corrupted = root / "verification-evidence-corrupted.zip"
    shutil.copy2(bundle, corrupted)
    data = bytearray(corrupted.read_bytes())
    data[len(data) // 2] ^= 1
    corrupted.write_bytes(data)
    corruption_rejected = False
    try:
        verify_bundle(corrupted)
    except (ValidationError, zipfile.BadZipFile, OSError):
        corruption_rejected = True
    _require(corruption_rejected, "corrupted evidence bundle was not rejected")

    return {
        "original_run": original_id,
        "reproduced_run": reproduced_id,
        "byte_identical_artifacts": len(artifacts),
        "bundle_content_sha256": manifest["content_sha256"],
        "corruption_negative_control": "rejected",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=REPOSITORY)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--acceleration-summary", type=Path)
    parser.add_argument("--claims-only", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()

    temporary = None
    try:
        if args.work is None:
            temporary = tempfile.TemporaryDirectory(prefix="eigenbrains-verify-")
            work = Path(temporary.name)
        else:
            work = args.work.resolve()
            work.mkdir(parents=True, exist_ok=False)

        report = {
            "ok": True,
            "model_routing": verify_model_routing(root),
            "research_acceleration": verify_acceleration(root, args.acceleration_summary),
        }
        if not args.claims_only:
            report["sdk_reproduction"] = reproduce_sdk(work)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (KeyError, TypeError, ValueError, ValidationError, VerificationFailure) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
