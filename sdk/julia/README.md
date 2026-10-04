# EigenBrains Julia SDK

The Julia package provides a protocol-v1 lifecycle client with structured remote
errors and mathematical primitives matching preregistration v3: outcome
probabilities, composite-alternative likelihoods, posterior updates, expected
information gain, and Wilson intervals.

It also exposes typed `ResourceBudget`, `FieldSchema`, `ArtifactSchema`,
`MetricSpec`, and `ResearchExperimentSpec` values plus the full generic evidence
lifecycle (`begin_research_run!` through validation, comparison, acceptance,
and reproduction). See [`../../docs/RESEARCH_SDK.md`](../../docs/RESEARCH_SDK.md).

```julia
using Pkg
Pkg.activate("sdk/julia")
Pkg.instantiate()
Pkg.test()
```

Run `examples/discovery.jl` from a Python environment where `discolab` is
installed. The suite is validated on Windows with Julia 1.13.1 and includes a
live Python bridge test for both lifecycle families in addition to
decision-math parity checks. The Python package is the authoritative sidecar.
