# EigenBrains codebase guide

For the cross-component topology, research SDK, and discovery-lab relationship,
start with [System architecture](SYSTEM_ARCHITECTURE.md). This file focuses on
the FastAPI/React control plane.

EigenBrains is an evidence-driven control plane for selecting and executing AI-agent architectures. The product combines a cinematic React interface, a typed FastAPI service, capability and fallback policy enforcement, provider-neutral model calls, and an experimental laboratory for measuring quality, cost, latency, availability, and downside risk.

The central design rule is simple: measurements may influence a decision, but they cannot override a hard capability, privacy, or authorization constraint.

## Runtime topology

```text
React + TypeScript interface
  -> typed HTTP/SSE client
  -> FastAPI routes
  -> capability and privacy feasibility checks
  -> architecture registry and optimizer
  -> provider-neutral agents and model adapters
  -> normalized call observations
  -> traces, metrics, and benchmark evidence
```

The Vite development server serves the interface on port `5173` and proxies `/api` and `/health` to FastAPI on port `8000`.

## Repository map

| Path | Responsibility |
|---|---|
| `frontend/src/App.tsx` | Desktop shell, navigation, theme state, Team dialog, and active workspace. |
| `frontend/src/components/` | Reusable interface surfaces, diagrams, charts, controls, and the Team panel. |
| `frontend/src/views/` | Workspace-level screens. Live views read backend catalogues; showcase content remains explicitly fixture-based. |
| `frontend/src/api/` | Typed fetch client, shared request/response types, system endpoint wrappers, and SSE subscription helper. |
| `backend/app/main.py` | Application factory, CORS, middleware, exception handlers, registries, and router mounting. |
| `backend/app/api/` | Public HTTP and SSE contracts. |
| `backend/app/ai/` | Provider-neutral `AIProvider`, `Agent`, message, response, token, and task abstractions. |
| `backend/app/providers/` | Minimal Anthropic, Gemini, OpenAI-compatible, Groq, and OpenRouter adapters. |
| `backend/app/capabilities/` | Capability graph, leases, implication, denials, scope, expiry, and least-privilege decisions. |
| `backend/app/fallback/` | Deterministic fallback eligibility and rejection reasons. |
| `backend/app/optimization/` | Pareto selection, utility, covariance, portfolio analysis, robust routing, Bayesian updates, and tail risk. |
| `backend/app/instrumentation/` | Pricing, normalized call metrics, traces, and recorders. |
| `backend/app/benchmark/` | Corpus, runner, frozen scoring, replay policies, confidence bounds, priors, stress tests, racing, and artifact generation. |
| `backend/app/system/registry.py` | In-memory capability and architecture catalogues exposed by the API. |
| `backend/tests/` | Offline unit and contract tests. |
| `benchmark/` | Versioned cases, non-secret configurations, frozen manifests, raw observations, derived artifacts, and reports. |

## Backend boundaries

### API layer

Routes translate JSON into domain objects and return explicit response models. They do not invent capabilities, model scores, fallback eligibility, or architecture measurements. The complete wire contract is documented in [API_CONTRACTS.md](API_CONTRACTS.md).

### Policy layer

`evaluate_policy` expands capability implications, applies explicit denials, validates leases, and separates missing mandatory requirements from missing optional ones. A mandatory failure makes an execution infeasible before optimization begins.

### Optimization layer

Candidates first pass hard capability and privacy constraints. Remaining candidates may be classified on an empirical Pareto frontier or ranked with caller-supplied weights. Unknown prices stay unknown and are excluded from cost-aware selection rather than being treated as zero.

### AI/provider layer

Providers implement one `AIProvider` interface and normalize their result into `ModelResponse`. `Agent._generate` is the instrumentation seam: all model calls should pass through it so provider, model, task, tokens, latency, cost, and outcome remain traceable.

Provider credentials are accepted only through environment variables. They are never part of request models, benchmark records, traces, or API responses.

### Experimental layer

Every execution becomes a `BenchmarkRun`. Analysis is derived from those immutable observations: reliability, paired losses, covariance, confidence bounds, Pareto status, tail risk, escalation economics, and weak priors. Offline replay is labeled separately from actual provider-backed execution.

See [FINANCIAL_MATH_AND_META_AGENT.md](FINANCIAL_MATH_AND_META_AGENT.md) for the quantitative model and [BENCHMARK_METHODOLOGY.md](BENCHMARK_METHODOLOGY.md) for the evidence protocol.

## Request lifecycle

1. `RequestLogMiddleware` assigns a request ID and records timing without logging bodies, prompts, credentials, cookies, or authorization headers.
2. FastAPI validates the request against Pydantic models.
3. The route constructs domain objects and invokes policy, fallback, or optimization logic.
4. Domain failures become the shared structured error envelope.
5. Successful results are serialized through explicit response models.
6. The frontend client either returns the typed body or throws `ApiError` with status, code, message, and details.

## Evidence states

| State | Meaning | Permitted use |
|---|---|---|
| `SAMPLE` | UI-only fixture data. | Visual demonstration only. |
| `BENCHMARK` | Recorded execution on a named corpus, split, prompt, and model configuration. | Experimental comparison within the declared scope. |
| `LIVE` | Runtime telemetry from the deployed task. | Operational routing and monitoring, subject to policy. |

These states must not be silently mixed. In particular, showcase fixtures are not benchmark evidence, and generic benchmark evidence is not a claim about an unseen task.

## Safe extension points

- Add an API route under `backend/app/api/routes/`, include it in `api/router.py`, and mirror its types in `frontend/src/api/types.ts`.
- Add a provider by implementing `AIProvider`; return real token usage and keep credentials environment-only.
- Add an agent by subclassing `Agent` and routing model calls through `_generate`.
- Add challenge task types in `ai/types.py`, objective cases in the corpus, and an evaluator with deterministic behavior.
- Publish an architecture only after all required measurements exist and its evidence state is explicit.
- Add mandatory capabilities as hard requirements, never as soft utility penalties.

## Local development

```powershell
# From the repository root: backend
cd .\backend
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --port 8000

# From the repository root: frontend, in another terminal
cd .\frontend
npm ci
npm run dev
```

Verification commands and the test map are in [TESTING.md](TESTING.md).

## Security invariants

- Do not read or commit `.env` files, API-key files, tokens, or credentials.
- Logs and traces must pass through the shared redaction layer.
- Never log prompts, documents, request headers, or cookies.
- Unknown cost is `null`, not zero.
- Held-out observations cannot tune gates, thresholds, model choice, or reconciliation rules.
- Provider failures, model correctness conditional on success, and end-to-end operational quality remain separate measurements.

