"""Research-grade evidence SDK primitives.

This module is deliberately separate from the domain-specific discovery lab.
It gives arbitrary computational experiments a small, validated boundary for
reproducibility, semantic artifacts, resource accounting, and evidence state.
The existing lab remains the authoritative engine for its own experiments.

Lifecycle (one append-only, hash-chained ``events.jsonl`` per run)::

    running --(checkpoint_written)*--> running --> failed
       |  ^                                          (terminal)
       |  +-- run_resumed (from the last checkpoint)
       v
    raw_complete --> validated --> accepted_as_evidence   (terminal)
         |               |
         +---------------+-------> rejected_as_evidence   (terminal)
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import inspect
import json
import os
import platform
import re
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping

import numpy as np

Stage = Literal["raw", "derived", "analysis"]
ArtifactKind = Literal["table", "array", "json"]
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")

CHECKPOINT_FORMAT = "eigenbrains.checkpoint.v1"
GENESIS_SHA256 = "0" * 64

# Event type -> status it moves the run into.
LIFECYCLE = {
    "run_started": "running",
    "run_resumed": "running",
    "run_failed": "failed",
    "run_finalized": "raw_complete",
    "run_validated": "validated",
    "run_accepted": "accepted_as_evidence",
    "run_rejected": "rejected_as_evidence",
}
STATUSES = ("running", "failed", "raw_complete", "validated", "accepted_as_evidence", "rejected_as_evidence")
TERMINAL_STATUSES = frozenset({"failed", "accepted_as_evidence", "rejected_as_evidence"})
# Which events may follow a run in a given status. Evidence (artifacts, metrics,
# checkpoints) can only be written while the run is open.
_ALLOWED_AFTER = {
    None: {"run_started"},
    "running": {"run_resumed", "run_failed", "run_finalized", "artifact_emitted", "metric_recorded",
                "checkpoint_written"},
    "raw_complete": {"run_validated", "run_rejected"},
    "validated": {"run_accepted", "run_rejected"},
}


class EvidenceError(RuntimeError):
    """Base class for evidence-layer failures (including refused lifecycle transitions)."""


class ValidationError(EvidenceError):
    """Raised when evidence violates its declared scientific contract or fails an integrity check."""


class BudgetExceeded(EvidenceError):
    """Raised when a cooperative evaluation or wall-time budget is exhausted."""


@dataclass(frozen=True)
class ResourceBudget:
    max_evaluations: int | None = None
    max_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.max_evaluations is not None and self.max_evaluations <= 0:
            raise ValueError("max_evaluations must be positive")
        if self.max_seconds is not None and self.max_seconds <= 0:
            raise ValueError("max_seconds must be positive")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "ResourceBudget":
        return cls(**dict(value or {}))


@dataclass(frozen=True)
class FieldSchema:
    name: str
    dtype: Literal["number", "integer", "string", "boolean"]
    unit: str | None = None
    role: str | None = None
    nullable: bool = False
    minimum: float | None = None
    maximum: float | None = None
    censoring: Literal["right", "left", "interval"] | None = None

    def __post_init__(self) -> None:
        _validate_name(self.name, "field")
        if self.dtype not in {"number", "integer", "string", "boolean"}:
            raise ValueError(f"field {self.name}: unknown dtype {self.dtype!r}")
        if self.dtype not in {"number", "integer"} and (
            self.minimum is not None or self.maximum is not None or self.censoring is not None
        ):
            raise ValueError(f"field {self.name}: ranges and censoring require a numeric dtype")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError(f"field {self.name}: minimum exceeds maximum")
        if self.censoring not in {None, "right", "left", "interval"}:
            raise ValueError(f"field {self.name}: unknown censoring {self.censoring!r}")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FieldSchema":
        return cls(**dict(value))


@dataclass(frozen=True)
class ArtifactSchema:
    name: str
    version: int
    kind: ArtifactKind
    fields: tuple[FieldSchema, ...] = ()
    dtype: str | None = None
    ndim: int | None = None
    unit: str | None = None
    role: str | None = None
    allow_extra_fields: bool = False

    def __post_init__(self) -> None:
        _validate_name(self.name, "schema")
        if self.version <= 0:
            raise ValueError("schema version must be positive")
        if self.kind not in {"table", "array", "json"}:
            raise ValueError(f"schema {self.name}: unknown kind {self.kind!r}")
        if self.kind == "table" and not self.fields:
            raise ValueError("table schemas require at least one field")
        if self.kind == "array" and not self.dtype:
            raise ValueError("array schemas require dtype")
        if self.ndim is not None and self.ndim < 0:
            raise ValueError("ndim cannot be negative")
        names = [item.name for item in self.fields]
        if len(names) != len(set(names)):
            raise ValueError(f"schema {self.name}: field names must be unique")

    @property
    def id(self) -> str:
        return f"{self.name}.v{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "id": self.id}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ArtifactSchema":
        data = dict(value)
        data.pop("id", None)
        data["fields"] = tuple(FieldSchema.from_dict(item) for item in data.get("fields", ()))
        return cls(**data)


@dataclass(frozen=True)
class MetricSpec:
    name: str
    unit: str
    role: Literal["primary", "secondary", "diagnostic"] = "secondary"
    minimum: float | None = None
    maximum: float | None = None
    censoring: Literal["right", "left", "interval"] | None = None

    def __post_init__(self) -> None:
        _validate_name(self.name, "metric")
        if not self.unit:
            raise ValueError(f"metric {self.name} requires a unit")
        if self.role not in {"primary", "secondary", "diagnostic"}:
            raise ValueError(f"metric {self.name}: unknown role {self.role!r}")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError(f"metric {self.name}: minimum exceeds maximum")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MetricSpec":
        return cls(**dict(value))


@dataclass(frozen=True)
class ExperimentSpecV2:
    capability: str
    hypothesis: str
    protocol: str
    parameters: Mapping[str, Any]
    seed: int
    outputs: tuple[ArtifactSchema, ...]
    primary_metric: MetricSpec
    budget: ResourceBudget = field(default_factory=ResourceBudget)
    runner: str | None = None
    inputs: Mapping[str, str] = field(default_factory=dict)
    reproduction_of: str | None = None

    def __post_init__(self) -> None:
        _validate_name(self.capability, "capability")
        if not self.hypothesis.strip():
            raise ValueError("hypothesis cannot be empty")
        if not self.protocol.strip():
            raise ValueError("protocol cannot be empty")
        if isinstance(self.seed, bool) or not isinstance(self.seed, (int, np.integer)) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if not self.outputs:
            raise ValueError("at least one output schema is required")
        ids = [schema.id for schema in self.outputs]
        if len(ids) != len(set(ids)):
            raise ValueError("output schema ids must be unique")
        for name in self.inputs:
            _validate_name(name, "input")
        # Absolute input paths inside the working directory are stored relative to it,
        # so specs (and the bundles that seal them) never publish local machine paths.
        object.__setattr__(self, "inputs", {k: _portable_input(v) for k, v in dict(self.inputs).items()})
        _canonical_json(dict(self.parameters))

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_version": 2,
            "capability": self.capability,
            "hypothesis": self.hypothesis,
            "protocol": self.protocol,
            "parameters": dict(self.parameters),
            "seed": int(self.seed),
            "outputs": [item.to_dict() for item in self.outputs],
            "primary_metric": asdict(self.primary_metric),
            "budget": asdict(self.budget),
            "runner": self.runner,
            "inputs": dict(self.inputs),
            "reproduction_of": self.reproduction_of,
        }

    @property
    def sha256(self) -> str:
        """Content hash of the canonical spec (identical to the hash of its spec.json)."""
        return _sha256_bytes((_canonical_json(self.to_dict()) + "\n").encode("utf-8"))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ExperimentSpecV2":
        data = dict(value)
        version = data.pop("spec_version", 2)
        if version != 2:
            raise ValueError(f"ExperimentSpecV2 requires spec_version 2, received {version!r}")
        data["outputs"] = tuple(ArtifactSchema.from_dict(item) for item in data["outputs"])
        data["primary_metric"] = MetricSpec.from_dict(data["primary_metric"])
        data["budget"] = ResourceBudget.from_dict(data.get("budget"))
        data["inputs"] = dict(data.get("inputs") or {})
        return cls(**data)


def _validate_name(value: str, kind: str) -> None:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ValueError(f"invalid {kind} name {value!r}")


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"value is not canonical JSON: {exc}") from exc


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _utc_iso(time_unix_ns: int) -> str:
    """ISO-8601 UTC, truncated (never rounded up) to microseconds, so a listed time
    used as an inclusive lower bound still selects the run it came from."""
    seconds, nanos = divmod(int(time_unix_ns), 1_000_000_000)
    stamp = datetime.fromtimestamp(seconds, tz=timezone.utc).replace(microsecond=nanos // 1000)
    return stamp.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _to_unix_ns(value: Any) -> int:
    """Accept unix nanoseconds, a datetime, or an ISO-8601 string (naive means UTC)."""
    if isinstance(value, bool):
        raise ValueError("time filters must be ISO-8601 strings, datetimes, or unix nanoseconds")
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return (value - _EPOCH) // timedelta(microseconds=1) * 1000
    raise ValueError(f"unsupported time value {value!r}")


def _portable_input(value: str | Path) -> str:
    """An input path as it should be recorded in a spec: relative to the working
    directory when it lies inside it; otherwise unchanged, because the file must
    still be locatable to re-hash it on reproduce and resume."""
    path = Path(value)
    if not path.is_absolute():
        return str(value)
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except (ValueError, OSError):
        return str(value)


def _portable_path(value: str | Path) -> str:
    """A path that is safe to publish: relative to the working directory when it is
    inside it, otherwise only the file name (absolute local paths leak machine
    layout and user names, and do not help a reader on another machine)."""
    try:
        resolved = Path(value).resolve()
    except (OSError, ValueError):
        return Path(str(value)).name
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return f"<external>/{resolved.name}"


# --------------------------------------------------------------------------- events

def _event_lines(run_dir: Path) -> list[str]:
    path = run_dir / "events.jsonl"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [line.rstrip("\n") for line in handle if line.strip()]


def _read_events(run_dir: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in _event_lines(run_dir)]


def _append_event(run_dir: Path, event_type: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    lines = _event_lines(run_dir)
    event = {
        "seq": len(lines) + 1,
        "time_unix_ns": time.time_ns(),
        "type": event_type,
        "payload": dict(payload or {}),
        "prev_sha256": _sha256_bytes(lines[-1].encode("utf-8")) if lines else GENESIS_SHA256,
    }
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(_canonical_json(event) + "\n")
    return event


def _chain_errors(lines: list[str]) -> list[str]:
    """Each event names the SHA-256 of the line before it, so editing, removing, or
    reordering an earlier event is detectable (tamper-evident, not signed)."""
    errors = []
    previous = GENESIS_SHA256
    for index, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return [f"event {index} is not valid JSON"]
        if event.get("seq") != index:
            errors.append(f"event {index} has sequence number {event.get('seq')!r}")
        if "prev_sha256" not in event:
            errors.append(f"event {index} is not hash-chained")
        elif event["prev_sha256"] != previous:
            errors.append(f"event chain broken at event {index}")
        previous = _sha256_bytes(line.encode("utf-8"))
    return errors


def _lifecycle_errors(events: list[dict[str, Any]]) -> list[str]:
    status: str | None = None
    for event in events:
        kind = event.get("type")
        allowed = _ALLOWED_AFTER.get(status, set())
        if kind not in allowed:
            return [f"event {event.get('seq')} ({kind}) is not allowed after status {status or 'none'}"]
        status = LIFECYCLE.get(kind, status)
    return []


def _status(events: list[dict[str, Any]]) -> str:
    status = "unknown"
    for event in events:
        status = LIFECYCLE.get(event["type"], status)
    return status


# --------------------------------------------------------------------------- provenance

def _git_provenance(cwd: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip())
        return {"commit": commit, "dirty": dirty, "error": None}
    except Exception as exc:
        return {"commit": None, "dirty": None, "error": type(exc).__name__}


def _dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            versions[name] = distribution.version
    return dict(sorted(versions.items(), key=lambda item: item[0].lower()))


def _redact_command(arguments: Iterable[str]) -> list[str]:
    result: list[str] = []
    redact_next = False
    sensitive = re.compile(r"key|token|secret|password|credential", re.IGNORECASE)
    for raw in arguments:
        argument = str(raw)
        if redact_next:
            result.append("<redacted>")
            redact_next = False
        elif argument.startswith("-") and "=" in argument and sensitive.search(argument.split("=", 1)[0]):
            result.append(argument.split("=", 1)[0] + "=<redacted>")
        else:
            result.append(_portable_path(argument) if Path(argument).is_absolute() else argument)
            redact_next = argument.startswith("-") and bool(sensitive.search(argument))
    return result


def _input_hashes(inputs: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    result = {}
    for name, raw_path in sorted(inputs.items()):
        _validate_name(name, "input")
        path = Path(raw_path)
        if not path.is_file():
            raise FileNotFoundError(f"input {name!r} does not exist: {raw_path}")
        result[name] = {"path": _portable_path(path), "sha256": _sha256_file(path), "bytes": path.stat().st_size}
    return result


def _runner_source(reference: str | None) -> str | None:
    """Source file of an importable ``module:qualname`` runner (imports the module)."""
    if not reference:
        return None
    try:
        module_name, _, qualname = reference.partition(":")
        obj: Any = importlib.import_module(module_name)
        for part in qualname.split("."):
            obj = getattr(obj, part)
        return inspect.getsourcefile(getattr(obj, "function", obj))
    except Exception:
        return None


def _provenance(spec: ExperimentSpecV2) -> dict[str, Any]:
    protocol_path = Path(spec.protocol)
    runner_file = _runner_source(spec.runner)
    return {
        "path_policy": "paths are relative to the working directory; paths outside it keep only their file name",
        "git": _git_provenance(Path.cwd()),
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": _portable_path(sys.executable),
            "virtualenv": sys.prefix != sys.base_prefix,
            "command": _redact_command(sys.argv),
        },
        "system": {
            "os": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "gpu": {"captured": False, "reason": "no GPU detector configured"},
        },
        "dependencies": _dependency_versions(),
        "protocol": {
            "reference": spec.protocol,
            "sha256": _sha256_file(protocol_path) if protocol_path.is_file() else None,
        },
        "runner": {
            "reference": spec.runner,
            "path": _portable_path(runner_file) if runner_file else None,
            "sha256": _sha256_file(Path(runner_file)) if runner_file and Path(runner_file).is_file() else None,
        },
        "inputs": _input_hashes(spec.inputs),
    }


def _compatibility_errors(spec: Mapping[str, Any], provenance: Mapping[str, Any]) -> list[str]:
    """Has anything the run depends on changed since it started? (inputs, protocol, runner)"""
    errors = []
    try:
        current = _input_hashes(spec.get("inputs", {}))
    except FileNotFoundError as exc:
        return [str(exc)]
    recorded = provenance.get("inputs", {})
    if {k: v["sha256"] for k, v in current.items()} != {k: v.get("sha256") for k, v in recorded.items()}:
        errors.append("an input changed since the run started")
    protocol = provenance.get("protocol", {})
    if protocol.get("sha256"):
        path = Path(protocol.get("reference", ""))
        if not path.is_file() or _sha256_file(path) != protocol["sha256"]:
            errors.append("the protocol file changed since the run started")
    runner = provenance.get("runner", {})
    if runner.get("sha256"):
        source = _runner_source(runner.get("reference"))
        if not source or _sha256_file(Path(source)) != runner["sha256"]:
            errors.append("the experiment runner changed since the run started")
    return errors


# --------------------------------------------------------------------------- validation

def _validate_scalar(value: Any, schema: FieldSchema | MetricSpec, label: str) -> None:
    if isinstance(schema, FieldSchema):
        if value is None and schema.nullable:
            return
        if value is None:
            raise ValidationError(f"{label} cannot be null")
        expected = schema.dtype
        valid = {
            "number": isinstance(value, (int, float, np.number)) and not isinstance(value, (bool, np.bool_)),
            "integer": isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)),
            "string": isinstance(value, str),
            "boolean": isinstance(value, (bool, np.bool_)),
        }[expected]
        if not valid:
            raise ValidationError(f"{label} must be {expected}")
        if expected in {"string", "boolean"}:
            return
    elif not isinstance(value, (int, float, np.number)) or isinstance(value, (bool, np.bool_)):
        raise ValidationError(f"{label} must be numeric")
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        raise ValidationError(f"{label} must be finite")
    if schema.minimum is not None and value < schema.minimum:
        raise ValidationError(f"{label} is below minimum {schema.minimum}")
    if schema.maximum is not None and value > schema.maximum:
        raise ValidationError(f"{label} is above maximum {schema.maximum}")


def _validate_table(rows: list[dict[str, Any]], schema: ArtifactSchema) -> None:
    if schema.kind != "table":
        raise ValidationError(f"schema {schema.id} is not a table schema")
    declared = {item.name: item for item in schema.fields}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValidationError(f"row {index} must be an object")
        missing = [name for name, item in declared.items() if name not in row and not item.nullable]
        if missing:
            raise ValidationError(f"row {index} is missing fields {missing}")
        extra = sorted(set(row) - set(declared))
        if extra and not schema.allow_extra_fields:
            raise ValidationError(f"row {index} has undeclared fields {extra}")
        for name, field_schema in declared.items():
            if name in row:
                _validate_scalar(row[name], field_schema, f"row {index}.{name}")


def _artifact_errors(run_dir: Path, artifact: Mapping[str, Any]) -> list[str]:
    path = (run_dir / artifact["path"]).resolve()
    if not path.is_relative_to(run_dir.resolve()):
        return [f"artifact {artifact['name']} escapes its run directory"]
    if not path.is_file():
        return [f"artifact {artifact['name']} is missing"]
    if _sha256_file(path) != artifact["sha256"]:
        return [f"artifact {artifact['name']} hash mismatch"]
    schema = ArtifactSchema.from_dict(artifact["schema"])
    try:
        if schema.kind == "table":
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
            _validate_table(rows, schema)
        elif schema.kind == "array":
            array = np.load(path, allow_pickle=False)
            if schema.dtype and array.dtype != np.dtype(schema.dtype):
                raise ValidationError(f"dtype {array.dtype} != {schema.dtype}")
            if schema.ndim is not None and array.ndim != schema.ndim:
                raise ValidationError(f"ndim {array.ndim} != {schema.ndim}")
        else:
            json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"artifact {artifact['name']} schema failure: {exc}"]
    return []


def _integrity_errors(run_dir: Path, lines: list[str], events: list[dict[str, Any]]) -> list[str]:
    """Checks that do not depend on the run being finished: event chain, lifecycle order,
    run metadata hashes, emitted artifacts, and checkpoints."""
    errors = _chain_errors(lines) + _lifecycle_errors(events)
    started = events[0]["payload"] if events and events[0].get("type") == "run_started" else {}
    for name, key in (("spec.json", "spec_sha256"), ("provenance.json", "provenance_sha256")):
        if key in started:
            path = run_dir / name
            if not path.is_file() or _sha256_file(path) != started[key]:
                errors.append(f"{name} does not match the hash recorded when the run started")
    for event in events:
        if event["type"] == "artifact_emitted":
            errors.extend(_artifact_errors(run_dir, event["payload"]))
        elif event["type"] == "checkpoint_written":
            path = (run_dir / event["payload"]["path"]).resolve()
            if not path.is_relative_to(run_dir.resolve()) or not path.is_file():
                errors.append(f"checkpoint {event['payload']['sequence']} is missing")
            elif _sha256_file(path) != event["payload"]["sha256"]:
                errors.append(f"checkpoint {event['payload']['sequence']} hash mismatch")
    return errors


# --------------------------------------------------------------------------- run context

class ArtifactEmitter:
    def __init__(self, context: "RunContext"):
        self._context = context

    def table(
        self,
        name: str,
        rows: Iterable[Mapping[str, Any]],
        *,
        schema: str | ArtifactSchema,
        stage: Stage = "raw",
        parents: Iterable[str] = (),
    ) -> dict[str, Any]:
        materialized = [dict(row) for row in rows]
        resolved = self._context._resolve_schema(schema, "table")
        _validate_table(materialized, resolved)
        payload = "".join(_canonical_json(row) + "\n" for row in materialized).encode("utf-8")
        return self._context._emit(name, payload, ".jsonl", resolved, stage, parents, len(materialized))

    def array(
        self,
        name: str,
        values: Any,
        *,
        schema: str | ArtifactSchema,
        stage: Stage = "raw",
        parents: Iterable[str] = (),
    ) -> dict[str, Any]:
        import io

        resolved = self._context._resolve_schema(schema, "array")
        array = np.asarray(values)
        if resolved.dtype and np.dtype(resolved.dtype) != array.dtype:
            raise ValidationError(f"array {name} has dtype {array.dtype}, expected {resolved.dtype}")
        if resolved.ndim is not None and array.ndim != resolved.ndim:
            raise ValidationError(f"array {name} has ndim {array.ndim}, expected {resolved.ndim}")
        if np.issubdtype(array.dtype, np.number) and not np.isfinite(array).all():
            raise ValidationError(f"array {name} contains non-finite values")
        buffer = io.BytesIO()
        np.save(buffer, np.ascontiguousarray(array), allow_pickle=False)
        descriptor = self._context._emit(name, buffer.getvalue(), ".npy", resolved, stage, parents, int(array.size))
        descriptor["shape"] = list(array.shape)
        descriptor["dtype"] = str(array.dtype)
        return descriptor

    def json(
        self,
        name: str,
        value: Any,
        *,
        schema: str | ArtifactSchema,
        stage: Stage = "raw",
        parents: Iterable[str] = (),
    ) -> dict[str, Any]:
        resolved = self._context._resolve_schema(schema, "json")
        payload = (_canonical_json(value) + "\n").encode("utf-8")
        return self._context._emit(name, payload, ".json", resolved, stage, parents, 1)


class RunContext:
    """One append-only research run with deterministic RNG and evidence guards.

    Use it as a context manager to finalize on success and record the failure on
    any exception (the exception still propagates)::

        with EvidenceStore(root).begin(spec) as run:
            ...
        run.report  # validation report written by finalize()
    """

    def __init__(self, run_dir: Path, spec: ExperimentSpecV2, *, evaluations: int = 0,
                 elapsed_offset: float = 0.0):
        self.run_dir = run_dir
        self.run_id = run_dir.name
        self.spec = spec
        self.seed = int(spec.seed)
        self.rng = np.random.default_rng(np.random.SeedSequence(self.seed))
        self.params = dict(spec.parameters)
        self.emit = ArtifactEmitter(self)
        self.report: dict[str, Any] | None = None
        self.restored_state: dict[str, Any] | None = None
        self.resumed_from: int | None = None
        self._started = time.perf_counter()
        self._elapsed_offset = float(elapsed_offset)
        self._evaluations = int(evaluations)
        self._open = True
        self._artifacts: dict[str, dict[str, Any]] = {}
        self._metrics: dict[str, dict[str, Any]] = {}
        self._schemas = {item.id: item for item in spec.outputs}
        self._streams: dict[str, np.random.Generator] = {}
        self._checkpoints = 0

    def __enter__(self) -> "RunContext":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc is not None:
            self.fail(exc)
            return False
        if self._open:
            try:
                self.report = self.finalize()
            except BaseException as error:
                self.fail(error)
                raise
        return False

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def elapsed_seconds(self) -> float:
        """Active execution time, cumulative across resumes (downtime is not counted)."""
        return self._elapsed_offset + time.perf_counter() - self._started

    @property
    def evaluations(self) -> int:
        return self._evaluations

    def child_rng(self, label: str) -> np.random.Generator:
        """Named stream derived from (seed, label). The same label returns the same
        generator object within a run, so a stream is never silently restarted;
        its state is saved by checkpoint() and restored by resume."""
        _validate_name(label, "RNG stream")
        if label not in self._streams:
            tag = int.from_bytes(hashlib.sha256(label.encode("utf-8")).digest()[:8], "big")
            self._streams[label] = np.random.default_rng(np.random.SeedSequence([self.seed, tag]))
        return self._streams[label]

    def consume(self, evaluations: int = 0) -> None:
        self._ensure_open()
        if evaluations < 0:
            raise ValueError("evaluations cannot be negative")
        self._evaluations += evaluations
        self.check_budget()

    def check_budget(self) -> None:
        budget = self.spec.budget
        if budget.max_evaluations is not None and self._evaluations > budget.max_evaluations:
            raise BudgetExceeded(
                f"evaluation budget exceeded: {self._evaluations} > {budget.max_evaluations}",
            )
        if budget.max_seconds is not None and self.elapsed_seconds > budget.max_seconds:
            raise BudgetExceeded(
                f"wall-time budget exceeded: {self.elapsed_seconds:.6f}s > {budget.max_seconds}s",
            )

    def metric(self, name: str, value: float, *, spec: MetricSpec | None = None) -> dict[str, Any]:
        self._ensure_open()
        self.check_budget()
        if name in self._metrics:
            raise FileExistsError(f"metric {name!r} already recorded")
        resolved = spec or (self.spec.primary_metric if name == self.spec.primary_metric.name else None)
        if resolved is None:
            raise ValidationError(f"metric {name!r} requires an explicit MetricSpec")
        if resolved.name != name:
            raise ValidationError(f"metric name {name!r} does not match spec {resolved.name!r}")
        _validate_scalar(value, resolved, f"metric {name}")
        record = {"value": float(value), "spec": asdict(resolved)}
        self._metrics[name] = record
        _append_event(self.run_dir, "metric_recorded", {"name": name, **record})
        return record

    def checkpoint(self, state: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Persist everything needed to resume: evaluation count, active elapsed time,
        the main and named RNG states, the evidence emitted so far, and a JSON
        ``state`` supplied by the experiment (its own loop position, population, ...)."""
        self._ensure_open()
        sequence = self._checkpoints + 1
        record = {
            "format": CHECKPOINT_FORMAT,
            "run_id": self.run_id,
            "sequence": sequence,
            "spec_sha256": self.spec.sha256,
            "evaluations": self._evaluations,
            "elapsed_seconds": self.elapsed_seconds,
            "rng": {
                "main": self.rng.bit_generator.state,
                "streams": {label: g.bit_generator.state for label, g in sorted(self._streams.items())},
            },
            "artifacts": sorted(self._artifacts),
            "metrics": sorted(self._metrics),
            "state": dict(state or {}),
        }
        payload = (_canonical_json(record) + "\n").encode("utf-8")
        relative = Path("checkpoints") / f"ckpt-{sequence:06d}.json"
        _write_exclusive(self.run_dir / relative, payload)
        self._checkpoints = sequence
        summary = {"sequence": sequence, "path": relative.as_posix(), "sha256": _sha256_bytes(payload),
                   "evaluations": self._evaluations, "elapsed_seconds": record["elapsed_seconds"]}
        _append_event(self.run_dir, "checkpoint_written", summary)
        return summary

    def finalize(self) -> dict[str, Any]:
        self._ensure_open()
        self.check_budget()
        produced = {item["schema"]["id"] for item in self._artifacts.values()}
        missing = sorted(set(self._schemas) - produced)
        if missing:
            raise ValidationError(f"run omitted declared output schemas {missing}")
        primary = self.spec.primary_metric.name
        if primary not in self._metrics:
            raise ValidationError(f"run omitted primary metric {primary!r}")
        _write_exclusive(
            self.run_dir / "artifacts.json",
            (_canonical_json(list(self._artifacts.values())) + "\n").encode("utf-8"),
        )
        _write_exclusive(
            self.run_dir / "metrics.json",
            (_canonical_json(self._metrics) + "\n").encode("utf-8"),
        )
        _append_event(self.run_dir, "run_finalized", {
            "elapsed_seconds": self.elapsed_seconds,
            "evaluations": self._evaluations,
            "artifact_count": len(self._artifacts),
            "artifacts_sha256": _sha256_file(self.run_dir / "artifacts.json"),
            "metrics_sha256": _sha256_file(self.run_dir / "metrics.json"),
        })
        self._open = False
        self.report = validate_run(self.run_dir.parent.parent, self.run_id, record=True)
        return self.report

    def fail(self, error: BaseException) -> None:
        self.record_failure(type(error).__name__, str(error))

    def record_failure(self, error_type: str, message: str) -> None:
        """Close the run as failed (no-op if it is already closed). Used directly by
        bridge clients whose own code failed outside this process."""
        if self._open:
            _append_event(self.run_dir, "run_failed", {
                "error_type": str(error_type),
                "message": str(message),
                "elapsed_seconds": self.elapsed_seconds,
                "evaluations": self._evaluations,
            })
            self._open = False

    def _ensure_open(self) -> None:
        if not self._open:
            raise EvidenceError(f"run {self.run_id} is closed")

    def _resolve_schema(self, schema: str | ArtifactSchema, kind: ArtifactKind) -> ArtifactSchema:
        resolved = schema if isinstance(schema, ArtifactSchema) else self._schemas.get(schema)
        if resolved is None or resolved.id not in self._schemas:
            raise ValidationError(f"schema {schema!r} was not declared by the experiment")
        if resolved != self._schemas[resolved.id]:
            raise ValidationError(f"schema {resolved.id} differs from its declaration")
        if resolved.kind != kind:
            raise ValidationError(f"schema {resolved.id} has kind {resolved.kind}, expected {kind}")
        return resolved

    def _emit(
        self,
        name: str,
        payload: bytes,
        suffix: str,
        schema: ArtifactSchema,
        stage: Stage,
        parents: Iterable[str],
        observations: int,
    ) -> dict[str, Any]:
        self._ensure_open()
        self.check_budget()
        _validate_name(name, "artifact")
        if stage not in ("raw", "derived", "analysis"):
            raise ValidationError(f"unknown artifact stage {stage!r}")
        if name in self._artifacts:
            raise FileExistsError(f"artifact {name!r} already exists")
        parent_list = list(parents)
        unknown = sorted(set(parent_list) - set(self._artifacts))
        if unknown:
            raise ValidationError(f"artifact {name!r} has unknown parents {unknown}")
        if stage != "raw" and not parent_list:
            raise ValidationError(f"{stage} artifact {name!r} requires explicit parents")
        relative = Path("artifacts") / stage / f"{name}{suffix}"
        path = self.run_dir / relative
        _write_exclusive(path, payload)
        descriptor = {
            "name": name,
            "stage": stage,
            "path": relative.as_posix(),
            "schema": schema.to_dict(),
            "parents": parent_list,
            "sha256": _sha256_bytes(payload),
            "bytes": len(payload),
            "observations": observations,
        }
        self._artifacts[name] = descriptor
        _append_event(self.run_dir, "artifact_emitted", descriptor)
        return descriptor


