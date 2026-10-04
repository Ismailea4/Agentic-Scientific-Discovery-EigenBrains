# Research evidence SDK

## Immediate interoperability demonstration

The fastest way to verify the language boundary is to run this from the
repository root after installing all three toolchains:

```powershell
python -m sdk.interop.demo
```

The demonstration creates five linked evidence runs in one store:

1. Python produces seeded NumPy and JSONL artifacts plus reference metrics.
2. Rust consumes the hashed NumPy input and records native entropy.
3. Julia consumes the hashed prediction input and records AUROC with clustered
   uncertainty.
4. Python checks both independent computations against the references and
   accepts the result only within `1e-12`.
5. Python reproduces the source run and requires byte-identical artifacts.

All runs use protocol v1, retain structured provenance, validate independently,
and are exported into one verified content-addressed bundle. The command prints
every run ID, both parity differences, and the bundle hash. The procedure is
specified in [`sdk/interop/PROTOCOL.md`](../sdk/interop/PROTOCOL.md). It is an
engineering proof and deliberately makes no research or performance claim.

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
Julia additionally require their normal toolchains and **a Python environment
where `discolab` is importable**: both start the Python sidecar
(`python -m discolab.rpc`) themselves and talk to it over stdio. They are
clients, not independent runtimes.

```powershell
cargo run --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml --example evidence -- study
julia --project=.\sdk\julia .\sdk\julia\examples\evidence.jl study
```

| Capability | Python | Rust | Julia |
|---|---|---|---|
| Typed contracts validated before sending | dataclasses | builders + `validate()` | builders + `validate()` |
| Scoped run (finalize on success, record failure on error) | `with store.begin(spec) as run` | `with_research_run` | `with_research_run(...) do` |
| Checkpoint / resume | `run.checkpoint`, `definition.resume` | `checkpoint_research_run`, `with_resumed_research_run` | `checkpoint_research_run!`, `with_resumed_research_run` |
| List, inspect, validate, compare, accept, reject | direct | bridge | bridge |
| Bundles and lineage | direct | bridge (named bundles) | bridge (named bundles) |
| Automatic runner reproduction | yes | only for allow-listed Python runners | only for allow-listed Python runners |
| Controlled RNG | NumPy generator + named streams | caller RNG, recorded seed | caller RNG, recorded seed |
| Specialized math | authoritative statistics | telemetry kernels, `.npy` reader | decision theory, clustered AUROC |

All three languages accept the same canonical spec and reject the same invalid
variants; this is tested against
[`contract-fixtures.json`](../sdk/protocol/v1/contract-fixtures.json), which
is generated from the Python types.

## What a completed run guarantees

A validated run has:

- an immutable run identifier and an append-only, **hash-chained** event log
  (each event stores the SHA-256 of the previous line);
- an `ExperimentSpecV2` declaring capability, hypothesis, protocol,
  parameters, seed, resource budget, expected outputs, and primary metric;
- deterministic NumPy RNG plus stable named child streams;
- semantic schemas for tables and arrays, including units, roles, bounds, and
  censoring metadata;
- explicit `raw`, `derived`, or `analysis` artifact stages and parent lineage;
- SHA-256 hashes for every artifact, referenced input, protocol file when
  available, importable Python runner, the spec and provenance files, and the
  artifact/metric manifests;
- Git, Python, package, operating-system, CPU, and command provenance, with
  **portable paths** (relative to the working directory; anything outside it is
  reduced to its file name, so no local absolute path is published);
- machine-checkable completeness and integrity validation.

Validation catches missing declared outputs, malformed values, wrong array
shape/dtype, incompatible metric units, path escape, missing files, changed
artifact bytes, edited/removed/reordered events, edited spec or provenance,
and impossible lifecycle orders. This is tamper-*evident* metadata, not a
cryptographic signature: someone who can rewrite every file consistently is
outside the threat model. Publish a bundle's `content_sha256` separately (a
commit, a report) to pin it.

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
        [{"evaluation": i, "loss": float(loss)} for i, loss in enumerate(losses)],
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

Without the decorator, the context manager gives the same guarantees:

```python
with EvidenceStore("study").begin(spec) as run:
    ...                      # emit, metric, consume, checkpoint
print(run.report)            # written by finalize() on a clean exit
```

On a clean exit the run is finalized and validated. On any exception, or if
finalization itself fails (for example a declared output was never emitted),
`run_failed` is recorded with the error type and message and the exception
propagates. No hidden retry is performed.

The decorator records an importable `module:qualname`. `reproduce` imports that
same definition and reruns it with the recorded parameters, seed, budget, and
inputs, then reports for every artifact whether it reproduced byte-for-byte
(`identical_artifacts`). It refuses if an input, the protocol file, or the
runner source changed since the original run.

### RNG and budgets

`run.rng` is the main seeded NumPy generator. `run.child_rng("label")` derives a
stable independent stream from the run seed and label; call order does not
change it, and the same label returns the same generator object for the rest
of the run (a stream is never silently restarted). Use separate labels for
initialization, mutation, bootstrap, and other stochastic mechanisms.

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
artifact must identify at least one already-emitted parent. Rust reads float64
arrays with `eigenbrains_sdk::npy::read_f64`.

