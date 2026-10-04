# EigenBrains

EigenBrains is an evidence-driven platform for agentic scientific discovery. It
combines a model/architecture control plane, a reproducible computational
laboratory, a multi-language research SDK, and an interface that explains the
system's decisions without confusing demonstration data with empirical results.

The project is built around one rule:

> Agents may propose, select, and interpret. Validated software owns
> measurements, constraints, state transitions, and statistical calculations.

## What the project does

- Evaluates models and agent architectures using paired outcomes, provider
  availability, cost, latency, covariance, tail risk, and uncertainty.
- Routes work under hard capability, privacy, authorization, and budget
  constraints.
- Runs an autonomous hypothesis-to-evidence loop through a PI supervisor and
  least-privilege literature, experiment-design, and critic agents.
- Executes real seeded numerical experiments on dynamic optimization problems.
- Records append-only decisions, preregistration hashes, raw artifacts,
  provenance, statistical verdicts, and changed next decisions.
- Exposes a research evidence SDK for Python, Rust, and Julia.
- Separates interface fixtures, offline replay, benchmark measurements,
  provider-backed architecture runs, and live telemetry.

## Architecture

```text
React control surface
        |
        v
FastAPI policy + routing + benchmark control plane
        |
        +--> provider-neutral agents and normalized observations
        +--> capability/fallback enforcement
        +--> portfolio, Pareto, Bayesian, and tail-risk analysis

Omnigent PI supervisor
        |
        +--> literature agent
        +--> experiment designer
        +--> critic
        |
        v
deterministic discolab tools --> append-only ledger --> scientific artifacts

Python evidence SDK <--> JSONL protocol <--> Rust and Julia clients
```

For component boundaries and data flow, read
[System architecture](docs/SYSTEM_ARCHITECTURE.md).

## Current empirical foundation

The repository contains five distinct evidence tracks:

1. **Paired model pilot.** A 120-call study measured quality, provider failures,
   latency, cost, and error dependence across five configured models. It found
   that model rank alone was insufficient because failure overlap differed
   substantially between pairs.
2. **Architecture baseline.** A frozen 72-case design measured three models and
   evaluated selective escalation. Offline replay and provider-backed verifier
   calls are reported separately. Held-out comparisons remain uncertainty-bound
   and are not presented as universal rankings.
3. **Autonomous discovery loops.** Two recorded Omnigent runs proposed competing
   experiments, selected by information gain and cost, executed seeded genetic
   algorithm studies, updated beliefs, and changed the next scientific decision.
4. **Measured research acceleration.** A frozen five-replicate study compared a
   conventional 24-seed design with selective 6 -> 12 -> 24-seed escalation
   across seven hypotheses. Selective escalation used 35.15% less simulation
   compute, a mean 1.54x acceleration (95% CI [1.28, 1.90]), while agreeing with
   the 48-seed reference on 28/35 decisions versus 29/35 for the full-size
   design. It produced five rescues and zero damages.
5. **A sealed held-out test overturned a +0.139 development signal.** A
   protocol frozen before any data was run once on 450 untouched runs (150
   independent clusters). Adding population entropy raised development AUROC
   by +0.139 [+0.131, +0.149], but on held-out landscapes the gain vanished:
   ΔAUROC −0.006 [−0.011, −0.0003], registered verdict `no_meaningful_gain`,
   with a landscape-dependent sign (Griewank +0.058, Levy −0.046). See the
   [sealed result report](docs/SEALED_ENTROPY_EARLY_WARNING_RESULT.md).

The recorded discovery evidence supports a development-stage result: population
entropy and genotypic dispersion added predictive information about impending
search stagnation on the studied development landscapes. It did not establish
that the resulting predictive mutation controller beats a rate-matched fixed
baseline. The sealed held-out test (track 5) then showed that entropy's added
predictive value does not generalize across untouched landscapes: it is
landscape-dependent, so it is not claimed as a universal early-warning signal.
The 1.54x acceleration and this negative result are separate studies.

Start with:

- [Model pilot report](benchmark/reports/PILOT_REPORT.md)
- [Machine-readable architecture baseline](benchmark/artifacts/baseline_v0/baseline_v0_summary.json)
- [Discovery run 1](discolab/results/run1_prereg_v1/README.md)
- [Discovery run 2](discolab/results/run2_prereg_v2/README.md)
- [Measured research-acceleration study](discolab/results/escalation/README.md)
- [Sealed entropy early-warning result (held-out, negative)](docs/SEALED_ENTROPY_EARLY_WARNING_RESULT.md)
- [Machine-readable acceleration results](discolab/results/escalation/summary.json)
- [Benchmark methodology](docs/BENCHMARK_METHODOLOGY.md)
- [Scientific rigor standard](docs/SCIENTIFIC_RIGOR.md)