# --------------------------------------------------------------------------- store

class EvidenceStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.runs = self.root / "research-runs"
        self.runs.mkdir(parents=True, exist_ok=True)

    def begin(self, spec: ExperimentSpecV2) -> RunContext:
        provenance = _provenance(spec)
        run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}"
        run_dir = self.runs / run_id
        run_dir.mkdir(parents=False, exist_ok=False)
        spec_bytes = (_canonical_json(spec.to_dict()) + "\n").encode("utf-8")
        provenance_bytes = (_canonical_json(provenance) + "\n").encode("utf-8")
        _write_exclusive(run_dir / "spec.json", spec_bytes)
        _write_exclusive(run_dir / "provenance.json", provenance_bytes)
        _append_event(run_dir, "run_started", {
            "seed": spec.seed,
            "capability": spec.capability,
            "reproduction_of": spec.reproduction_of,
            "spec_sha256": _sha256_bytes(spec_bytes),
            "provenance_sha256": _sha256_bytes(provenance_bytes),
        })
        return RunContext(run_dir, spec)

    def resume(self, run_id: str, spec: ExperimentSpecV2 | None = None) -> RunContext:
        return resume_context(self.root, run_id, spec)

    def inspect(self, run_id: str) -> dict[str, Any]:
        return inspect_run(self.root, run_id)

    def validate(self, run_id: str) -> dict[str, Any]:
        return validate_run(self.root, run_id, record=True)

    def compare(self, left: str, right: str) -> dict[str, Any]:
        return compare_runs(self.root, left, right)

    def accept(self, run_id: str, rationale: str) -> dict[str, Any]:
        return accept_run(self.root, run_id, rationale)

    def reject(self, run_id: str, reason: str) -> dict[str, Any]:
        return reject_run(self.root, run_id, reason)

    def reproduce(self, run_id: str) -> dict[str, Any]:
        return reproduce_run(self.root, run_id)

    def list(self, **filters: Any) -> list[dict[str, Any]]:
        return list_runs(self.root, **filters)

    def lineage(self) -> dict[str, Any]:
        return lineage_graph(self.root)

    def export_bundle(self, run_ids: Iterable[str], destination: str | Path, **options: Any) -> dict[str, Any]:
        from .bundle import export_bundle

        return export_bundle(self.root, run_ids, destination, **options)


