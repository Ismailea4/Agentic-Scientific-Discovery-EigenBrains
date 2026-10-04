# EigenBrains Rust SDK

This crate combines a persistent client for the versioned local Python bridge
with native numerical kernels. Generic evidence runs use typed
`ResourceBudget`, `FieldSchema`, `ArtifactSchema`, `MetricSpec`, and
`ResearchExperimentSpec` structs, followed by `begin_research_run`, semantic
artifact/metric calls, budget accounting, and final validation.

The Python package remains the authoritative evidence runtime. Remote
validation errors are returned as `SdkError::Remote` rather than flattened into
transport failures. The full workflow and current limitations are documented
in [`../../../docs/RESEARCH_SDK.md`](../../../docs/RESEARCH_SDK.md).

The Rust crate provides:

- a persistent client covering every protocol-v1 lifecycle method;
- structured remote errors that retain both the Python error code and message;
- native normalized-entropy, CVaR, and Wilson-interval kernels;
- an end-to-end Python bridge test plus native numerical tests.

```bash
cargo test
cargo run --example telemetry --release
```

The telemetry example is a local timing harness, not a published benchmark.
The crate is validated on Windows with Rust 1.99.0. The bridge test starts the
authoritative Python RPC process from the source checkout, exercises validated
proposal/scoring/selection transitions, and verifies structured error recovery.
