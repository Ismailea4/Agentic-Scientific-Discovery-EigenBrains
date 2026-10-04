# Operations runbook

This runbook covers normal startup, verification, experiment execution,
shutdown, and incident handling. It does not authorize provider spending or
held-out evaluation; those require the experiment-specific approval and limits.

## Component matrix

| Component | Default address/process | Persistent output |
|---|---|---|
| FastAPI backend | `127.0.0.1:8000` | optional logs, metrics, eval artifacts |
| Vite frontend | `localhost:5173` | production build under `frontend/dist/` |
| Omnigent server | `127.0.0.1:6810` by example | lab-local SQLite and artifacts |
| Omnigent host | background process attached to server | host/server logs |
| SDK JSONL bridge | child process over stdin/stdout | research-run directory |

## Safe startup order

1. Confirm the intended Git branch, commit, and worktree status.
2. Activate the correct Python environment.
3. Set only required environment variables.
4. Run `.\scripts\verify.ps1 -CoreOnly` or the full offline verifier.
5. Start the backend and verify `/health`.
6. Start the frontend and perform a browser smoke test.
7. Start Omnigent only if an agentic discovery run is needed.
8. Enable provider credentials only for an explicitly authorized live run.

This order isolates deterministic failures before external cost or provider
state enters the system.

## Backend operation

Start:

```powershell
Set-Location .\backend
$env:PYTHONPATH = "."
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health and contract checks:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/system/capabilities
Invoke-RestMethod http://127.0.0.1:8000/api/system/architectures
```

Empty catalogues are valid. A `500` should emit a structured error without
exposing the exception body, prompt, credential, or request headers.

Configuration variables:

| Variable | Default | Purpose |
|---|---|---|
| `APP_HOST` | `127.0.0.1` | bind address |
| `APP_PORT` | `8000` | API port |
| `CORS_ORIGINS` | local Vite origins | comma-separated browser origins |
| `LOG_LEVEL` | `INFO` | log threshold |
| `LOG_FORMAT` | `console` | `console` or `json` |
| `LOG_FILE_ENABLED` | `false` | optional local file sink |
| `LOG_FILE_PATH` | `data/logs/app.jsonl` | file sink path |
| `METRICS_OUTPUT_DIR` | `data/metrics` | normalized call observations |
| `EVAL_OUTPUT_DIR` | `data/evals` | evaluation artifacts |

When running from `backend/`, relative output paths resolve from that directory
unless overridden.

## Frontend operation

```powershell
Set-Location .\frontend
npm ci
npm run typecheck
npm run build
npm run dev
```

Verification:

- browser reaches `http://localhost:5173`;
- navigation preserves the last home chapter;
- left sidebar expands on pointer presence and collapses otherwise;
- dark and light themes remain readable;
- Team panel opens and closes;
- live catalogue failures display a controlled state;
- browser console contains no uncaught errors.

The screenshot script under `frontend/scripts/` is for visual QA. Screenshots
are not benchmark or scientific evidence.

## SDK bridge operation

Manual bridge invocation:

```powershell
python -m discolab.rpc --root .\study --actor external-sdk
```

The bridge reads one JSON request per line and writes exactly one JSON response
per line. Do not write diagnostic text to stdout; it would corrupt the protocol.
Diagnostics belong on stderr.

The bridge is stateful for an open evidence run. A transport interruption may
leave a run incomplete. Inspect state before retrying a mutating request; never
assume a timed-out mutation failed to land.

## Omnigent laboratory operation

### Start

Run from Git Bash inside `discolab/`:

```bash
bash scripts/start_lab.sh main 6810
```

The script:

- sets `DISCOLAB_HOME=lab_home/main`;
- creates the lab and Omnigent directories;
- verifies `ANTHROPIC_API_KEY` exists without printing it;
- initializes the ledger when absent;
- starts server and host as background processes;
- waits for server health and an online host;
- writes process IDs and logs beneath the lab home.

### Run a session