def _run_dir(root: str | Path, run_id: str) -> Path:
    _validate_name(run_id, "run id")
    path = Path(root).resolve() / "research-runs" / run_id
    if not path.is_dir():
        raise FileNotFoundError(f"unknown run {run_id}")
    return path


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def inspect_run(root: str | Path, run_id: str) -> dict[str, Any]:
    run_dir = _run_dir(root, run_id)
    events = _read_events(run_dir)
    return {
        "run_id": run_id,
        "status": _status(events),
        "spec": _read_json(run_dir / "spec.json"),
        "provenance": _read_json(run_dir / "provenance.json"),
        "artifacts": _read_json(run_dir / "artifacts.json", []),
        "metrics": _read_json(run_dir / "metrics.json", {}),
        "events": events,
    }


def validate_run(root: str | Path, run_id: str, *, record: bool = False) -> dict[str, Any]:
    """Completeness and integrity check of a finished run. Raises ValidationError
    listing every problem; with ``record`` a raw_complete run becomes validated."""
    run_dir = _run_dir(root, run_id)
    lines = _event_lines(run_dir)
    events = [json.loads(line) for line in lines]
    status = _status(events)
    if status in {"running", "failed", "unknown"}:
        raise ValidationError(f"run {run_id} is {status}, not complete evidence")
    errors = _integrity_errors(run_dir, lines, events)
    try:
        snapshot = inspect_run(root, run_id)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationError(f"run {run_id} metadata is unreadable: {exc}") from exc
    finalized = next((e["payload"] for e in events if e["type"] == "run_finalized"), {})
    for name, key in (("artifacts.json", "artifacts_sha256"), ("metrics.json", "metrics_sha256")):
        if key in finalized and (not (run_dir / name).is_file() or _sha256_file(run_dir / name) != finalized[key]):
            errors.append(f"{name} does not match the hash recorded at finalization")
    declared = {item["id"]: item for item in (snapshot["spec"] or {}).get("outputs", [])}
    produced = [artifact.get("schema", {}).get("id") for artifact in snapshot["artifacts"]]
    missing = sorted(set(declared) - set(produced))
    undeclared = sorted(set(produced) - set(declared))
    if missing:
        errors.append(f"declared output schemas not produced: {missing}")
    if undeclared:
        errors.append(f"undeclared output schemas produced: {undeclared}")
    if len(produced) != len(set(produced)):
        errors.append("an output schema was produced more than once")
    emitted = {e["payload"]["name"]: e["payload"]["sha256"] for e in events if e["type"] == "artifact_emitted"}
    for artifact in snapshot["artifacts"]:
        if emitted.get(artifact["name"]) != artifact.get("sha256"):
            errors.append(f"artifact {artifact['name']} differs from the event log")
        if artifact["name"] not in emitted:
            errors.extend(_artifact_errors(run_dir, artifact))
    primary = (snapshot["spec"] or {}).get("primary_metric", {}).get("name")
    if primary not in snapshot["metrics"]:
        errors.append(f"primary metric {primary!r} is missing")
    for name, metric in snapshot["metrics"].items():
        try:
            _validate_scalar(metric["value"], MetricSpec.from_dict(metric["spec"]), f"metric {name}")
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        raise ValidationError("; ".join(dict.fromkeys(errors)))
    if record and status == "raw_complete":
        _append_event(run_dir, "run_validated", {"artifact_count": len(snapshot["artifacts"])})
    return {"run_id": run_id, "valid": True, "status": _status(_read_events(run_dir)), "errors": []}


