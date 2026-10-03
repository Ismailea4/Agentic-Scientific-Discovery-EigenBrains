# Test strategy and commands

The default verification suite is offline and deterministic. It currently contains 120 backend tests plus frontend type and production-build checks. Live provider calls are never part of the default unit suite.

## Standard verification

```powershell
# Backend
cd F:\hack7\backend
$env:PYTHONPATH='.'
python -m pytest tests -q --basetemp F:\hack7\.pytest-eigenbrains

# Frontend
cd F:\hack7\frontend
npm run typecheck
npm run build
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

## Provider-backed experiments

Provider-backed runs are controlled experiments, not unit tests. They must have explicit authorization, known price ceilings, fixed prompts/configuration, bounded concurrency, immutable raw observations, and a stop condition. Their methodology is described in [BENCHMARK_METHODOLOGY.md](BENCHMARK_METHODOLOGY.md).

