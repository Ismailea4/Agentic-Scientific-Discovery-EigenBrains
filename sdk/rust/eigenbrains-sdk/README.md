# EigenBrains Rust SDK

The Rust crate provides:

- a persistent typed client for `python -m discolab.rpc`;
- native normalized-entropy, CVaR, and Wilson-interval kernels;
- parity tests against authoritative Python outputs.

```bash
cargo test
cargo run --example telemetry --release
```

The telemetry example is a local timing harness, not a published benchmark.
Rust is not installed on the current development machine, so this initial crate
has not yet been compiled here.