## Evidence lifecycle

```text
running --(checkpoint_written)--> running --> failed                (terminal)
   ^  |
   |  +--> raw_complete --> validated --> accepted_as_evidence      (terminal)
   |            |               |
   |            +---------------+-------> rejected_as_evidence      (terminal)
   +-- run_resumed (from the last checkpoint, after an interruption)
```

- `finalize()` writes the artifact and metric manifests and immediately
  validates the run.
- `accept(run_id, rationale)` requires a non-empty rationale and a run that
  validates.
- `reject(run_id, reason)` requires a non-empty reason. It is allowed for any
  finished run, including one that fails validation; the integrity result is
  recorded next to the reason so a rejection of corrupted evidence is
  auditable.
- Both decisions are **terminal**. Repeating the identical decision with the
  identical text is an idempotent no-op (`"idempotent": true`, nothing is
  appended), so a client may safely retry after a lost response. Any other
  second decision (accept after reject, a different reason) is refused with
  `EvidenceError`.
- Running and failed runs cannot be decided.

## Checkpoint and resume

```python
@experiment(...)
def long_search(run):
    state = run.restored_state or {"generation": 0, "population": initial()}
    rng = run.child_rng("mutation")
    for g in range(state["generation"], run.params["generations"]):
        state["population"] = step(state["population"], rng)
        state["generation"] = g + 1
        run.consume(run.params["population_size"])
        if g % 50 == 0:
            run.checkpoint(state)          # JSON-serialisable state only
    run.emit.table(...)
    run.metric(...)

long_search.resume("study", "RUN-...")     # or: eigenbrains-sdk --root study resume RUN-...
```

A checkpoint stores the evaluation count, the active elapsed time, the main and
all named RNG bit-generator states, the names of evidence emitted so far, and
the experiment's own JSON `state`. It is written once, exclusively, and its
SHA-256 is recorded in the event log. Resuming restores all of it, so a run
interrupted after a checkpoint and resumed produces the same artifacts as an
uninterrupted run (tested byte-for-byte).

Resume is refused, failing closed, when the run:

- is finished, failed, accepted or rejected;
- has no checkpoint;
- is corrupted (event chain, spec/provenance, artifact, or checkpoint hash);
- is resumed with a spec whose canonical hash differs from the recorded one;
- depends on an input, protocol file, or runner source that changed;
- recorded artifacts or metrics after its last checkpoint (the resumed code
  would orphan or duplicate them — checkpoint right after emitting).

Limits, stated plainly:

- The experiment must checkpoint its own loop state; the SDK cannot capture
  arbitrary Python objects, open files, or native library state.
- Only NumPy generators obtained from the run (`run.rng`, `run.child_rng`) are
  restored. Other RNGs must be saved in `state`.
- Elapsed time counts active execution only; downtime between the crash and the
  resume is not charged to the wall budget.
- The SDK does not detect a still-running original process. Resume only when
  the first process is known to be gone; two concurrent writers to one run are
  unsupported.
- Bridge clients (Rust/Julia) resume with `research.resume`; it restores the
  Python context and returns the saved state, but executes no code.

## Listing, inspecting, comparing

```python
store = EvidenceStore("study")
store.list(capability="optimization", status="validated", seed=7,
           created_after="2026-10-04T00:00:00Z")
store.inspect(run_id); store.validate(run_id)
store.compare(left, right)     # metric deltas (units must match) + artifact byte identity
store.lineage()                # parent edges inside runs, input-hash edges across runs
```

Time bounds are inclusive and accept ISO-8601 strings (naive means UTC),
datetimes, or unix nanoseconds. Listed times are truncated to microseconds, so a
listed `created_at` used as a lower bound still selects that run. Comparison
reports the signed and relative change without claiming which direction is
scientifically preferable. Lineage connects an input of one run to the run
that produced a byte-identical artifact; unmatched inputs are listed as
external.

## Bundles

```python
from discolab import export_bundle, verify_bundle

manifest = export_bundle("study", [run_a, run_b], "evidence.zip")
verify_bundle("evidence.zip")          # raises ValidationError on any problem
```

A bundle contains each run directory unchanged plus `bundle.json`, which lists
every file with its SHA-256 and size. The bundle's identity,
`content_sha256`, is the hash of that canonical file list, so the same runs
always give the same identity; archives are written deterministically (sorted
members, fixed timestamps). Only validated or decided runs can be exported, and
they must validate (rejected runs are exported as they are, so the rejection
can be audited).

Verification fails closed on: a missing, extra, resized or altered file; a
manifest whose identity does not match its file list; unsafe archive members
(absolute paths, `..`, drive letters, links, duplicates); archives over the
size limits; a corrupted archive; a run whose status differs from the manifest;
and any run that does not validate inside the bundle.

## Command line

