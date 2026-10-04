# Research evidence SDK

The SDK turns a computational experiment into a self-describing evidence run.
It is designed for the point where an idea becomes data: the hypothesis,
protocol, parameters, seed, resource bounds, outputs, metrics, environment, and
lineage travel together. Python is the authoritative runtime. Rust and Julia
use typed clients over the same versioned local protocol.

## Install from this checkout

```powershell
python -m pip install -e .\discolab
```

Python can then run `python .\sdk\examples\research_evidence.py`. Rust and
Julia additionally require their normal toolchains; both launch the installed
Python sidecar themselves:

```powershell
cargo run --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml --example evidence -- study
julia --project=.\sdk\julia .\sdk\julia\examples\evidence.jl study
```

| Capability | Python | Rust | Julia |
|---|---|---|---|
| Define typed experiment/schema contracts | native dataclasses | native structs | native structs |
| Emit/validate/inspect/compare evidence | direct | local bridge | local bridge |
| Automatic runner reproduction | yes | inspect/request only | inspect/request only |
| Controlled RNG | NumPy generator + named streams | caller RNG, recorded seed | caller RNG, recorded seed |
| Specialized math | authoritative statistics | telemetry/performance kernels | decision-theory helpers |

## What a completed run guarantees

A validated run has:

- an immutable run identifier and append-only lifecycle events;
- an `ExperimentSpecV2` declaring capability, hypothesis, protocol,
  parameters, seed, resource budget, expected outputs, and primary metric;
- deterministic NumPy RNG plus stable named child streams;
- semantic schemas for tables and arrays, including units, roles, bounds, and
  censoring metadata;
- explicit `raw`, `derived`, or `analysis` artifact stages and parent lineage;
- SHA-256 hashes for every artifact, referenced input, protocol file when
  available, and importable Python runner;
- Git, Python, package, operating-system, CPU, and command provenance;
- machine-checkable completeness and integrity validation.

Validation catches missing declared outputs, malformed values, wrong array
shape/dtype, incompatible metric units, path escape, missing files, and changed
artifact bytes. This is tamper-evident metadata, not a cryptographic signature:
an attacker who can rewrite both an artifact and its manifest is outside the
current threat model.

## Python: one reproducible experiment

```python
from discolab import (
    ArtifactSchema, FieldSchema, MetricSpec, ResourceBudget, experiment,
)

trajectory = ArtifactSchema(
    name="trajectory",
    version=1,
    kind="table",
    fields=(
        FieldSchema("evaluation", "integer", unit="count", role="index", minimum=0),
        FieldSchema("loss", "number", unit="objective", role="observation"),
    ),
)
recovery = MetricSpec(
    "recovery_time", unit="evaluations", role="primary",
    minimum=0, censoring="right",
)

@experiment(
    capability="optimization",
    hypothesis="The controller recovers after a landscape shift.",
    protocol="protocols/recovery-v1.md",
    outputs=(trajectory,),
    primary_metric=recovery,
)
def recovery_experiment(run):
    rng = run.child_rng("optimizer")
    losses = rng.uniform(size=10)
    run.consume(evaluations=len(losses))
    run.emit.table(
        "trajectory",
        [
            {"evaluation": i, "loss": float(loss)}
            for i, loss in enumerate(losses)
        ],
        schema=trajectory.id,
    )
    run.metric("recovery_time", 10)

report = recovery_experiment.run(
    "study",
    parameters={"population": 64},
    seed=2026,
    budget=ResourceBudget(max_evaluations=10, max_seconds=30),
)
print(report["run_id"])
```

The decorator records an importable `module:qualname`. `reproduce` imports that
same definition and reruns it with the recorded parameters, seed, budget, and
inputs. Ad-hoc bridge runs can still be recorded from Rust or Julia, but are not
automatically reproducible unless they name an importable Python runner.

### RNG and budgets

`run.rng` is the main seeded NumPy generator. `run.child_rng("label")` derives a
stable independent stream from the run seed and label; call order does not
change it. Use separate labels for initialization, mutation, bootstrap, and
other stochastic mechanisms.

`run.consume(n)` accounts for evaluations and checks both evaluation and wall
budgets. `run.check_budget()` checks wall time without consuming evaluations.
Budgets are cooperative: the SDK fails the next accounting/check call; it does
not forcibly interrupt native or external code.

