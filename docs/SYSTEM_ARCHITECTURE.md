# System architecture

EigenBrains is an evidence-centered research platform composed of four layers:

```text
Researcher / operator
        |
        +--> Cinematic React control surface
        |          |
        |          +--> FastAPI policy, routing, benchmark, and telemetry services
        |
        +--> Python / Rust / Julia research SDK
        |          |
        |          +--> versioned local JSONL bridge
        |          +--> evidence runs, schemas, provenance, validation
        |
        +--> Omnigent PI supervisor
                   |
                   +--> literature / designer / critic specialists
                   +--> deterministic scientific tools
                   +--> append-only discovery ledger and run artifacts
```

The layers are intentionally separable. The UI can demonstrate the product
narrative without spending provider budget. The API can evaluate policies and
benchmarks without running the Omnigent lab. The scientific core can execute
offline without an LLM. The SDK can record experiments outside the original
dynamic-optimization domain.

## Repository topology

| Path | Role | Authoritative data |
|---|---|---|
| `frontend/` | React/Vite desktop-style interface | UI state and explicitly labeled fixtures |
| `backend/` | FastAPI control plane, policy, providers, optimization, benchmark analysis | API models, normalized call observations, routing calculations |
| `benchmark/` | Frozen model-evaluation inputs, limits, observations, and reports | paired raw calls and derived architecture evidence |
| `discolab/` | Deterministic scientific engine and Omnigent discovery loop | preregistration, ledger, numerical artifacts, belief updates |
| `sdk/` | Rust/Julia clients, protocol, examples | cross-language compatibility contract |
| `docs/` | Human-readable operating and research standards | interpretation, procedures, limitations |

## Control-plane request flow

```text
HTTP request
  -> request ID and safe timing log
  -> Pydantic validation
  -> hard capability/privacy feasibility
  -> deterministic fallback or multi-objective selection
  -> provider-neutral agent boundary, when authorized
  -> normalized model-call observation
  -> explicit response model / structured error
```

Hard constraints precede utility. A high predicted quality cannot compensate
for a missing mandatory capability, an explicit denial, an incompatible privacy
class, an expired lease, or an unavailable provider.

Provider adapters normalize messages, token usage, latency, outcome, and cost.
Unknown prices remain `null`; they are never converted to zero. Model
correctness conditional on a successful provider response remains separate from
provider availability and end-to-end operational correctness.

## Benchmark evidence flow

```text
Frozen corpus + split + prompt + evaluator + limits
  -> provider calls with immutable case IDs
  -> raw normalized observations
  -> paired loss matrix
  -> reliability and task-family summaries
  -> covariance / conditional failure / complementarity
  -> replayed or provider-backed architecture policies
  -> empirical and robust Pareto frontiers
  -> weak, explicitly overturnable priors
```

Pairing is central: every compared model should see the same case. Missing
provider responses are operational failures, but they must not be silently
reclassified as reasoning errors. Offline replay must remain labeled separately
from a provider-backed multi-agent execution.

## Discovery-loop flow

```text
Frozen preregistration
  -> literature evidence and competing experiment proposals
  -> deterministic information-gain-per-cost scoring
  -> PI selection, with justification and override record
  -> seeded numerical experiment
  -> preregistered statistical analysis
  -> verdict and Bayesian belief update
  -> stop or selectively escalate sample size while inconclusive
  -> critic interpretation and threats to validity
  -> next decision and rescored candidates
```

The PI owns which experiment to run. Specialist permissions are structurally
limited:

- literature retrieves and records evidence but cannot spend compute;
- designer proposes and scores experiments but cannot select or run them;
- critic interprets completed results but cannot rewrite specifications;
- only the PI selects, runs, and records the next decision.

Agents never supply measured numbers. Numerical outputs come from deterministic
tools, and every state transition passes through ledger guards.

The acceleration harness is a deterministic evaluation of the decision policy,
not another agent. It compares fixed full-size experiments with frozen
6 -> 12 -> 24-seed escalation against a separate 48-seed reference. Its source
of truth is `discolab/escalation_protocol.yaml`; recorded ledgers, manifests,
per-replicate results, and the aggregate summary live under
`discolab/results/escalation/`.

## Research SDK flow

```text
ExperimentSpecV2
  -> seeded RunContext
  -> cooperative budget accounting
  -> schema-checked raw artifacts
  -> derived/analysis artifacts with parent lineage
  -> unit-bearing metrics
  -> finalize
  -> hash and schema validation
  -> deliberate evidence decision
```

Python is authoritative. Rust provides a typed client and performance-oriented
kernels. Julia provides a typed client and mathematical helpers. Both clients
communicate with a persistent local Python process using protocol version 1.
The bridge accepts named operations; it is not a general shell or arbitrary
Python execution service.

## Data ownership and immutability

| Object | Mutation policy |
|---|---|
| Benchmark case definitions | versioned; freeze before provider execution |
| Raw provider observations | append-only or immutable cache entry |
| Discovery ledger | append-only; state is a pure fold over events |
| Raw scientific artifacts | write once inside a run |
| Derived reports | regenerable from raw observations and frozen analysis code |
| UI fixtures | editable, but always marked `SAMPLE` |

Never repair raw evidence in place. If a protocol, evaluator, or parser is
wrong, preserve the original result, create a new version, document the reason,
and rerun or conduct a labeled sensitivity analysis.

## Trust boundaries

1. **External providers are untrusted dependencies.** Responses may fail,
   drift, truncate, or violate schemas.
2. **LLM agents are decision aids.** They do not receive authority to fabricate
   results or bypass policies.
3. **The numerical core is the measurement authority.** Seeded tools and
   validators produce scientific quantities.
4. **The UI is not an evidence store.** It renders API results and fixtures.
5. **The filesystem is local trust.** Content hashes detect accidental or
   partial changes under the documented threat model; they are not a substitute
   for cryptographic signatures or access control.

## Extension rules

When adding a component, preserve the boundary it belongs to:

- new providers implement the provider interface and shared instrumentation;
- new API endpoints use response models and update the frontend type mirror;
- new capabilities remain hard policy objects, not utility bonuses;
- new experiment families define a protocol, schemas, seeds, and decision rules
  before running;
- new language bindings extend the versioned protocol and parity tests;
- new UI demonstrations identify whether their values are sample, replay,
  benchmark, provider-backed, or live.
