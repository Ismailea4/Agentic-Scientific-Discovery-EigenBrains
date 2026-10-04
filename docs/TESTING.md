# Test strategy and commands

The default verification suites are offline and deterministic. Test counts
evolve with the implementation and should be read from the current pytest
collection output rather than copied into durable claims. Live provider calls
are never part of the default unit suite.

## Repository-level verification

From the repository root, the preferred acceptance command is:

```powershell
.\scripts\verify.ps1
```

This composes evidence-claim checks, a deterministic SDK reproduction and
tamper negative control, both Python suites, the frontend build, and the Rust
and Julia suites. It makes no provider calls. Use `-CoreOnly` for the Python
control plane or `-ClaimsOnly` to verify only the committed machine-readable
claims. The exact contract is documented in [VERIFICATION.md](VERIFICATION.md).

## Standard verification

```powershell
# Backend, from the repository root
cd .\backend
$env:PYTHONPATH='.'
$testRoot = Join-Path $PWD ('.tmp-pytest-' + [guid]::NewGuid())
python -m pytest tests -q --basetemp $testRoot

# Frontend
cd ..\frontend
npm run typecheck
npm run build

# Discovery lab and Python SDK
cd ..\discolab
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$testRoot = Join-Path $PWD ('.tmp-pytest-' + [guid]::NewGuid())
python -m pytest -q --basetemp $testRoot

# Rust SDK
cd ..
cargo fmt --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml -- --check
cargo clippy --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml

# Julia SDK
julia --project=.\sdk\julia -e 'using Pkg; Pkg.instantiate(); Pkg.test()'
```

The explicit `--basetemp` keeps pytest temporary files inside the workspace and avoids machine-specific temp-directory permissions.

## Test map

| Test module | Contract protected |
|---|---|
| `test_health.py` | Root and API-prefixed health routes. |
| `test_system_api.py` | Empty registries, registry round-trips, Pareto request/response behavior, policy evaluation, fallback, and validation errors. |
| `test_stream.py` | SSE content type, named heartbeat event, and JSON payload. |
| `test_errors.py` | Structured error envelope and status mapping. |
| `test_logging.py` | Secret redaction, request IDs, safe structured logs, error events, optimizer/fallback audit events. |
| `test_ai_interfaces.py` | Provider and agent abstraction behavior. |
| `test_instrumentation.py` | Token, latency, cost, recorder, and model-call observations. |
| `test_trace.py` | Execution trace construction and sanitization. |
| `test_capabilities.py` | Capability implication, leases, scope, expiry, denials, and mandatory requirements. |
| `test_fallback.py` | Ordered fallback eligibility and rejection reasons. |
| `test_pareto.py` | Multi-objective dominance and optimizer behavior. |
| `test_eval.py` | Caller-supplied evaluation and artifact persistence. |
| `test_benchmark_lab.py` | Corpus, runner, aggregation, calibration, tail risk, ablations, artifacts, and publishing. |
| `test_experiment_systems.py` | Confidence bounds, covariance, priors, routing, racing, stress, and experimental controls. |
| `test_pilot.py` | Paired case selection, cost projections, hard limits, and pilot-report sensitivity. |
| `test_baseline_v0.py` | Frozen scoring, split discipline, selective replay, reliability decomposition, and baseline artifact integrity. |

## Important invariants under test

- Catalogues start empty; production routes do not inject sample data.
- All application errors share the same JSON envelope.
- Capability and privacy checks happen before optimization.
- Fallback selection is deterministic and records rejection reasons.
- Logs omit prompts, documents, credentials, headers, and cookies.
- Unknown model price remains unknown.
- Benchmark calls require explicit spend, call, and concurrency limits.
- Paired statistics require identical case coverage.
- Held-out data cannot fit routing thresholds.
- Offline replay is labeled as replay and makes no provider calls.
- Provider availability is not conflated with correctness conditional on a successful call.

## Writing a backend test

Use the shared `client` fixture from `tests/conftest.py` for API tests. Prefer exact assertions for stable contracts:

```python
def test_catalogue_contract(client):
    response = client.get("/api/system/capabilities")
    assert response.status_code == 200
    assert response.json() == {"capabilities": []}
```

For pure policy or optimizer behavior, instantiate domain objects directly. Avoid network calls, wall-clock assumptions, random data without a fixed seed, or assertions against implementation-private fields.

For artifact tests, use pytest's `tmp_path` and verify both human-readable and machine-readable outputs. Never use a real credential in fixtures.

## Adding an API contract

A route change is complete only when the following agree:

- Pydantic model and route behavior;
- TypeScript interface and client wrapper;
- success response test;
- validation/error response test;
- [API_CONTRACTS.md](API_CONTRACTS.md).

## Frontend verification

The frontend currently uses static type checking and a production Vite build rather than a browser unit-test framework. `npm run typecheck` protects the backend/client type mirror; `npm run build` protects module resolution, asset imports, and production bundling.

Visual regression inputs live under `frontend/qa-screenshots/`, and `frontend/scripts/capture-story.mjs` captures the principal chapters and Team surface. These are QA artifacts, not numerical benchmark evidence.

## Discovery-lab test map

| Test module | Contract protected |
|---|---|
| `test_ga.py` | Determinism, common random numbers, elitism, controller visibility, invalid actions. |
| `test_controllers_features.py` | Mutation bounds, intervention behavior, labels, feature causality, model serialization. |
| `test_landscapes.py` | Known optima, seeded shifts, domain safety, recovery calibration. |
| `test_predict.py` | Logistic fitting, informative/null feature behavior, AUROC inference. |
| `test_metrics.py` | Censoring-aware recovery outcomes and rescue/damage counts. |
| `test_stats.py` | AUROC, Wilson, clustered bootstrap, multiplicity, McNemar, effect sizes, CVaR. |
| `test_planner.py` | Likelihood model, information gain, posterior direction, SESOI, status consistency. |
| `test_ledger.py` | Initialization, append-only guards, pure replay, preregistration hashing. |
| `test_lab_flow.py` | Full state machine, held-out feasibility, failure/abort behavior, belief coupling. |
| `test_literature.py` | Identifier/title evidence validation. |
| `test_portfolio.py` | Failure dependence and complementarity. |
| `test_sdk.py` | Python/RPC contract, schema parity, and cross-language numerical fixtures. |
| `test_evidence_sdk.py` | Generic evidence runs, deterministic reproduction, budget and tamper failures. |

Additional evidence-lifecycle modules may be present on active branches. Their
test names are the executable specification for checkpoint, decision, listing,
bundle, and protocol behavior.

## Test taxonomy

- **Unit:** one deterministic function or state transition; no network.
- **Contract:** agreement between API/model/client or RPC/language bindings.
- **Invariant:** property that must hold across generated or adversarial inputs.
- **Integration:** real local components, such as a Rust client plus Python bridge.
- **Scientific regression:** frozen numerical output or verdict under a named protocol.
- **Provider-backed experiment:** paid/time-sensitive empirical run; never part of default CI.

Tests prove implementation behavior, not the scientific truth of a hypothesis.
A passing statistical test suite shows that the estimator behaves as specified;
it does not validate the assumptions of a particular study.

## Provider-backed experiments

Provider-backed runs are controlled experiments, not unit tests. They must have explicit authorization, known price ceilings, fixed prompts/configuration, bounded concurrency, immutable raw observations, and a stop condition. Their methodology is described in [BENCHMARK_METHODOLOGY.md](BENCHMARK_METHODOLOGY.md).

