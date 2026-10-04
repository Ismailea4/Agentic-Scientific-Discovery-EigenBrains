# EigenBrains Julia SDK

A protocol-v1 client with structured remote errors, validated evidence
contracts, and mathematical primitives. **A Python sidecar is required**:
`open_client` starts `python -m discolab.rpc` (keywords `python`, `actor`,
`allowed_runner_modules`), so `discolab` must be importable by that Python.

- Contracts: `ResourceBudget`, `FieldSchema`, `ArtifactSchema`, `MetricSpec`,
  `ResearchExperimentSpec`, with `validate`, builders (`field_schema`,
  `table_schema`, `array_schema`, `json_schema`, `metric_spec`,
  `research_spec`) and `spec_dict` / `spec_from_dict`. Invalid contracts raise
  `ContractError` before anything is sent.
- Lifecycle: every protocol-v1 method (`METHODS`), plus
  `with_research_run(client, spec) do run_id ... end` and
  `with_resumed_research_run(client, run_id) do run_id, state ... end`, which
  finalize on success and record a failure before rethrowing.
- Mathematics: outcome probabilities, composite-alternative likelihoods,
  posterior updates and expected information gain matching preregistration v3;
  Wilson intervals; `auroc`, `clustered_auroc` and `paired_clustered_auroc`
  (Obuchowski 1997 clustered variance, reducing to DeLong 1988 for singleton
  clusters).

```bash
julia --project=sdk/julia -e 'using Pkg; Pkg.instantiate()'
julia --project=sdk/julia sdk/julia/test/runtests.jl
julia --project=sdk/julia sdk/julia/examples/evidence.jl study
```

Tests check numerical parity with Python fixtures, the exact DeLong reduction,
the clustered SE against a cluster bootstrap, method and contract parity, and a
live bridge lifecycle. See [`../../docs/RESEARCH_SDK.md`](../../docs/RESEARCH_SDK.md).
Validated on Windows with Julia 1.13.1.