def _decide(root: str | Path, run_id: str, decision: Literal["accept", "reject"], text: str) -> dict[str, Any]:
    """Evidence decisions are terminal. Repeating the identical decision with the
    identical text is an idempotent no-op; any other second decision is refused."""
    target, event_type, key = {
        "accept": ("accepted_as_evidence", "run_accepted", "rationale"),
        "reject": ("rejected_as_evidence", "run_rejected", "reason"),
    }[decision]
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{decision} requires a non-empty {key}")
    run_dir = _run_dir(root, run_id)
    events = _read_events(run_dir)
    status = _status(events)
    if status in {"accepted_as_evidence", "rejected_as_evidence"}:
        previous = next(e for e in reversed(events) if e["type"] in {"run_accepted", "run_rejected"})
        if status == target and previous["payload"].get(key) == text:
            return {"run_id": run_id, "status": status, key: text, "idempotent": True}
        raise EvidenceError(f"run {run_id} is already {status}; evidence decisions are terminal")
    if status not in {"raw_complete", "validated"}:
        raise EvidenceError(f"run {run_id} is {status}; only a finished run can be {decision}ed")
    payload: dict[str, Any] = {key: text}
    if decision == "accept":
        validate_run(root, run_id, record=True)
    else:
        try:
            validate_run(root, run_id)
            payload["integrity"] = "valid"
        except ValidationError as exc:
            payload["integrity"] = f"invalid: {exc}"
    _append_event(run_dir, event_type, payload)
    return {"run_id": run_id, "status": target, **payload, "idempotent": False}


