# HTTP and streaming API contracts

The backend is a FastAPI application. In local development the direct origin is `http://localhost:8000`; the Vite server proxies the same routes from `http://localhost:5173`.

FastAPI also exposes generated interactive documentation at `/docs` and the OpenAPI schema at `/openapi.json`.

## Contract conventions

- JSON requests use `Content-Type: application/json`.
- Timestamps are ISO-8601 strings in UTC unless a request explicitly supplies an offset.
- Catalogue endpoints return empty arrays until application code registers entries.
- `quality` is maximized; `cost`, `latency`, and `risk` are minimized.
- Unknown values are not synthesized. API architecture candidates currently require numeric metrics.
- There is no authentication layer in this repository.

### Error envelope

Every handled non-2xx response uses:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Human-readable explanation.",
    "details": {}
  }
}
```

Defined application errors are `404 not_found`, `422 validation_error`, and `502 provider_error`. FastAPI request-shape failures use `422 request_validation_error`; unexpected failures use `500 internal_error`. The frontend mirrors this as `ApiError` in `frontend/src/api/client.ts`.

## Endpoint summary

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Root health check for operators and load balancers. |
| `GET` | `/api/health` | API-prefixed form of the same health check. |
| `GET` | `/api/system/capabilities` | Read the in-memory capability catalogue. |
| `GET` | `/api/system/architectures` | Read measured architecture candidates in the registry. |
| `POST` | `/api/system/pareto-frontier` | Classify caller-supplied candidates as frontier or dominated. |
| `POST` | `/api/system/evaluate-policy` | Evaluate capability requirements against denials and leases. |
| `POST` | `/api/system/resolve-fallback` | Select the first eligible fallback in explicit preference order. |
| `GET` | `/api/stream/heartbeat` | Finite five-event SSE heartbeat used to verify streaming. |

## Health

`GET /health` and `GET /api/health`

```json
{
  "status": "ok",
  "version": "0.1.0",
  "time": "2026-10-03T12:00:00+00:00"
}
```

## Capability catalogue

`GET /api/system/capabilities`

```json
{
  "capabilities": [
    {
      "name": "draft",
      "description": "Create a draft response",
      "implies": ["read"]
    }
  ]
}
```

`name` is the stable capability identifier. `implies` is a directed implication list expanded by the policy engine.

## Architecture catalogue

`GET /api/system/architectures`

```json
{
  "architectures": [
    {
      "id": "selective-verifier-v0",
      "name": "Selective verifier",
      "quality": 0.83,
      "cost": 0.00005,
      "latency": 1378.0,
      "risk": 0.17,
      "metadata": {"evidence_state": "BENCHMARK"}
    }
  ]
}
```

The registry starts empty. Only complete, measured candidates should be published.

## Pareto classification

`POST /api/system/pareto-frontier`

Request:

```json
{
  "candidates": [
    {"id": "lean", "quality": 0.75, "cost": 1.0, "latency": 10.0, "risk": 0.25},
    {"id": "careful", "quality": 0.90, "cost": 2.0, "latency": 20.0, "risk": 0.10}
  ]
}
```

Response:

```json
{
  "frontier": ["careful", "lean"],
  "dominated": []
}
```

A candidate dominates another only when it is no worse on all four objectives and strictly better on at least one. Candidate IDs must be unique.

## Capability policy evaluation

`POST /api/system/evaluate-policy`

Request:

```json
{
  "capabilities": [
    {"name": "read", "description": null, "implies": []},
    {"name": "draft", "description": null, "implies": ["read"]}
  ],
  "requirements": [
    {"capability": "read", "mandatory": true},
    {"capability": "export", "mandatory": false}
  ],
  "denied": ["export"],
  "leases": [
    {
      "capability": "draft",
      "allowed": true,
      "task_scope": "alpha",
      "expires_at": null,
      "max_calls": null,
      "calls_used": 0,
      "source": "profile"
    }
  ],
  "task_scope": "alpha"
}
```

Response:

```json
{
  "allowed": true,
  "granted": ["draft", "read"],
  "denied": ["export"],
  "missing_mandatory": [],
  "missing_optional": ["export"],
  "reasons": [
    "all mandatory capabilities are satisfied",
    "missing optional capability 'export'"
  ]
}
```

`expires_at` must be ISO-8601. A lease is usable only when it is allowed, in scope, unexpired, and below `max_calls`. Missing mandatory requirements make `allowed` false; missing optional requirements do not.

## Fallback resolution

`POST /api/system/resolve-fallback`

Request:

```json
{
  "candidates": [
    {
      "id": "primary",
      "available": false,
      "capabilities": ["read"],
      "privacy_class": "restricted",
      "allowed_tasks": ["review"]
    },
    {
      "id": "local",
      "available": true,
      "capabilities": ["read"],
      "privacy_class": "restricted",
      "allowed_tasks": ["review"]
    }
  ],
  "mandatory_capabilities": ["read"],
  "accepted_privacy_classes": ["restricted"],
  "task": "review",
  "preference_order": ["primary", "local"],
  "capabilities": []
}
```

Response:

```json
{
  "selected_id": "local",
  "considered": ["local", "primary"],
  "rejected": [{"id": "primary", "reason": "unavailable"}],
  "reason": "selected 'local' as the first preference-order candidate that satisfied every constraint"
}
```

Resolution is deterministic and order-sensitive. A candidate can be rejected for availability, capability, privacy-class, or task-scope failure. A higher model score cannot override these checks.

## Server-Sent Events

`GET /api/stream/heartbeat` returns `text/event-stream` with `Cache-Control: no-cache`, `Connection: keep-alive`, and `X-Accel-Buffering: no`.

Each of the five frames has this shape:

```text
event: heartbeat
data: {"tick": 0, "time": "2026-10-03T12:00:00+00:00"}

```

The frontend subscribes with `subscribeSSE(path, handlers)` and must explicitly listen for the named `heartbeat` event.

## Keeping frontend and backend synchronized

When an endpoint changes:

1. Update its Pydantic request/response model in `backend/app/api/routes/`.
2. Update the matching TypeScript interface in `frontend/src/api/types.ts`.
3. Update or add the wrapper in `frontend/src/api/system.ts`.
4. Add a backend contract test that asserts status and exact response shape.
5. Run backend tests, frontend type checking, and the production build.