```powershell
eigenbrains-sdk --root study list --status validated --since 2026-10-04T00:00:00Z
eigenbrains-sdk --root study inspect RUN-ABC123
eigenbrains-sdk --root study validate RUN-ABC123
eigenbrains-sdk --root study compare RUN-ABC123 RUN-DEF456
eigenbrains-sdk --root study accept RUN-ABC123 --rationale "registered checks passed"
eigenbrains-sdk --root study reject RUN-DEF456 --reason "pilot, not part of the protocol"
eigenbrains-sdk --root study reproduce RUN-ABC123
eigenbrains-sdk --root study resume RUN-ABC123
eigenbrains-sdk --root study lineage
eigenbrains-sdk --root study export RUN-ABC123 RUN-DEF456 --out evidence.zip
eigenbrains-sdk verify-bundle evidence.zip
```

Results are JSON on stdout with exit code 0. A failure is one JSON line on
stderr, `{"ok": false, "error": {"code", "message"}, "exit_code"}`, without a
traceback:

| Exit code | Meaning |
|---|---|
| 2 | invalid usage or value |
| 3 | validation or integrity failure |
| 4 | unknown run, input, or bundle |
| 5 | refused lifecycle transition |
| 6 | budget exceeded |
| 7 | refused by policy |
| 1 | anything else |

## Rust client

```rust
use eigenbrains_sdk::{
    ArtifactEmission, ArtifactSchema, BridgeConfig, FieldSchema, MetricSpec,
    ResearchExperimentSpec,
};

let spec = ResearchExperimentSpec::builder("optimization", "hypothesis", "protocols/v1.yaml")
    .seed(2026)
    .output(ArtifactSchema::table("trajectory", 1)
        .field(FieldSchema::integer("evaluation").unit("count").minimum(0.0))
        .field(FieldSchema::number("loss").unit("objective")))
    .primary_metric(MetricSpec::new("recovery_time", "evaluations").primary())
    .max_evaluations(10_000)
    .build()?;                                   // SdkError::Invalid before anything is sent

let mut client = BridgeConfig::new("study").actor("rust-researcher").spawn()?;
let (_, report) = client.with_research_run(&spec, |run| {
    run.consume(10)?;
    run.emit(&ArtifactEmission::table("trajectory", "trajectory.v1", rows))?;
    run.metric("recovery_time", 10.0)
})?;                                             // failure is recorded, then returned
```

`SdkError` distinguishes transport (`Io`, `Json`, `Protocol`), local contract
(`Invalid`), and remote (`Remote { code, message }`) failures. A panic inside
the closure is not caught; the run stays `running` and can be inspected or
resumed from its last checkpoint.

## Julia client

```julia
using EigenBrainsSDK

spec = research_spec("optimization", "hypothesis", "protocols/v1.yaml";
    seed=2026,
    outputs=[table_schema("trajectory", [field_schema("loss", "number"; unit="objective")])],
    primary_metric=metric_spec("recovery_time", "evaluations"; role="primary"))

client = open_client("study"; python="python", actor="julia-researcher")
value, report = with_research_run(client, spec) do run_id
    emit_research_artifact!(client, run_id, "trajectory", "table", rows, "trajectory.v1")
    record_research_metric!(client, run_id, "recovery_time", 10.0)
end
close(client)
```

Invalid contracts raise `ContractError` locally; remote failures raise
`ProtocolError(code, message)`. The package also provides decision-theory
helpers and `auroc`, `clustered_auroc`, `paired_clustered_auroc` (Obuchowski
1997 clustered variance; reduces to DeLong et al. 1988 for one observation per
cluster), all checked against Python parity fixtures where Python has an
equivalent.

## Directory contract

```text
study/research-runs/RUN-.../
  spec.json
  provenance.json
  events.jsonl          hash-chained
  artifacts.json        written at finalize
  metrics.json          written at finalize
  checkpoints/ckpt-000001.json ...
  artifacts/
    raw/
    derived/
    analysis/
study/bundles/<name>.zip   (bridge exports)
```

Run files are created exclusively and artifact names cannot be reused inside a
run. Keep the whole run directory together when archiving it, or export a
bundle.

## Current boundaries

- Rust and Julia are typed local clients; a Python sidecar remains required.
- Wall-time and evaluation limits are cooperative, not process-level quotas.
- GPU identity is explicitly recorded as unavailable until a portable detector
  is added.
- Manifests are hash-chained and content-addressed, not signed.
- One writer per run; concurrent writers and still-alive original processes
  are not detected.
- JSONL and `.npy` favor zero extra dependencies; columnar Parquet/Zarr
  backends can be added later behind new artifact kinds.
- Automatic reproduction is limited to importable Python experiment
  definitions, and over the bridge to modules explicitly allow-listed when the
  bridge starts. Bridge-originated runs remain fully inspectable and
  validatable.
- Runs written before the event chain existed do not validate under this
  version (their events carry no `prev_sha256`).

These boundaries are intentional and visible in provenance rather than hidden
behind claims the runtime cannot currently support.
