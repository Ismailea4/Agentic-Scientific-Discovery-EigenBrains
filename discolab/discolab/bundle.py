"""Content-addressed evidence bundles.

A bundle packages complete runs so another person or machine can check them
without trusting the producer's directory. ``bundle.json`` lists every file with
its SHA-256 and size; the bundle's identity is the SHA-256 of that canonical
file list (``content_sha256``). Verification fails closed: a missing, extra,
or altered file, an unsafe archive member, or a run that does not validate
makes the whole bundle invalid.

This is tamper-*evident*, not signed: someone who can rewrite the files can
also rewrite the manifest. Publish ``content_sha256`` through a separate
channel (a commit, a paper) to pin a bundle.
"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .evidence import (
    EvidenceError,
    ValidationError,
    _canonical_json,
    _read_events,
    _run_dir,
    _sha256_bytes,
    _sha256_file,
    _status,
    _validate_name,
    validate_run,
)

BUNDLE_FORMAT = "eigenbrains.evidence-bundle.v1"
MANIFEST = "bundle.json"
EXPORTABLE = frozenset({"validated", "accepted_as_evidence", "rejected_as_evidence"})
MAX_MEMBERS = 100_000
MAX_UNCOMPRESSED_BYTES = 4 * 1024**3
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def content_address(files: list[dict[str, Any]]) -> str:
    return _sha256_bytes(_canonical_json(sorted(files, key=lambda f: f["path"])).encode("utf-8"))


def export_bundle(root: str | Path, run_ids: Iterable[str], destination: str | Path, *,
                  archive: bool = True) -> dict[str, Any]:
    """Write the given runs to ``destination`` (a deterministic .zip, or a directory
    when ``archive`` is False). Runs must be validated or decided, and valid —
    except rejected runs, which are exported as they are so a rejection can be
    audited. Returns the manifest."""
    ids = sorted(set(run_ids))
    if not ids:
        raise ValueError("a bundle needs at least one run")
    entries: list[tuple[str, Path]] = []
    runs = []
    for run_id in ids:
        run_dir = _run_dir(root, run_id)
        status = _status(_read_events(run_dir))
        if status not in EXPORTABLE:
            raise EvidenceError(f"run {run_id} is {status}; only validated or decided runs can be bundled")
        if status != "rejected_as_evidence":
            validate_run(root, run_id)
        spec = json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
        runs.append({"run_id": run_id, "status": status, "capability": spec["capability"],
                     "spec_sha256": _sha256_file(run_dir / "spec.json")})
        for path in sorted(p for p in run_dir.rglob("*") if p.is_file()):
            if path.is_symlink():
                raise EvidenceError(f"run {run_id} contains a symbolic link: {path.name}")
            entries.append((f"research-runs/{run_id}/{path.relative_to(run_dir).as_posix()}", path))
    files = [{"path": name, "sha256": _sha256_file(path), "bytes": path.stat().st_size} for name, path in entries]
    manifest = {"format": BUNDLE_FORMAT, "runs": runs, "files": files, "content_sha256": content_address(files)}
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f"bundle destination already exists: {destination.name}")
    if archive:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, data in [(MANIFEST, manifest_bytes)] + [(n, p.read_bytes()) for n, p in entries]:
                info = zipfile.ZipInfo(name, date_time=_FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                zf.writestr(info, data)
    else:
        destination.mkdir(parents=True)
        (destination / MANIFEST).write_bytes(manifest_bytes)
        for name, path in entries:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    return manifest


def _safe_member(name: str) -> bool:
    if not name or "\\" in name or name.startswith("/") or ":" in name:
        return False
    parts = PurePosixPath(name).parts
    return all(part not in ("", ".", "..") for part in parts)


def _extract(archive: Path, target: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ValidationError(f"bundle has {len(infos)} members, above the limit of {MAX_MEMBERS}")
        if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
            raise ValidationError("bundle expands beyond the size limit")
        names = [i.filename for i in infos]
        if len(names) != len(set(names)):
            raise ValidationError("bundle contains duplicate members")
        for info in infos:
            mode = (info.external_attr >> 16) & 0o170000
            if info.is_dir() or not _safe_member(info.filename) or mode not in (0, 0o100000):
                raise ValidationError(f"unsafe bundle member {info.filename!r}")
            out = target / info.filename
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, out.open("xb") as dst:
                shutil.copyfileobj(src, dst)


def _verify_tree(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"bundle manifest is missing or unreadable: {type(exc).__name__}") from exc
    if manifest.get("format") != BUNDLE_FORMAT:
        raise ValidationError(f"unsupported bundle format {manifest.get('format')!r}")
    listed = {f["path"]: f for f in manifest.get("files", [])}
    present = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} - {MANIFEST}
    for path in sorted(set(listed) - present):
        errors.append(f"missing file {path}")
    for path in sorted(present - set(listed)):
        errors.append(f"unlisted file {path}")
    for path in sorted(set(listed) & present):
        if not _safe_member(path):
            errors.append(f"unsafe path {path}")
            continue
        actual = root / path
        if actual.stat().st_size != listed[path]["bytes"] or _sha256_file(actual) != listed[path]["sha256"]:
            errors.append(f"file {path} does not match its manifest hash")
    if content_address(list(listed.values())) != manifest.get("content_sha256"):
        errors.append("content_sha256 does not match the file list")
    run_reports = []
    for run in manifest.get("runs", []):
        run_id = run.get("run_id", "")
        try:
            _validate_name(run_id, "run id")
            status = _status(_read_events(root / "research-runs" / run_id))
            if status != run.get("status"):
                errors.append(f"run {run_id} is {status} but the manifest says {run.get('status')}")
            if status == "rejected_as_evidence":
                run_reports.append({"run_id": run_id, "status": status, "valid": None})
            else:
                validate_run(root, run_id)
                run_reports.append({"run_id": run_id, "status": status, "valid": True})
        except Exception as exc:
            errors.append(f"run {run_id}: {exc}")
    listed_runs = {p.split("/")[1] for p in listed if p.startswith("research-runs/") and p.count("/") >= 2}
    if listed_runs != {r.get("run_id") for r in manifest.get("runs", [])}:
        errors.append("the manifest's run list does not match its files")
    if errors:
        raise ValidationError("bundle verification failed: " + "; ".join(errors))
    return {"valid": True, "content_sha256": manifest["content_sha256"], "files": len(listed), "runs": run_reports}


def verify_bundle(path: str | Path) -> dict[str, Any]:
    """Verify a bundle archive or directory. Raises ValidationError on any problem."""
    path = Path(path)
    if path.is_dir():
        return _verify_tree(path)
    if not path.is_file():
        raise FileNotFoundError(f"no bundle at {path.name}")
    if not zipfile.is_zipfile(path):
        raise ValidationError(f"{path.name} is not a zip archive")
    with tempfile.TemporaryDirectory(prefix="eb-bundle-") as tmp:
        try:
            _extract(path, Path(tmp))
        except (zipfile.BadZipFile, zlib.error, OSError, EOFError) as exc:
            raise ValidationError(f"bundle archive is corrupted: {type(exc).__name__}: {exc}") from exc
        report = _verify_tree(Path(tmp))
    report["archive_sha256"] = _sha256_file(path)
    return report


def read_manifest(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if path.is_dir():
        return json.loads((path / MANIFEST).read_text(encoding="utf-8"))
    with zipfile.ZipFile(path) as zf:
        return json.load(io.BytesIO(zf.read(MANIFEST)))
