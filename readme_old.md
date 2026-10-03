# EigenBrains

EigenBrains is an evidence-driven control center for composing and selecting
AI-agent architectures. It combines a **React + TypeScript + Vite** desktop
interface with a **Python FastAPI** backend, provider-neutral model adapters,
least-privilege capability enforcement, deterministic fallback, end-to-end
instrumentation, and a reproducible quantitative laboratory.

The repository contains measured generic-baseline evidence, but makes no claim
about an unseen domain. Interface fixtures, benchmark observations, and live
runtime telemetry remain explicitly separated.

## Documentation

- [`docs/CODEBASE.md`](docs/CODEBASE.md) — architecture, module ownership,
  request lifecycle, extension points, and security invariants.
- [`docs/API_CONTRACTS.md`](docs/API_CONTRACTS.md) — HTTP/SSE endpoints,
  schemas, examples, errors, and frontend synchronization rules.
- [`docs/TESTING.md`](docs/TESTING.md) — unit-test map, protected invariants,
  verification commands, and contribution guidance.
- [`docs/FINANCIAL_MATH_AND_META_AGENT.md`](docs/FINANCIAL_MATH_AND_META_AGENT.md)
  — portfolio theory, econometrics, routing policy, priors, and measured results.
- [`docs/BENCHMARK_METHODOLOGY.md`](docs/BENCHMARK_METHODOLOGY.md) — corpus,
  splits, scoring, provider protocol, call accounting, statistics, and limitations.

## Quickstart

Backend (Python 3.10+; developed on 3.14):

```bash
cd backend
python -m venv .venv
# Git Bash on Windows:
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

Frontend (Node 18+; developed on 22):

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

The Vite dev server proxies `/api` and `/health` to `http://localhost:8000`,
so no CORS is needed in dev; CORS for `localhost:5173` is also configured for
direct cross-origin calls.

## Verification commands

```bash
cd backend && ./.venv/Scripts/python.exe -m pytest     # or: python -m pytest with venv active
cd frontend && npm run typecheck && npm run build
```

## Pipeline

The runtime and laboratory share one path. Generic benchmark evidence can
seed weak priors, while task-specific measurements and caller-supplied
preferences determine the deployed architecture.

```
Benchmark
    ↓
measured quality, cost, latency, risk
    ↓
capability-feasible set          # hard constraint, never a weight
    ↓
Pareto / weighted utility
    ↓
selected architecture
    ↓
least-privilege execution
    ↓
fallback, only if it is allowed
    ↓
auditable execution trace
```

Security checks (`evaluate_policy`, fallback allow-lists, optimizer
constraints) remove candidates before utility is computed. A higher score
cannot buy back a denied capability.

## Logging

Operational logs and execution traces are separate. Logs are events on
stderr (and an optional JSONL file). Traces are the product audit record
built by `ExecutionTraceBuilder` in `app/instrumentation/trace.py`. Logs are
redacted via `app.core.redaction.redact`; trace metadata passes through
`sanitize_metadata`, which coerces values to strings and replaces any
secret-ish key (key, token, secret, password, credential, env) with
`"[REDACTED]"`.

```
LOG_LEVEL=INFO
LOG_FORMAT=console          # or json
LOG_FILE_ENABLED=false
LOG_FILE_PATH=backend/data/logs/app.jsonl
```

Events include `request.started`, `request.completed`, `request.failed`,
`model.call.*`, `agent.*` (via `Agent.execute`), `capability.granted`,
`capability.denied`, `optimizer.*`, `fallback.*`, and `sse.connected` /
`sse.disconnected`. Query strings, authorization headers, cookies, prompts,
and document fields are not logged. `bind_execution(task_id=..., trace_id=...)`
stamps later events.

## Architecture map

```
backend/app/
├── main.py                  # create_app(): CORS, request log, errors, routers
├── config.py                # Settings from env (see .env.example)
├── core/
│   ├── errors.py            # AppError → {"error": {code, message, details}}
│   ├── logging.py           # structured stdlib events, console or JSON
│   ├── redaction.py         # shared secret redaction
│   └── request_log.py       # ASGI request timing, no body buffering
├── api/routes/
│   ├── health.py            # GET /health and /api/health
│   ├── stream.py            # GET /api/stream/heartbeat
│   └── system.py            # capabilities, architectures, pareto, policy, fallback
├── ai/                      # AIProvider + Agent ABCs, instrumented _generate
├── capabilities/            # leases, implication, least-privilege decision
├── optimization/            # metrics, Pareto, weighted utility, constraints
├── fallback/                # ordered, auditable fallback resolution
├── instrumentation/         # per-call tokens/latency/cost + execution trace
├── eval/                    # caller-supplied scores → JSONL + CSV
└── system/registry.py       # empty in-memory catalogues
```

System endpoints (all generic; the caller supplies every number):

