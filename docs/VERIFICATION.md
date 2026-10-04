# Verification and reproduction

The repository provides one offline PowerShell entry point for evidence
integrity, deterministic reproduction, and implementation tests:

```powershell
.\scripts\verify.ps1
```

Run it from the repository root. It never reads credential values and never
contacts a model provider.

## What the default command verifies

1. The published selective-model policy values are derived again from
   `benchmark/artifacts/baseline_v0/baseline_v0_summary.json`:
   - held-out observed quality `0.750` for Qwen-only, always-both, and selective
     Qwen-to-GPT-OSS routing;
   - `16.0%` estimated cost reduction and `35.2%` latency reduction versus
     always-both;
   - provider-backed S3 confirmation with zero rescues and zero damages.
2. The research-acceleration claims are derived again from
   `discolab/results/escalation/summary.json`:
   - five replicates and 35 hypothesis-replicates;
   - mean compute ratio `1.542` with every replicate above one;
   - `28/35` selective and `29/35` full-size reference agreement;
   - five rescues and zero damages.
3. A fresh Python SDK evidence run is executed with a root seed and named RNG
   stream, validated, reproduced under a second run ID, and compared for
   byte-identical artifacts.
4. The two runs are exported to a deterministic content-addressed bundle and
   verified. A deliberately corrupted temporary copy must fail verification.
5. Backend and discovery-lab Python tests run with workspace-local temporary
   directories and single-threaded numerical libraries.
6. Frontend type checking/build, Rust formatting/Clippy/tests, and Julia tests
   run when the full profile is selected.

The command exits nonzero when any requested step fails and prints a compact
PASS/FAIL table. Temporary outputs are deleted only from the script-created
`.verification/<timestamp>/` directory after its resolved path is checked.

## Profiles

Full offline verification:

```powershell
.\scripts\verify.ps1
```

Python/control-plane verification when Node, Rust, or Julia is unavailable:

```powershell
.\scripts\verify.ps1 -CoreOnly
```

Fast claim-integrity check without test suites or SDK reproduction:

```powershell
.\scripts\verify.ps1 -ClaimsOnly
```

Install declared Python and frontend dependencies before verification:

```powershell
.\scripts\verify.ps1 -Install
```

Dependency installation is explicit because it can download packages and
modify local environments. Rust and Julia dependencies remain owned by their
toolchains.

## Full acceleration reproduction

The committed acceleration bundle excludes approximately 125 MB of raw traces;
the frozen harness regenerates them from seeds. To rerun all five replicates
and compare the regenerated summary with the recorded one:

```powershell
.\scripts\verify.ps1 -CoreOnly -ReproduceAcceleration -KeepArtifacts
```

This is CPU-intensive but performs no provider calls. Output is written beneath
`.verification/<timestamp>/acceleration-reproduction/`. With `-KeepArtifacts`
the directory remains for inspection; without it, the verified temporary tree
is removed at the end.

The reproduction must match:

- the frozen protocol object;
- per-replicate compute ratios within numerical tolerance;
- all strategy/reference agreement arrays;
- gate rate, rescue, damage, and denominator economics.

Do not point the harness at `discolab/results/escalation/`: the experimental
runner refuses to overwrite an existing evidence directory.

## Interpreting a successful verification

A passing command establishes that the checked implementation and evidence
artifacts are internally consistent and reproducible under the current
environment. It does not establish:

- generalization to unseen scientific domains;
- statistical equivalence between 28/35 and 29/35 agreement;
- stable future provider behavior;
- validity of assumptions not tested by the frozen protocols.

Those boundaries are part of the result, not exceptions to verification.
