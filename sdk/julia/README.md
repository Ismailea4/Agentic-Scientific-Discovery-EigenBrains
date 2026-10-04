# EigenBrains Julia SDK

The Julia package provides the JSONL bridge client and mathematical primitives
matching preregistration v3: outcome probabilities, composite-alternative
likelihoods, posterior updates, expected information gain, and Wilson intervals.

```julia
using Pkg
Pkg.activate("sdk/julia")
Pkg.instantiate()
Pkg.test()
```

Run `examples/discovery.jl` from a Python environment where `discolab` is
installed. Julia is not installed on the current development machine, so this
initial package has not yet been executed here.