- `GET /api/system/capabilities` — registered capability catalog (starts empty)
- `GET /api/system/architectures` — registered architecture candidates (starts empty)
- `POST /api/system/pareto-frontier` — classify caller-supplied candidates
- `POST /api/system/evaluate-policy` — evaluate leases/denials against requirements
- `POST /api/system/resolve-fallback` — ordered fallback with rejection reasons

```
frontend/src/
├── App.tsx                  # glass shell: workspace, showcase, stream
├── components/              # panels, agent graph, frontier chart, inspector
├── views/                   # workspace reads live catalogues only
├── dev/fixtures.ts          # showcase-only sample numbers
└── api/                     # typed client, SSE helper, system routes
```

Error contract (kept in sync both sides): non-2xx responses return
`{"error": {"code", "message", "details"}}`; the frontend surfaces this via
`ApiError`.

## Where to plug in challenge code

- **AI providers**: subclass `app.ai.provider.AIProvider` (implement `name`,
  `generate`, `stream`) adapting your provider SDK into `ModelResponse`
  (including real `TokenUsage` so cost estimation works).
- **Agents**: subclass `app.ai.agent.Agent`; implement `run()` and call
  `self._generate(messages, ...)` for every model call — instrumentation
  (model, agent, task type, tokens, latency, USD cost, success/failure) is
  then automatic. Extend `TaskType` in `app/ai/types.py` with challenge
  categories.
- **Pricing**: `DEFAULT_PRICING` is empty. Call `PricingTable.register_model`
  with a per-1k price you have checked. Until then `estimated_cost_usd` stays
  unset, so a demo cannot show a stale dollar figure.
- **Metrics persistence**: construct `MetricsRecorder(jsonl_path=settings.metrics_output_dir / "calls.jsonl")`
  or add sink callables.
- **Evaluation**: build `EvalCase`s, call `run_evaluation(cases, fn, scorer=...)`
  with your own scorer, persist via `EvalRecorder(settings.eval_output_dir)`
  (`write_jsonl` / `write_csv`). The framework never invents scores.
- **Routes**: add modules under `app/api/routes/` and include them in
  `app/api/router.py`; mirror response types in `frontend/src/api/types.ts`.
- **Capabilities**: register names on `app.state.capabilities`. Call
  `evaluate_policy` with the caller's leases. Do not treat a policy failure
  as a score penalty.
- **Architectures**: register measured `ArchitectureCandidate`s on
  `app.state.architectures`. `select_best` applies hard constraints,
  then Pareto, then `OptimizationWeights` supplied by the caller. Default
  weights are neutral (quality 1, penalties 0), not a Fast/Balanced preset.
- **Covariance and tail risk**: aligned benchmark runs can produce empirical
  covariance/correlation, failure overlap, Jaccard similarity, and lower-tail
  statistics. Missing evidence remains missing rather than being synthesized.
- **Fallback**: `resolve_fallback` walks `preference_order` and takes the
  first candidate that is available, holds the mandatory capabilities, matches
  an accepted privacy class, and lists the task. Anything else is rejected
  with a reason.
- **Traces**: `ExecutionTraceBuilder` records the decisions you pass in.
  `add_optimization` stores `OptimizationResult.to_dict()`. Model-call
  metadata is not copied onto the trace.
- **Logs**: call `log_event` for new operational facts. Use `bind_execution`
  around a task. Do not log prompts, documents, or headers.
- **Domain errors**: raise `AppError` subclasses (`NotFoundError`,
  `ValidationError`, `ProviderError`, or your own) — they automatically render
  in the structured error format.

## Interface

`npm run dev` serves three views:

- **Workspace** reads `GET /api/system/capabilities` and
  `GET /api/system/architectures`. Both are empty until something registers.
  Fast / Balanced / Maximum Reliability are labels with no weights.
- **Showcase** (`#/showcase`) is the only place fixture numbers are used. It
  posts those fixtures to the Pareto, policy, and fallback routes.
- **Stream** exercises the existing heartbeat SSE pipe.

The dev server proxies `/api` and `/health` to port 8000.

## Experimental laboratory

The backend includes an Architecture Baseline v0 laboratory
on the same provider, instrumentation, optimizer, registry, and API spine. It
provides a deterministic 72-case objective corpus, paired uncertainty,
empirical and robust Pareto analysis, covariance and conditional-failure
diagnostics, downside VaR/CVaR, marginal-agent economics, bounded weak priors,
sequential racing, robust routing, stress tests, and architecture cards. It
ships no fabricated model results and makes no challenge-performance claim.
See [`docs/BENCHMARK_METHODOLOGY.md`](docs/BENCHMARK_METHODOLOGY.md) for the
frozen evidence protocol and [`backend/EXPERIMENTS.md`](backend/EXPERIMENTS.md)
for implementation-level experimental tooling.

## Environment

Copy `.env.example` to `backend/.env` (or export the variables) to override
defaults. Placeholders only — no secrets belong in the repo.
