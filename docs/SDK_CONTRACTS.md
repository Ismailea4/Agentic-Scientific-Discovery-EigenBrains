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

## Compatibility and parity

The Python implementation is authoritative. Rust and Julia numerical helpers
must pass [`parity-fixtures.json`](../sdk/protocol/v1/parity-fixtures.json)
within its declared tolerance before their outputs may enter a scientific
ledger. New fields may be added compatibly; removing or changing existing
semantics requires a new protocol version.

The language clients also run live bridge tests against a temporary Python lab.
Those tests cover initialization, proposal, deterministic scoring, selection,
state/event reads, and recovery from a structured remote error.
