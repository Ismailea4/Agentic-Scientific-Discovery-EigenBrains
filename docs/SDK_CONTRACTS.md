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
id/version mismatches and successful envelopes that omit `result`.

## Methods

| Method | Required parameters | Mutation |
|---|---|---|
| `initialize` | none | creates the first ledger event |
| `state` | none | no |
| `events` | none | no |
| `propose` | `experiment` | appends a validated candidate |
| `score` | none | appends a deterministic scoring round |
| `select` | `experiment_id`, `justification` | selects a feasible scored experiment |
| `run` | optional `confirm_heldout` (default false) | runs the selected experiment and records artifacts/results |
| `abort` | `experiment_id`, `reason` | records an interrupted run as failed |
| `result` | `experiment_id` | no |
| `analyze` | `experiment_id`, `interpretation`; optional `threats_to_validity` | records analysis and deterministic belief updates |
| `decide` | `decision`, `rationale`; optional `next_experiment` | records the next scientific decision |
| `register_hypothesis` | hypothesis schema | appends a testable agent-generated hypothesis |
| `research.begin` | `spec` (`ExperimentSpecV2`) | creates a generic evidence run |
| `research.emit` | `run_id`, `name`, `kind`, `value`, `schema`; optional `stage`, `parents` | validates and writes one semantic artifact |
| `research.metric` | `run_id`, `name`, `value`; optional metric `spec` | records one unit-bearing metric |
| `research.consume` | `run_id`; optional `evaluations` | accounts work and enforces cooperative budgets |
| `research.finalize` | `run_id` | closes, checks completeness, and validates a run |
| `research.inspect` | `run_id` | no |
| `research.validate` | `run_id` | verifies hashes and schemas; records validation once |
| `research.compare` | `left`, `right` | no |
| `research.accept` | `run_id`, `rationale` | marks validated output accepted as evidence |
| `research.reproduce` | `run_id` | reruns an importable Python experiment definition |

The `research.*` calls are stateful within one bridge process between `begin`
and `finalize`. If the bridge exits, unfinished contexts are deliberately not
resumed. Completed runs remain inspectable from any later process.

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

## Compatibility and parity

The Python implementation is authoritative. Rust and Julia numerical helpers
must pass [`parity-fixtures.json`](../sdk/protocol/v1/parity-fixtures.json)
within its declared tolerance before their outputs may enter a scientific
ledger. New fields may be added compatibly; removing or changing existing
semantics requires a new protocol version.

The language clients also run live bridge tests against a temporary Python lab.
Those tests cover initialization, proposal, deterministic scoring, selection,
state/event reads, a schema-validated generic evidence run, and recovery from a
structured remote error.
