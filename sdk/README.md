# EigenBrains SDK

The SDK exposes the same validated research transitions used by the Omnigent
agents. It is intentionally not a second implementation of the laboratory.

## Architecture

```text
Python SDK (authoritative orchestration and statistics)
             |
             +-- JSONL protocol v1 over stdio
                    |-- Rust client + native telemetry kernels
                    `-- Julia client + theoretical decision-math helpers
```

Every mutation still passes through the append-only ledger and its transition
guards. The protocol never accepts arbitrary Python code or shell commands.

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
See [`protocol/v1/schema.json`](protocol/v1/schema.json). Rust and Julia clients
Both clients expose all protocol-v1 lifecycle methods and retain the remote
error code and message so callers can distinguish validation, transition, and
transport failures.

## Language responsibilities

- **Python** owns AI orchestration, experiment lifecycle, artifacts, and the
  authoritative statistical implementation.
- **Rust** is the performance path for high-volume telemetry and simulation
  kernels. It also provides a typed bridge client.
- **Julia** is the mathematical-research path for priors, posterior updates,
  information gain, and future symbolic/numerical extensions.

[`protocol/v1/parity-fixtures.json`](protocol/v1/parity-fixtures.json) freezes
authoritative Python outputs for Rust/Julia numerical-parity tests. Performance
benchmarks are the next engineering step. No speed claim should be published
until the Rust kernels are benchmarked on the same inputs and machine.

## Verification

```bash
cd discolab
python -m pytest -q
cd ..
cargo test --manifest-path sdk/rust/eigenbrains-sdk/Cargo.toml
julia --project=sdk/julia -e 'using Pkg; Pkg.instantiate(); Pkg.test()'
```

The Rust and Julia suites each start a real Python bridge in a temporary lab,
exercise validated lifecycle transitions, and confirm that a rejected method
returns a structured error without terminating the persistent session.
