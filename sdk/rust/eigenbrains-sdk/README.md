# EigenBrains Rust SDK

A typed client for the versioned local Python bridge plus native numerical
kernels. **A Python sidecar is required**: the client starts
`python -m discolab.rpc` (configure with `BridgeConfig`: `python`, `actor`,
`python_path`, `allow_runner_module`), so `discolab` must be importable.

The crate provides:

- validated contract builders (`ResearchExperimentSpec::builder`,
  `ArtifactSchema::table/array/json`, `FieldSchema::number/...`,
  `MetricSpec::new`) mirroring the Python rules, with `to_json`/`from_json`;
- `with_research_run` / `with_resumed_research_run`, which finalize on success
  and record `research.fail` on any error;
- a client method for every protocol-v1 method (`METHODS`), including
  checkpoint, resume, listing (`RunFilter`), terminal decisions, lineage and
  bundles; remote errors keep their Python code and message
  (`SdkError::Remote`), local contract errors are `SdkError::Invalid`;
- kernels: normalized population entropy (following the Python telemetry
  operation by operation, including NumPy's pairwise summation), batch
  entropy, CVaR, Wilson interval, quantiles;
- `npy::read_f64` for the float64 C-order arrays the runtime emits.

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
cargo run --example evidence -- study
cargo run --release --example interop_audit -- <root> <population.npy> <reference.json> <protocol> <discolab-source>
```

Tests check method and contract parity against `sdk/protocol/v1`, reject every
invalid fixture spec, and run a live bridge covering scoped runs, failures,
listing, checkpoint/resume across bridge processes, decisions and bundles.
The `telemetry` example is a local timing harness, not a published benchmark.
Validated on Windows with Rust 1.99.0.

For the complete Python -> Rust -> Julia demonstration, run
`python -m sdk.interop.demo` from the repository root. The driver supplies the
hashed Python artifacts to this crate's `interop_audit` example and records the
native result in the same evidence store.