def accept_run(root: str | Path, run_id: str, rationale: str) -> dict[str, Any]:
    """Accept a run as evidence. The run must validate; acceptance is terminal."""
    return _decide(root, run_id, "accept", rationale)


def reject_run(root: str | Path, run_id: str, reason: str) -> dict[str, Any]:
    """Reject a finished run as evidence (a reason is required; rejection is terminal).
    Invalid runs may be rejected; the integrity result is recorded with the reason."""
    return _decide(root, run_id, "reject", reason)


def list_runs(
    root: str | Path,
    *,
    capability: str | None = None,
    status: str | None = None,
    seed: int | None = None,
    created_after: Any = None,
    created_before: Any = None,
) -> list[dict[str, Any]]:
    """Run summaries ordered by creation time, optionally filtered. Times accept
    ISO-8601 strings, datetimes, or unix nanoseconds; bounds are inclusive."""
    if status is not None and status not in STATUSES + ("unreadable",):
        raise ValueError(f"unknown status {status!r}; expected one of {STATUSES}")
    after = _to_unix_ns(created_after) if created_after is not None else None
    before = _to_unix_ns(created_before) if created_before is not None else None
    runs_dir = Path(root).resolve() / "research-runs"
    rows = []
    for run_dir in sorted(runs_dir.iterdir()) if runs_dir.is_dir() else []:
        if not run_dir.is_dir() or not _NAME.fullmatch(run_dir.name):
            continue
        try:
            events = _read_events(run_dir)
            spec = json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
            created = int(events[0]["time_unix_ns"])
            row = {
                "run_id": run_dir.name,
                "status": _status(events),
                "capability": spec["capability"],
                "hypothesis": spec["hypothesis"],
                "seed": spec["seed"],
                "created_unix_ns": created,
                "created_at": _utc_iso(created),
                "reproduction_of": spec.get("reproduction_of"),
                "resumes": sum(e["type"] == "run_resumed" for e in events),
            }
        except Exception as exc:
            row = {"run_id": run_dir.name, "status": "unreadable", "error": type(exc).__name__,
                   "capability": None, "hypothesis": None, "seed": None, "created_unix_ns": None,
                   "created_at": None, "reproduction_of": None, "resumes": 0}
        if capability is not None and row["capability"] != capability:
            continue
        if status is not None and row["status"] != status:
            continue
        if seed is not None and row["seed"] != seed:
            continue
        if after is not None and (row["created_unix_ns"] is None or row["created_unix_ns"] < after):
            continue
        if before is not None and (row["created_unix_ns"] is None or row["created_unix_ns"] > before):
            continue
        rows.append(row)
    return sorted(rows, key=lambda r: (r["created_unix_ns"] is None, r["created_unix_ns"] or 0, r["run_id"]))