```bash
export DISCOLAB_HOME="$PWD/lab_home/main"
.venv/Scripts/python scripts/run_session.py \
  --port 6810 \
  --timeout 3600 \
  --idle-grace 30 \
  --prompt "Run one development-stage discovery round."
```

The driver records session events in `omnigent_events.jsonl`. Human approval
requests are presented in the terminal or web interface. A noninteractive
request with no response is declined after the configured wait.

### Inspect

```bash
.venv/Scripts/python -m discolab.cli state
.venv/Scripts/python -m discolab.cli trace
.venv/Scripts/python -m discolab.cli result E1
```

### Recover an interrupted experiment

Inspect the ledger and run directory first. If the selected experiment never
completed and no worker remains active:

```bash
.venv/Scripts/python -m discolab.cli abort E1 "worker interrupted after operator verification"
```

Do not abort merely because a long numerical run is quiet. Verify the worker
process and artifact timestamps.

### Stop

```bash
bash scripts/stop_lab.sh main
```

Confirm the port is released and preserve the lab directory before cleanup.

## Provider-backed benchmark gate

Before any live calls, record:

- authorization and owner;
- exact models/providers;
- corpus and split;
- prompt/evaluator versions;
- temperature and output cap;
- maximum calls overall and per model;
- provider request ceiling;
- concurrency;
- conservative dollar ceiling;
- retry policy;
- stop conditions.

Recommended environment-limit pattern:

```powershell
$env:MAX_BENCHMARK_SPEND_USD = "0.20"
$env:MAX_TOTAL_INFERENCE_CALLS = "245"
$env:MAX_PROVIDER_REQUESTS = "246"
$env:MAX_CONCURRENCY = "1"
```

These values are examples only. The approved experiment configuration is
authoritative. Operational headroom is not permission to add experiments.

After a live run:

1. stop at the approved boundary;
2. preserve raw observations before analysis;
3. classify provider availability separately from model correctness;
4. calculate actual and unknown cost separately;
5. validate case coverage and pairing;
6. generate derived artifacts offline;
7. freeze and report before launching another stage.

## Logging and privacy

Safe logs may contain:

- request/run IDs;
- event names;
- duration;
- status and normalized error class;
- provider/model identifiers;
- token counts and known cost;
- non-sensitive experiment metadata.

Logs must not contain:

- API-key values;
- authorization headers or cookies;
- prompts or private documents;
- raw environment dumps;
- browser profiles;
- user credential-store contents.

Use the shared redaction utilities. Redaction is defense in depth, not
permission to log sensitive data first.

## Backup and archival

Before moving or archiving a study:

1. stop writers;
2. validate every completed run;
3. preserve the protocol and commit hash;
4. include raw, derived, and analysis artifacts with manifests;
5. exclude credentials, virtual environments, caches, build directories, and
   provider-response caches that are not approved for sharing;
6. compute an archive hash;
7. test extraction into a new directory;
8. run bundle validation or the documented integrity checks.

## Incident response

### Suspected credential exposure

1. Stop the process and disconnect the affected credential.
2. Rotate/revoke it at the provider.
3. Do not paste the value into an issue, chat, or log.
4. Determine whether it entered Git history, artifacts, logs, screenshots, or
   build output.
5. Remove public exposure using the repository host's secret-remediation
   procedure; ordinary file deletion does not remove Git history.
6. Document impact without reproducing the secret.

### Corrupted evidence

1. Mark the run invalid or rejected; do not repair raw bytes in place.
2. Preserve the corrupted copy for audit if safe.
3. identify the first failed hash/schema/event-chain check;
4. trace parent/child artifacts;
5. rerun under a new run ID;
6. document whether conclusions changed.

### Provider drift or outage

1. Preserve status, timestamp, model ID, and normalized error.
2. Do not label it model-intelligence failure.
3. Stop when the retry/provider-request ceiling is reached.
4. Rerun only under a new recorded stage if the protocol allows it.
5. Report both conditional quality and operational quality.
