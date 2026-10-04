# EigenBrains SDK

The SDK exposes the same validated research transitions used by the Omnigent
agents. It is intentionally not a second implementation of the laboratory.

It also provides a domain-independent evidence runtime for computational
research: declared contracts, controlled RNG and budgets, hash-chained run
logs, checkpoint/resume, terminal accept/reject decisions, lineage, and
content-addressed bundles. The full guide is
[`docs/RESEARCH_SDK.md`](../docs/RESEARCH_SDK.md); the wire contract is
[`docs/SDK_CONTRACTS.md`](../docs/SDK_CONTRACTS.md).

## Architecture

```text
Python SDK (authoritative orchestration, evidence runtime and statistics)
             |
             +-- JSONL protocol v1 over stdio (python -m discolab.rpc)
                    |-- Rust client + native telemetry kernels + .npy reader
                    `-- Julia client + decision mathematics + clustered ROC statistics
```

**Rust and Julia require the Python sidecar.** Each client starts
`python -m discolab.rpc` itself, so the selected Python must be able to import
`discolab` (installed with `pip install -e discolab`, or via `PYTHONPATH`
pointing at the `discolab` directory of a checkout).

Domain-specific mutations pass through the laboratory ledger and its transition
guards. Generic evidence runs use their own append-only, hash-chained
lifecycle log, declared schemas, content hashes, and provenance manifest. The
protocol never accepts Python code or shell commands; a run may name an
importable Python runner only when the bridge is started with
`--allow-runner-module`.

## One-command interoperability proof

With Python/discolab, Cargo, and Julia installed, run from the repository root:

```powershell
python -m sdk.interop.demo
```

This is an executable proof, not a diagram. Python writes seeded NumPy and
JSONL evidence; Rust independently reads the NumPy artifact and recomputes
entropy with its native kernel; Julia independently reads the prediction table
and recomputes AUROC plus clustered uncertainty. All three write protocol-v1
runs into the same append-only evidence store. Python then checks `1e-12`
parity, reproduces the source artifacts byte-for-byte, accepts the combined
result, and verifies one content-addressed bundle.

The terminal prints one run ID per language, both numerical differences, the
bundle identity, and the evidence root. Inspect `interop-summary.json` and the
`research-runs/` directory underneath that root. Use explicit tool locations
when they are not yet on `PATH`:

```powershell
python -m sdk.interop.demo `
  --cargo <path-to-cargo.exe> `
  --julia <path-to-julia.exe>
```

The procedure is frozen in
[`interop/PROTOCOL.md`](interop/PROTOCOL.md). It makes no provider calls and no
scientific or speed claim.

## Python

```python
from discolab import DiscoveryLab, Experiment

lab = DiscoveryLab("lab_home/sdk-demo", actor="example")
lab.initialize()
experiment = Experiment.prediction(
    title="Entropy warning signal",
    rationale="Test incremental predictive information.",
    hypotheses=["H1"],
    landscapes=["rastrigin", "ackley"],
    n_seeds=12,
    feature_sets=["fitness", "fitness+entropy"],
)
experiment_id = lab.propose(experiment)["id"]
scores = lab.score()
lab.select(experiment_id, "highest feasible expected information gain")
result = lab.run()
```

## Cross-language bridge

```bash
python -m discolab.rpc --root lab_home/sdk-demo --actor external-sdk
```

The process accepts one JSON request per line and emits one response per line.
See [`protocol/v1/schema.json`](protocol/v1/schema.json), whose `x-methods`
table lists each method's required and optional parameters. Both the Rust and
Julia clients implement every protocol-v1 method, validate contracts locally,
offer scoped runs that finalize on success and record failures, and retain the
remote error code and message so callers can distinguish validation,
transition, and transport failures.

## Language responsibilities

- **Python** owns AI orchestration, experiment lifecycle, artifacts, and the
  authoritative statistical implementation.
- **Rust** is the performance path for high-volume telemetry kernels (entropy
  that follows the Python computation operation by operation, CVaR, Wilson)
  and reads the runtime's float64 `.npy` artifacts.
- **Julia** is the mathematical-research path: priors, posterior updates,
  information gain, and clustered ROC inference (Obuchowski 1997).

Two fixture files freeze cross-language behaviour:
[`parity-fixtures.json`](protocol/v1/parity-fixtures.json) (numerical outputs)
and [`contract-fixtures.json`](protocol/v1/contract-fixtures.json) (method
list, canonical spec, invalid specs; regenerate with
`generate_contract_fixtures.py`). No speed claim should be published without
repeated measurements on the same inputs and machine; the
`research_prototypes/entropy_early_warning` study shows how one is recorded.

## Verification

```bash
cd discolab
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python -m pytest -q
cd ..
cargo fmt --manifest-path sdk/rust/eigenbrains-sdk/Cargo.toml --check
cargo clippy --manifest-path sdk/rust/eigenbrains-sdk/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path sdk/rust/eigenbrains-sdk/Cargo.toml
julia --project=sdk/julia sdk/julia/test/runtests.jl
```

The Rust and Julia suites set `PYTHONPATH` to the checkout's `discolab`
directory and use `$PYTHON` (default `python`) to start real bridges in
temporary labs.
