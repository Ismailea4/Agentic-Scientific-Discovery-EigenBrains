# SDK contracts

## Stability boundary

Protocol version `1.0` is the cross-language compatibility boundary. Python
may evolve internally, but Rust and Julia clients depend only on the envelopes
defined by [`sdk/protocol/v1/schema.json`](../sdk/protocol/v1/schema.json).

Request:

```json
{"id": 1, "version": "1.0", "method": "state", "params": {}}
```

Success:

```json
{"id": 1, "version": "1.0", "ok": true, "result": {}}
```

Failure:

```json
{"id": 1, "version": "1.0", "ok": false,
 "error": {"code": "LedgerError", "message": "..."}}
```

The bridge returns expected validation and transition failures as structured
errors and stays alive. Invalid JSON also returns a structured error with a
null request id. One input line always produces one output line.

Rust exposes remote failures as `SdkError::Remote { code, message }`; Julia
raises `ProtocolError(code, message)`. Both clients additionally reject response
id/version mismatches and successful envelopes that omit `result`, and both
validate evidence contracts locally before sending (`SdkError::Invalid`,
`ContractError`).

Error codes are the Python exception class names:

| Code | Meaning |
|---|---|
| `ValueError` | malformed request, unknown method or parameter, invalid value |
| `KeyError` | unknown experiment, or no open research run with that id in this bridge process |
| `FileNotFoundError` | unknown run, input, or bundle |
| `FileExistsError` | artifact, metric, or bundle name already used |
| `PermissionError` | refused by policy (held-out run without confirmation, runner module not allow-listed) |
| `LedgerError` | refused laboratory transition |
| `EvidenceError` | refused evidence lifecycle transition (closed, finished, decided, not resumable) |
| `ValidationError` | evidence violates its declared contract or fails an integrity check |
| `BudgetExceeded` | cooperative evaluation or wall-time budget exhausted |

## Methods

The method table is closed and declarative (`discolab.rpc.METHODS`). The schema
carries the same table under `x-methods` (required and optional parameters,
mutation flag) and a test keeps the two identical. A request with a missing
required parameter or **any unknown parameter** is rejected with `ValueError`,
so a typo cannot silently fall back to a default.

| Method | Required parameters | Optional | Mutation |
|---|---|---|---|
| `describe` | none | | no (protocol version, methods, runner policy) |
| `initialize` | none | | creates the first ledger event |
| `state` | none | | no |
| `events` | none | | no |
| `propose` | `experiment` | | appends a validated candidate |
| `score` | none | | appends a deterministic scoring round |
| `select` | `experiment_id`, `justification` | | selects a feasible scored experiment |
| `run` | none | `confirm_heldout` (default false) | runs the selected experiment and records artifacts/results |
| `abort` | `experiment_id`, `reason` | | records an interrupted run as failed |
| `result` | `experiment_id` | | no |
| `analyze` | `experiment_id`, `interpretation` | `threats_to_validity` | records analysis and deterministic belief updates |
| `decide` | `decision`, `rationale` | `next_experiment` | records the next scientific decision |
| `register_hypothesis` | `hypothesis_id`, `statement`, `h0`, `family` | `feature_set`, `baseline_feature_set`, `controller`, `comparator` | appends a testable agent-generated hypothesis |
| `research.begin` | `spec` (`ExperimentSpecV2`) | | creates a generic evidence run |
| `research.emit` | `run_id`, `name`, `kind`, `value`, `schema` | `stage`, `parents` | validates and writes one semantic artifact |
| `research.metric` | `run_id`, `name`, `value` | `spec` | records one unit-bearing metric |
| `research.consume` | `run_id` | `evaluations` | accounts work and enforces cooperative budgets |
| `research.checkpoint` | `run_id` | `state` (JSON object) | writes a hash-referenced checkpoint |
| `research.resume` | `run_id` | | reopens an interrupted run in this bridge from its last checkpoint; returns the saved state |
| `research.fail` | `run_id`, `error_type`, `message` | | records a client-side failure; the run becomes failed |
| `research.finalize` | `run_id` | | closes, checks completeness, and validates a run |
| `research.inspect` | `run_id` | | no |
| `research.validate` | `run_id` | | verifies hashes and schemas; records validation once |
| `research.list` | none | `capability`, `status`, `seed`, `created_after`, `created_before` | no |
| `research.compare` | `left`, `right` | | no |
| `research.accept` | `run_id`, `rationale` | | terminal: accepted as evidence (run must validate) |
| `research.reject` | `run_id`, `reason` | | terminal: rejected as evidence (integrity result recorded) |
| `research.reproduce` | `run_id` | | reruns an allow-listed importable Python experiment definition |
| `research.lineage` | none | | no |
| `research.export_bundle` | `run_ids`, `name` | | writes `<root>/bundles/<name>.zip` |
| `research.verify_bundle` | `name` | | no (fails closed) |

The `research.*` writing calls are stateful within one bridge process between
`begin`/`resume` and `finalize`/`fail`. If the bridge exits, an unfinished run
stays `running`; a later bridge (from any language) continues it with
`research.resume` if it has a checkpoint. A finalize that fails validation
leaves the bridge run open so the client can emit what is missing; the scoped
helpers (`with_research_run` in Rust and Julia) instead record the failure,
matching Python's context manager.

