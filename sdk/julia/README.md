# EigenBrains Julia SDK

The Julia package provides a protocol-v1 lifecycle client with structured remote
errors and mathematical primitives matching preregistration v3: outcome
probabilities, composite-alternative likelihoods, posterior updates, expected
information gain, and Wilson intervals.

```julia
using Pkg
Pkg.activate("sdk/julia")
Pkg.instantiate()
Pkg.test()
```

Run `examples/discovery.jl` from a Python environment where `discolab` is
installed. The suite is validated on Windows with Julia 1.13.1 and includes a
live Python bridge lifecycle test in addition to decision-math parity checks.