### Artifact formats

| Kind | Stored format | Intended use |
|---|---|---|
| `table` | canonical JSON Lines | records with named semantic fields |
| `array` | NumPy `.npy`, pickle disabled | dense numerical tensors |
| `json` | canonical JSON | structured reports and model state |

Tables validate each field's primitive type, nullability, range, and extra
field policy. Arrays validate declared NumPy dtype and rank. Every artifact
must use an output schema declared before execution. A derived or analysis
artifact must identify at least one already-emitted parent.

## Evidence lifecycle

```text
running --> failed
   |
   v
raw_complete --> validated --> accepted_as_evidence
```

`finalize()` writes the artifact and metric manifests and immediately validates
the run. Acceptance is a separate deliberate act with a non-empty rationale.
Failure records the exception class, message, elapsed time, and consumed
evaluations. No hidden retry is performed.

## Inspect, validate, compare, reproduce

After installing the Python package:

```powershell
eigenbrains-sdk --root study inspect RUN-ABC123
eigenbrains-sdk --root study validate RUN-ABC123
eigenbrains-sdk --root study compare RUN-ABC123 RUN-DEF456
eigenbrains-sdk --root study accept RUN-ABC123 --rationale "registered checks passed"
eigenbrains-sdk --root study reproduce RUN-ABC123
```

The equivalent Python API is `EvidenceStore(root).inspect/validate/compare/
accept/reproduce`. Comparison reports common metrics only, rejects incompatible
units, and returns the signed and relative change without claiming which
direction is scientifically preferable.

## Rust client

Rust owns performance-sensitive kernels and uses typed contracts for evidence
runs. The local Python environment must have `discolab` installed.

```rust
use eigenbrains_sdk::{ArtifactEmission, Bridge, ResearchExperimentSpec};

let mut client = Bridge::spawn("python", "study", "rust-researcher")?;
let opened = client.begin_research_run(&spec)?; // typed ResearchExperimentSpec
let run_id = opened["run_id"].as_str().unwrap();
client.consume_research_budget(run_id, evaluations)?;
client.emit_research_artifact(
    run_id,
    &ArtifactEmission {
        name: "trajectory".into(), kind: "table".into(), value: rows,
        schema: "trajectory.v1".into(), stage: "raw".into(), parents: vec![],
    },
)?;
client.record_research_metric(run_id, "recovery_time", 10.0, None)?;
client.finalize_research_run(run_id)?;
```

`ResourceBudget`, `FieldSchema`, `ArtifactSchema`, `MetricSpec`, and
`ResearchExperimentSpec` are native Rust structs. Transport and remote
validation failures remain distinct through `SdkError`.

## Julia client

Julia owns mathematical exploration and exposes the same typed evidence
contracts:

```julia
using EigenBrainsSDK

client = open_client("study"; python="python", actor="julia-researcher")
opened = begin_research_run!(client, spec) # typed ResearchExperimentSpec
run_id = opened["run_id"]
consume_research_budget!(client, run_id, evaluations)
emit_research_artifact!(
    client, run_id, "trajectory", "table", rows, "trajectory.v1",
)
record_research_metric!(client, run_id, "recovery_time", 10.0)
finalize_research_run!(client, run_id)
close(client)
```

The Julia package also provides decision-theory helpers verified against frozen
Python parity fixtures. `ProtocolError` preserves the server error code and
message.

## Directory contract

```text
study/research-runs/RUN-.../
  spec.json
  provenance.json
  events.jsonl
  artifacts.json
  metrics.json
  artifacts/
    raw/
    derived/
    analysis/
```

Run files are created exclusively and artifact names cannot be reused inside a
run. Keep the whole run directory together when archiving it.

## Current boundaries

- Rust and Julia are typed local clients; a Python sidecar remains required.
- Wall-time and evaluation limits are cooperative, not process-level quotas.
- GPU identity is explicitly recorded as unavailable until a portable detector
  is added.
- Checkpoint/resume and signed manifests are not implemented yet.
- JSONL and `.npy` favor zero extra dependencies; columnar Parquet/Zarr
  backends can be added later behind new artifact kinds.
- Automatic reproduction is limited to importable Python experiment
  definitions. Bridge-originated runs remain fully inspectable and validatable.

These boundaries are intentional and visible in provenance rather than hidden
behind claims the runtime cannot currently support.
