"""Research-grade evidence SDK primitives.

This module is deliberately separate from the domain-specific discovery lab.
It gives arbitrary computational experiments a small, validated boundary for
reproducibility, semantic artifacts, resource accounting, and evidence state.
The existing lab remains the authoritative engine for its own experiments.
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
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping

import numpy as np

Stage = Literal["raw", "derived", "analysis"]
ArtifactKind = Literal["table", "array", "json"]
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


class EvidenceError(RuntimeError):
    """Base class for evidence-layer failures."""


class ValidationError(EvidenceError):
    """Raised when evidence violates its declared scientific contract."""


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
        if self.dtype not in {"number", "integer"} and (
            self.minimum is not None or self.maximum is not None or self.censoring is not None
        ):
            raise ValueError(f"field {self.name}: ranges and censoring require a numeric dtype")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError(f"field {self.name}: minimum exceeds maximum")

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
        if self.kind == "table" and not self.fields:
            raise ValueError("table schemas require at least one field")
        if self.kind == "array" and not self.dtype:
            raise ValueError("array schemas require dtype")
        if self.ndim is not None and self.ndim < 0:
            raise ValueError("ndim cannot be negative")

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
        if not self.outputs:
            raise ValueError("at least one output schema is required")
        ids = [schema.id for schema in self.outputs]
        if len(ids) != len(set(ids)):
            raise ValueError("output schema ids must be unique")
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

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ExperimentSpecV2":
        data = dict(value)
        version = data.pop("spec_version", 2)
        if version != 2:
            raise ValueError(f"ExperimentSpecV2 requires spec_version 2, received {version!r}")
        data["outputs"] = tuple(ArtifactSchema.from_dict(item) for item in data["outputs"])
        data["primary_metric"] = MetricSpec.from_dict(data["primary_metric"])
        data["budget"] = ResourceBudget.from_dict(data.get("budget"))
        return cls(**data)


def _validate_name(value: str, kind: str) -> None:
    if not _NAME.fullmatch(value):
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


def _read_events(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "events.jsonl"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _append_event(run_dir: Path, event_type: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    events = _read_events(run_dir)
    event = {
        "seq": len(events) + 1,
        "time_unix_ns": time.time_ns(),
        "type": event_type,
        "payload": dict(payload or {}),
    }
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(_canonical_json(event) + "\n")
    return event


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
        return {"commit": None, "dirty": None, "error": f"{type(exc).__name__}: {exc}"}


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
            result.append(argument)
            redact_next = argument.startswith("-") and bool(sensitive.search(argument))
    return result


def _input_hashes(inputs: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    result = {}
    for name, raw_path in sorted(inputs.items()):
        _validate_name(name, "input")
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"input {name!r} does not exist: {path}")
        result[name] = {"path": str(path), "sha256": _sha256_file(path), "bytes": path.stat().st_size}
    return result


def _provenance(spec: ExperimentSpecV2) -> dict[str, Any]:
    protocol_path = Path(spec.protocol)
    runner_file = None
    if spec.runner:
        try:
            module_name, _, qualname = spec.runner.partition(":")
            obj: Any = importlib.import_module(module_name)
            for part in qualname.split("."):
                obj = getattr(obj, part)
            runner_file = inspect.getsourcefile(getattr(obj, "function", obj))
        except Exception:
            runner_file = None
    return {
        "git": _git_provenance(Path.cwd()),
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
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
            "path": runner_file,
            "sha256": _sha256_file(Path(runner_file)) if runner_file and Path(runner_file).is_file() else None,
        },
        "inputs": _input_hashes(spec.inputs),
    }


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
        np.save(buffer, array, allow_pickle=False)
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
    """One append-only research run with deterministic RNG and evidence guards."""

    def __init__(self, run_dir: Path, spec: ExperimentSpecV2):
        self.run_dir = run_dir
        self.run_id = run_dir.name
        self.spec = spec
        self.seed = int(spec.seed)
        self.rng = np.random.default_rng(np.random.SeedSequence(self.seed))
        self.params = dict(spec.parameters)
        self.emit = ArtifactEmitter(self)
        self._started = time.perf_counter()
        self._evaluations = 0
        self._open = True
        self._artifacts: dict[str, dict[str, Any]] = {}
        self._metrics: dict[str, dict[str, Any]] = {}
        self._schemas = {item.id: item for item in spec.outputs}

    @property
    def elapsed_seconds(self) -> float:
        return time.perf_counter() - self._started

    @property
    def evaluations(self) -> int:
        return self._evaluations

    def child_rng(self, label: str) -> np.random.Generator:
        _validate_name(label, "RNG stream")
        tag = int.from_bytes(hashlib.sha256(label.encode("utf-8")).digest()[:8], "big")
        return np.random.default_rng(np.random.SeedSequence([self.seed, tag]))

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
        })
        self._open = False
        return validate_run(self.run_dir.parent.parent, self.run_id, record=True)

    def fail(self, error: BaseException) -> None:
        if self._open:
            _append_event(self.run_dir, "run_failed", {
                "error_type": type(error).__name__,
                "message": str(error),
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
        _write_exclusive(run_dir / "spec.json", (_canonical_json(spec.to_dict()) + "\n").encode("utf-8"))
        _write_exclusive(
            run_dir / "provenance.json",
            (_canonical_json(provenance) + "\n").encode("utf-8"),
        )
        _append_event(run_dir, "run_started", {
            "seed": spec.seed,
            "capability": spec.capability,
            "reproduction_of": spec.reproduction_of,
        })
        return RunContext(run_dir, spec)

    def inspect(self, run_id: str) -> dict[str, Any]:
        return inspect_run(self.root, run_id)

    def validate(self, run_id: str) -> dict[str, Any]:
        return validate_run(self.root, run_id, record=True)

    def compare(self, left: str, right: str) -> dict[str, Any]:
        return compare_runs(self.root, left, right)

    def accept(self, run_id: str, rationale: str) -> dict[str, Any]:
        return accept_run(self.root, run_id, rationale)

    def reproduce(self, run_id: str) -> dict[str, Any]:
        return reproduce_run(self.root, run_id)


def _run_dir(root: str | Path, run_id: str) -> Path:
    _validate_name(run_id, "run id")
    path = Path(root).resolve() / "research-runs" / run_id
    if not path.is_dir():
        raise FileNotFoundError(f"unknown run {run_id}")
    return path


def _status(events: list[dict[str, Any]]) -> str:
    transitions = {
        "run_started": "running",
        "run_failed": "failed",
        "run_finalized": "raw_complete",
        "run_validated": "validated",
        "run_accepted": "accepted_as_evidence",
    }
    status = "unknown"
    for event in events:
        status = transitions.get(event["type"], status)
    return status


def inspect_run(root: str | Path, run_id: str) -> dict[str, Any]:
    run_dir = _run_dir(root, run_id)
    events = _read_events(run_dir)
    return {
        "run_id": run_id,
        "status": _status(events),
        "spec": json.loads((run_dir / "spec.json").read_text(encoding="utf-8")),
        "provenance": json.loads((run_dir / "provenance.json").read_text(encoding="utf-8")),
        "artifacts": json.loads((run_dir / "artifacts.json").read_text(encoding="utf-8"))
        if (run_dir / "artifacts.json").exists() else [],
        "metrics": json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
        if (run_dir / "metrics.json").exists() else {},
        "events": events,
    }


def validate_run(root: str | Path, run_id: str, *, record: bool = False) -> dict[str, Any]:
    run_dir = _run_dir(root, run_id)
    snapshot = inspect_run(root, run_id)
    if snapshot["status"] in {"running", "failed", "unknown"}:
        raise ValidationError(f"run {run_id} is {snapshot['status']}, not complete evidence")
    errors = []
    declared = {
        item["id"]: item for item in snapshot["spec"].get("outputs", [])
    }
    produced = [artifact.get("schema", {}).get("id") for artifact in snapshot["artifacts"]]
    missing = sorted(set(declared) - set(produced))
    undeclared = sorted(set(produced) - set(declared))
    if missing:
        errors.append(f"declared output schemas not produced: {missing}")
    if undeclared:
        errors.append(f"undeclared output schemas produced: {undeclared}")
    if len(produced) != len(set(produced)):
        errors.append("an output schema was produced more than once")
    primary = snapshot["spec"].get("primary_metric", {}).get("name")
    if primary not in snapshot["metrics"]:
        errors.append(f"primary metric {primary!r} is missing")
    for artifact in snapshot["artifacts"]:
        path = (run_dir / artifact["path"]).resolve()
        if not path.is_relative_to(run_dir.resolve()):
            errors.append(f"artifact {artifact['name']} escapes its run directory")
            continue
        if not path.is_file():
            errors.append(f"artifact {artifact['name']} is missing")
            continue
        if _sha256_file(path) != artifact["sha256"]:
            errors.append(f"artifact {artifact['name']} hash mismatch")
            continue
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
            errors.append(f"artifact {artifact['name']} schema failure: {exc}")
    for name, metric in snapshot["metrics"].items():
        try:
            _validate_scalar(metric["value"], MetricSpec.from_dict(metric["spec"]), f"metric {name}")
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        raise ValidationError("; ".join(errors))
    if record and snapshot["status"] == "raw_complete":
        _append_event(run_dir, "run_validated", {"artifact_count": len(snapshot["artifacts"])})
    return {"run_id": run_id, "valid": True, "status": _status(_read_events(run_dir)), "errors": []}


def accept_run(root: str | Path, run_id: str, rationale: str) -> dict[str, Any]:
    validate_run(root, run_id, record=True)
    run_dir = _run_dir(root, run_id)
    status = _status(_read_events(run_dir))
    if status == "accepted_as_evidence":
        raise EvidenceError(f"run {run_id} is already accepted")
    if not rationale.strip():
        raise ValueError("acceptance rationale cannot be empty")
    _append_event(run_dir, "run_accepted", {"rationale": rationale})
    return {"run_id": run_id, "status": "accepted_as_evidence"}


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
    return {
        "left": left,
        "right": right,
        "same_capability": a["spec"]["capability"] == b["spec"]["capability"],
        "same_hypothesis": a["spec"]["hypothesis"] == b["spec"]["hypothesis"],
        "metrics": comparisons,
    }


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
        spec = ExperimentSpecV2(
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
        context = EvidenceStore(root).begin(spec)
        try:
            self.function(context)
            return context.finalize()
        except BaseException as exc:
            context.fail(exc)
            raise

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


def reproduce_run(root: str | Path, run_id: str) -> dict[str, Any]:
    snapshot = inspect_run(root, run_id)
    validate_run(root, run_id)
    runner = snapshot["spec"].get("runner")
    if not runner:
        raise EvidenceError(f"run {run_id} has no importable runner")
    module_name, separator, qualname = runner.partition(":")
    if not separator:
        raise EvidenceError(f"invalid runner reference {runner!r}")
    obj: Any = importlib.import_module(module_name)
    for part in qualname.split("."):
        obj = getattr(obj, part)
    if not isinstance(obj, ExperimentDefinition):
        raise EvidenceError(f"runner {runner!r} is not an ExperimentDefinition")
    current_inputs = _input_hashes(snapshot["spec"].get("inputs", {}))
    if current_inputs != snapshot["provenance"].get("inputs", {}):
        raise EvidenceError("an input changed since the original run")
    runner_file = inspect.getsourcefile(obj.function)
    recorded_hash = snapshot["provenance"].get("runner", {}).get("sha256")
    current_hash = _sha256_file(Path(runner_file)) if runner_file else None
    if recorded_hash != current_hash:
        raise EvidenceError("the experiment runner changed since the original run")
    spec = snapshot["spec"]
    return obj.run(
        root,
        parameters=spec["parameters"],
        seed=spec["seed"],
        budget=ResourceBudget.from_dict(spec.get("budget")),
        inputs=spec.get("inputs", {}),
        reproduction_of=run_id,
    )