def compare_runs(root: str | Path, left: str, right: str) -> dict[str, Any]:
    a, b = inspect_run(root, left), inspect_run(root, right)
    validate_run(root, left)
    validate_run(root, right)
    common = sorted(set(a["metrics"]) & set(b["metrics"]))
    comparisons = {}
    for name in common:
        ma, mb = a["metrics"][name], b["metrics"][name]
        if ma["spec"]["unit"] != mb["spec"]["unit"]:
            raise ValidationError(f"metric {name} uses incompatible units")
        av, bv = float(ma["value"]), float(mb["value"])
        comparisons[name] = {
            "unit": ma["spec"]["unit"],
            "left": av,
            "right": bv,
            "delta_right_minus_left": bv - av,
            "relative_change": (bv - av) / abs(av) if av else None,
        }
    left_hashes = {item["name"]: item["sha256"] for item in a["artifacts"]}
    right_hashes = {item["name"]: item["sha256"] for item in b["artifacts"]}
    return {
        "left": left,
        "right": right,
        "same_capability": a["spec"]["capability"] == b["spec"]["capability"],
        "same_hypothesis": a["spec"]["hypothesis"] == b["spec"]["hypothesis"],
        "same_spec_except_lineage": _spec_core(a["spec"]) == _spec_core(b["spec"]),
        "metrics": comparisons,
        "artifacts": {
            name: {"identical": left_hashes.get(name) == right_hashes.get(name),
                   "left_sha256": left_hashes.get(name), "right_sha256": right_hashes.get(name)}
            for name in sorted(set(left_hashes) | set(right_hashes))
        },
    }


