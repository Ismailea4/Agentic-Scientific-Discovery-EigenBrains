# Interoperability demonstration protocol

This is a deterministic engineering demonstration, not a scientific result.
Its purpose is to prove that Python, Rust, and Julia can participate in one
validated evidence lifecycle without copying results between independent
stores.

## Frozen procedure

1. Python creates a seeded `32 x 4` population and a labelled prediction table.
2. Python records normalized population entropy and AUROC as reference values.
3. Rust reads the hashed NumPy population artifact, recomputes entropy with its
   native kernel, and records a new evidence run in the same store.
4. Julia reads the hashed prediction artifact, recomputes AUROC and a clustered
   interval, and records a new evidence run in the same store.
5. Python consumes the Rust and Julia artifacts, fails closed unless both
   reference differences are at most `1e-12`, and records the parity verdict.
6. The Python source run is reproduced byte-for-byte.
7. All runs are validated and exported as one content-addressed evidence
   bundle, which is independently verified before the demonstration passes.

The population seed is `2026`, bounds are `[-5, 5]`, and the entropy histogram
uses eight bins. The prediction fixture contains six two-observation clusters,
each with one positive and one negative outcome.

## Acceptance rule

The demonstration passes only when:

- Rust and Python entropy differ by at most `1e-12`;
- Julia and Python AUROC differ by at most `1e-12`;
- the reproduced Python artifacts are byte-identical;
- every evidence run validates;
- bundle verification returns the same content identity as bundle export.

Toolchain startup and compilation time are excluded from scientific metrics.
No performance claim is made by this demonstration.