## Security boundary

The bridge never executes caller-supplied code or shell commands:

- the method table is explicit (no attribute lookup by method name);
- a run may name a Python `runner` only if the bridge was started with
  `--allow-runner-module MODULE` covering it (default: none). The check runs
  before anything is imported, on `research.begin`, `research.reproduce` and
  `research.resume`;
- bundles are addressed by a validated name inside `<root>/bundles`, never by a
  free path, and archive members are checked for traversal before extraction;
- `protocol` and `inputs` paths are only read to compute SHA-256 hashes, and
  only portable forms of their paths are recorded.

## Generic evidence schema

`ExperimentSpecV2` is the common Python/Rust/Julia contract:

```json
{
  "spec_version": 2,
  "capability": "optimization",
  "hypothesis": "The controller recovers after a shift.",
  "protocol": "protocols/recovery-v1.md",
  "parameters": {"population": 64},
  "seed": 2026,
  "outputs": [{
    "name": "trajectory", "version": 1, "kind": "table",
    "fields": [
      {"name": "evaluation", "dtype": "integer", "unit": "count", "role": "index"},
      {"name": "loss", "dtype": "number", "unit": "objective", "role": "observation"}
    ]
  }],
  "primary_metric": {
    "name": "recovery_time", "unit": "evaluations", "role": "primary",
    "minimum": 0, "censoring": "right"
  },
  "budget": {"max_evaluations": 10000, "max_seconds": 60},
  "runner": null,
  "inputs": {},
  "reproduction_of": null
}
```

Field dtypes are `number`, `integer`, `string`, or `boolean`. Artifact kinds are
`table`, `array`, or `json`; stages are `raw`, `derived`, or `analysis`.
Derived/analysis artifacts require explicit parent names. Metric units must
match for comparison. See
[`RESEARCH_SDK.md`](RESEARCH_SDK.md) for the complete workflow and limitations.

## Experiment schema

Common fields:

```json
{
  "kind": "prediction",
  "title": "Entropy warning signal",
  "rationale": "Test incremental predictive information.",
  "hypotheses": ["H1"],
  "landscapes": ["rastrigin", "ackley"],
  "n_seeds": 12,
  "feature_sets": ["fitness", "fitness+entropy"],
  "controllers": null
}
```

Control experiments set `kind` to `control`, provide `controllers`, and set
`feature_sets` to null. The authoritative Pydantic model and preregistration
perform semantic validation; the transport contract intentionally does not
duplicate those evolving scientific constraints.

## Invariants

- Every mutating call has an `actor` fixed when the client/bridge starts.
- Clients cannot set posterior values, verdicts, costs, or measured results.
- Raw artifacts remain immutable and are addressed by experiment id.
- Selection requires the latest scoring round and a feasible candidate.
- Analysis requires a completed experiment.
- SDK execution fails closed on held-out experiments unless the caller passes
  `confirm_heldout: true` after obtaining and recording human approval.
- Protocol clients must not retry a mutating call after an unknown transport
  failure without first reading `state`/`events` to determine whether it landed.
- Generic evidence outputs must be declared before execution and emitted only
  once. Finalization fails if a declared schema or primary metric is missing.
- Artifact paths are run-local and content-verified with SHA-256.
- Evaluation and wall-time bounds are cooperative: callers must use
  `research.consume` and the Python runtime's budget checks.
- Evidence decisions are terminal; repeating an identical decision with
  identical text is an idempotent no-op, so a client may retry it after an
  unknown transport failure. Other mutating calls must not be retried blindly:
  read `research.inspect` first.
- Event logs are hash-chained and validated; runs, checkpoints and bundles are
  tamper-evident, not signed.

## Compatibility and parity

The Python implementation is authoritative. Two frozen fixture files define
cross-language parity:

- [`parity-fixtures.json`](../sdk/protocol/v1/parity-fixtures.json):
  numerical outputs (entropy, CVaR, Wilson, AUROC, decision mathematics).
  Rust and Julia helpers must match within its declared tolerance before their
  outputs may enter a scientific record.
- [`contract-fixtures.json`](../sdk/protocol/v1/contract-fixtures.json),
  generated by `generate_contract_fixtures.py` from the Python dataclasses:
  the method list, one canonical `ExperimentSpecV2`, and 21 invalid variants.
  Python, Rust and Julia must each round-trip the canonical spec exactly, build
  it identically with their builders, and reject every invalid variant. A
  Python test fails if the file is not regenerated after a contract change.

New methods and optional fields may be added compatibly within protocol `1.0`
(clients can feature-detect with `describe`); removing or changing existing
semantics requires a new protocol version.

The language clients also run live bridge tests against a temporary Python lab.
They cover laboratory initialization, proposal, scoring, selection,
state/event reads, scoped evidence runs, client-side failure, listing,
checkpoint and resume from a second bridge process, terminal decisions,
bundle export and verification, bundle-name confinement, and recovery from a
structured remote error.