## Repository map

| Path | Purpose |
|---|---|
| `frontend/` | React/Vite cinematic control surface and visual QA assets |
| `backend/` | FastAPI API, provider abstractions, policy, optimization, instrumentation, and benchmark engine |
| `benchmark/` | Frozen cases/configuration, raw observations, derived artifacts, and reports |
| `discolab/` | Scientific core, preregistration, Omnigent bundle, ledgers, and recorded discovery runs |
| `sdk/` | Rust and Julia packages, cross-language protocol, and executable examples |
| `docs/` | Architecture, research, operations, API, testing, and reproducibility documentation |

## Quick start

### Backend

```powershell
python -m venv .venv-backend
& .\.venv-backend\Scripts\Activate.ps1
python -m pip install -r .\backend\requirements-dev.txt
Set-Location .\backend
$env:PYTHONPATH = "."
python -m pytest tests -q
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend

In another terminal:

```powershell
Set-Location .\frontend
npm ci
npm run typecheck
npm run build
npm run dev
```

Open `http://localhost:5173`. API documentation is available at
`http://localhost:8000/docs`.

### Scientific core and SDK

```powershell
Set-Location .\discolab
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
python -m pytest -q
Set-Location ..
python .\sdk\examples\research_evidence.py
```

The complete platform setup, including Rust, Julia, and Omnigent, is in
[Getting started](docs/GETTING_STARTED.md).

## Research SDK

The SDK records experiments as self-describing evidence runs:

- explicit hypothesis, protocol, parameters, seed, budget, outputs, and primary
  metric;
- controlled random streams;
- semantic table/array/JSON schemas;
- units, bounds, roles, censoring, stages, and lineage;
- Git/runtime/dependency/system provenance;
- content validation, comparison, evidence decisions, and reproduction.

Python is the authoritative runtime. Rust is the performance-oriented path and
Julia is the mathematical-research path; both use a versioned local JSONL
protocol and retain structured remote errors.

Read [Research SDK](docs/RESEARCH_SDK.md) and
[SDK contracts](docs/SDK_CONTRACTS.md).

To experience the three-language contract directly:

```powershell
python -m sdk.interop.demo
```

The command produces one shared, validated evidence graph across Python, Rust,
and Julia and exports a verified bundle. It is an interoperability proof, not a
performance or scientific benchmark.

## Reproducibility and scientific rigor

Before making a scientific claim:

1. freeze the hypothesis, primary outcome, split, seed policy, exclusions,
   statistical analysis, stopping rule, and budgets;
2. separate development/tuning from held-out confirmation;
3. preserve pairing, clustering, censoring, and failures;
4. keep raw, derived, and analysis artifacts distinct;
5. report effect sizes and uncertainty, including unresolved comparisons;
6. validate content hashes and schemas;
7. reproduce at least one run independently;
8. state exactly which claims are supported, unresolved, or contradicted.

The full standards are in:

- [Reproducibility handbook](docs/REPRODUCIBILITY.md)
- [Scientific rigor standard](docs/SCIENTIFIC_RIGOR.md)
- [Scientific research playbook](docs/SCIENTIFIC_RESEARCH_PLAYBOOK.md)

## Verify the repository offline

From PowerShell at the repository root:

```powershell
.\scripts\verify.ps1
```

The command makes no provider calls. It validates the published model-routing
and research-acceleration claims against their machine-readable artifacts,
performs a deterministic SDK run and byte-level reproduction, and runs the
offline Python, frontend, Rust, and Julia verification suites. Use
`.\scripts\verify.ps1 -CoreOnly` when the optional language toolchains are not
installed. See [Verification and reproduction](docs/VERIFICATION.md).

## Security

The repository must never contain credential values. Provider keys are read
from environment variables only. Logs omit prompts, documents, request headers,
cookies, and credentials. The local API currently has no authentication and
must not be exposed directly to an untrusted network.

See [Security policy](SECURITY.md).

## Documentation

The documentation portal is [docs/README.md](docs/README.md). It includes
architecture, setup, operations, contracts, testing, contribution rules,
troubleshooting, terminology, reproducibility, and research standards.

## Scope and limitations

- Generic benchmark evidence is a weak prior, not proof about an unseen task.
- Small held-out sets produce wide uncertainty, especially for tail risk and
  rescue probability.
- Offline replay is not equivalent to an executed multi-agent architecture.
- Provider behavior and pricing can drift over time.
- Rust and Julia SDK clients currently rely on the Python sidecar.
- Content hashes provide integrity checks under a local threat model; they are
  not digital signatures.
- The discovery results recorded so far are development-stage unless explicitly
  labeled otherwise.

Negative and inconclusive results are first-class outputs. The platform's goal
is not to guarantee a positive discovery; it is to reach valid evidence and the
next defensible decision faster.