def _spec_core(spec: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in spec.items() if k != "reproduction_of"}


def lineage_graph(root: str | Path) -> dict[str, Any]:
    """Provenance graph of a store: artifact -> artifact edges inside runs (declared
    parents) and artifact -> run edges across runs (an input whose SHA-256 equals an
    artifact some other run produced). Inputs no run produced are listed as external."""
    runs = [row for row in list_runs(root) if row["status"] != "unreadable"]
    produced: dict[str, list[dict[str, str]]] = {}
    snapshots = {}
    for row in runs:
        snap = inspect_run(root, row["run_id"])
        snapshots[row["run_id"]] = snap
        emitted = [e["payload"] for e in snap["events"] if e["type"] == "artifact_emitted"]
        for artifact in emitted:
            produced.setdefault(artifact["sha256"], []).append(
                {"run_id": row["run_id"], "artifact": artifact["name"], "stage": artifact["stage"]})
    edges, external = [], []
    for run_id, snap in snapshots.items():
        for artifact in (e["payload"] for e in snap["events"] if e["type"] == "artifact_emitted"):
            for parent in artifact["parents"]:
                edges.append({"kind": "parent", "from_run": run_id, "from_artifact": parent,
                              "to_run": run_id, "to_artifact": artifact["name"]})
        for name, item in sorted((snap["provenance"] or {}).get("inputs", {}).items()):
            sources = [p for p in produced.get(item["sha256"], []) if p["run_id"] != run_id]
            if not sources:
                external.append({"run_id": run_id, "input": name, "path": item["path"], "sha256": item["sha256"]})
            for source in sources:
                edges.append({"kind": "input", "from_run": source["run_id"], "from_artifact": source["artifact"],
                              "to_run": run_id, "input": name, "sha256": item["sha256"]})
    return {"runs": [{k: r[k] for k in ("run_id", "status", "capability", "created_at")} for r in runs],
            "edges": edges, "external_inputs": external}


# --------------------------------------------------------------------------- resume

def resume_context(root: str | Path, run_id: str, spec: ExperimentSpecV2 | None = None) -> RunContext:
    """Reopen an interrupted run from its last checkpoint.

    Refused (fail closed) when the run is finished, failed, or decided; has no
    checkpoint; is corrupted (event chain, metadata, artifact, or checkpoint
    hashes); was given an incompatible spec; depends on an input, protocol, or
    runner that changed; or emitted evidence after its last checkpoint (that
    evidence would be orphaned or duplicated by the resumed code).
    """
    run_dir = _run_dir(root, run_id)
    lines = _event_lines(run_dir)
    events = [json.loads(line) for line in lines]
    status = _status(events)
    if status != "running":
        raise EvidenceError(f"run {run_id} is {status}; only an interrupted running run can be resumed")
    problems = _integrity_errors(run_dir, lines, events)
    if problems:
        raise ValidationError(f"cannot resume corrupted run {run_id}: " + "; ".join(problems))
    recorded = ExperimentSpecV2.from_dict(json.loads((run_dir / "spec.json").read_text(encoding="utf-8")))
    recorded_sha = _sha256_file(run_dir / "spec.json")  # the file as written, independent of normalisation
    if spec is not None and spec.sha256 != recorded_sha:
        raise EvidenceError(f"incompatible spec: run {run_id} was started with spec {recorded_sha[:12]}, "
                            f"resume was given {spec.sha256[:12]}")
    checkpoints = [i for i, e in enumerate(events) if e["type"] == "checkpoint_written"]
    if not checkpoints:
        raise EvidenceError(f"run {run_id} has no checkpoint to resume from")
    last = checkpoints[-1]
    late = [e["type"] for e in events[last + 1:] if e["type"] in {"artifact_emitted", "metric_recorded"}]
    if late:
        raise EvidenceError(f"run {run_id} recorded {late} after its last checkpoint; resuming would orphan them")
    info = events[last]["payload"]
    record = json.loads((run_dir / info["path"]).read_text(encoding="utf-8"))
    if (record.get("format") != CHECKPOINT_FORMAT or record.get("run_id") != run_id
            or record.get("sequence") != info["sequence"] or record.get("spec_sha256") != recorded_sha):
        raise ValidationError(f"checkpoint {info['sequence']} of run {run_id} does not belong to this run/spec")
    incompatible = _compatibility_errors(recorded.to_dict(), _read_json(run_dir / "provenance.json", {}))
    if incompatible:
        raise EvidenceError(f"cannot resume run {run_id}: " + "; ".join(incompatible))

    context = RunContext(run_dir, recorded, evaluations=record["evaluations"],
                         elapsed_offset=record["elapsed_seconds"])
    context.rng.bit_generator.state = record["rng"]["main"]
    for label, state in record["rng"]["streams"].items():
        context.child_rng(label).bit_generator.state = state
    for event in events[:last]:
        if event["type"] == "artifact_emitted":
            context._artifacts[event["payload"]["name"]] = dict(event["payload"])
        elif event["type"] == "metric_recorded":
            payload = event["payload"]
            context._metrics[payload["name"]] = {"value": payload["value"], "spec": payload["spec"]}
    context._checkpoints = info["sequence"]
    context.restored_state = record["state"]
    context.resumed_from = info["sequence"]
    _append_event(run_dir, "run_resumed", {"checkpoint_sequence": info["sequence"],
                                           "evaluations": record["evaluations"],
                                           "elapsed_seconds": record["elapsed_seconds"]})
    return context


