# EigenBrains Rust SDK

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