# --------------------------------------------------------------------------- declared experiments

class ExperimentDefinition:
    def __init__(
        self,
        function: Callable[[RunContext], Any],
        *,
        capability: str,
        hypothesis: str,
        protocol: str,
        outputs: Iterable[ArtifactSchema],
        primary_metric: MetricSpec,
    ):
        self.function = function
        self.capability = capability
        self.hypothesis = hypothesis
        self.protocol = protocol
        self.outputs = tuple(outputs)
        self.primary_metric = primary_metric
        self.__name__ = function.__name__
        self.__doc__ = function.__doc__
        self.__module__ = function.__module__
        self.__qualname__ = function.__qualname__

    @property
    def reference(self) -> str:
        return f"{self.__module__}:{self.__qualname__}"

    def spec(
        self,
        *,
        parameters: Mapping[str, Any],
        seed: int,
        budget: ResourceBudget | None = None,
        inputs: Mapping[str, str] | None = None,
        reproduction_of: str | None = None,
    ) -> ExperimentSpecV2:
        return ExperimentSpecV2(
            capability=self.capability,
            hypothesis=self.hypothesis,
            protocol=self.protocol,
            parameters=dict(parameters),
            seed=seed,
            outputs=self.outputs,
            primary_metric=self.primary_metric,
            budget=budget or ResourceBudget(),
            runner=self.reference,
            inputs=dict(inputs or {}),
            reproduction_of=reproduction_of,
        )

    def run(
        self,
        root: str | Path,
        *,
        parameters: Mapping[str, Any],
        seed: int,
        budget: ResourceBudget | None = None,
        inputs: Mapping[str, str] | None = None,
        reproduction_of: str | None = None,
    ) -> dict[str, Any]:
        spec = self.spec(parameters=parameters, seed=seed, budget=budget, inputs=inputs,
                         reproduction_of=reproduction_of)
        with EvidenceStore(root).begin(spec) as context:
            self.function(context)
        return context.report

    def resume(self, root: str | Path, run_id: str) -> dict[str, Any]:
        """Continue an interrupted run of this definition from its last checkpoint.
        The function sees ``run.restored_state`` and ``run.resumed_from``."""
        recorded = inspect_run(root, run_id)["spec"]
        if recorded.get("runner") != self.reference:
            raise EvidenceError(f"run {run_id} was started by {recorded.get('runner')!r}, not {self.reference!r}")
        with EvidenceStore(root).resume(run_id) as context:
            self.function(context)
        return context.report

    def __call__(self, context: RunContext) -> Any:
        return self.function(context)


def experiment(
    *,
    capability: str,
    hypothesis: str,
    protocol: str,
    outputs: Iterable[ArtifactSchema],
    primary_metric: MetricSpec,
) -> Callable[[Callable[[RunContext], Any]], ExperimentDefinition]:
    """Declare a reproducible Python experiment with explicit evidence contracts."""

    def decorate(function: Callable[[RunContext], Any]) -> ExperimentDefinition:
        return ExperimentDefinition(
            function,
            capability=capability,
            hypothesis=hypothesis,
            protocol=protocol,
            outputs=outputs,
            primary_metric=primary_metric,
        )

    return decorate


def load_runner(reference: str) -> ExperimentDefinition:
    module_name, separator, qualname = reference.partition(":")
    if not separator:
        raise EvidenceError(f"invalid runner reference {reference!r}")
    obj: Any = importlib.import_module(module_name)
    for part in qualname.split("."):
        obj = getattr(obj, part)
    if not isinstance(obj, ExperimentDefinition):
        raise EvidenceError(f"runner {reference!r} is not an ExperimentDefinition")
    return obj


def reproduce_run(root: str | Path, run_id: str) -> dict[str, Any]:
    """Rerun an importable experiment with the recorded parameters, seed, budget and
    inputs, then report which artifacts reproduced byte-for-byte."""
    snapshot = inspect_run(root, run_id)
    validate_run(root, run_id)
    runner = snapshot["spec"].get("runner")
    if not runner:
        raise EvidenceError(f"run {run_id} has no importable runner")
    definition = load_runner(runner)
    incompatible = _compatibility_errors(snapshot["spec"], snapshot["provenance"])
    if incompatible:
        raise EvidenceError(f"cannot reproduce run {run_id}: " + "; ".join(incompatible))
    spec = snapshot["spec"]
    report = definition.run(
        root,
        parameters=spec["parameters"],
        seed=spec["seed"],
        budget=ResourceBudget.from_dict(spec.get("budget")),
        inputs=spec.get("inputs", {}),
        reproduction_of=run_id,
    )
    comparison = compare_runs(root, run_id, report["run_id"])
    return {**report, "reproduction_of": run_id,
            "identical_artifacts": all(item["identical"] for item in comparison["artifacts"].values()),
            "artifacts": comparison["artifacts"]}


def resume_run(root: str | Path, run_id: str) -> dict[str, Any]:
    """Resume an interrupted run of an importable experiment definition."""
    runner = inspect_run(root, run_id)["spec"].get("runner")
    if not runner:
        raise EvidenceError(f"run {run_id} has no importable runner; resume it from its client instead")
    return load_runner(runner).resume(root, run_id)
