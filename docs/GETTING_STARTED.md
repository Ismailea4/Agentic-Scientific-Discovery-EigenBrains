# Getting started

This guide takes a clean checkout to a verified local installation. The API/UI,
the discovery laboratory, and the language SDKs can be used independently.
Install only the components you need.

All commands below start at the repository root. PowerShell examples are shown
because the project is verified on Windows; Git Bash is required for the
current Omnigent start/stop scripts.

## Fastest offline acceptance check

After installing the declared component dependencies, run the repository-level
verifier from the root:

```powershell
.\scripts\verify.ps1
```

It derives the published acceleration values from their machine-readable
artifacts, performs a fresh deterministic SDK run/reproduction/tamper check,
and tests the Python, frontend, Rust, and Julia components. Use `-CoreOnly`
when only Python is installed or `-ClaimsOnly` for a fast evidence-integrity
check. See [Verification and reproduction](VERIFICATION.md) for profiles and
interpretation limits.

## Prerequisites

Required for the API and scientific core:

- Git;
- Python 3.12 or newer;
- PowerShell 7 or Windows PowerShell 5.1.

Required by component:

| Component | Additional requirement |
|---|---|
| Frontend | Node.js and npm compatible with the committed lockfile |
| Omnigent lab | Git Bash, Omnigent 0.16.0, an Anthropic credential in the process environment |
| Rust SDK | Stable Rust toolchain with Cargo, rustfmt, and Clippy |
| Julia SDK | Julia 1.10 or newer; the verified local toolchain may be newer |

The repository never needs credential values in committed files. Provider
credentials are read from process environment variables only.

## Clone and inspect

```powershell
git clone https://github.com/Ismailea4/Agentic-Scientific-Discovery-EigenBrains.git
Set-Location Agentic-Scientific-Discovery-EigenBrains
git status --short
git rev-parse HEAD
```

Record the commit hash in any experimental report. A clean `git status` is the
preferred starting point for a reproducible run. If the tree is intentionally
dirty, preserve the diff and record `git.dirty=true` in provenance.

## Backend API

Create an isolated environment and install development dependencies:

```powershell
python -m venv .venv-backend
& .\.venv-backend\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\backend\requirements-dev.txt
```

Run the offline suite:

```powershell
Set-Location .\backend
$env:PYTHONPATH = "."
$testRoot = Join-Path $PWD (".tmp-pytest-" + [guid]::NewGuid())
python -m pytest tests -q --basetemp $testRoot
Set-Location ..
```

Start the API:

```powershell
Set-Location .\backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify from another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Start-Process http://127.0.0.1:8000/docs
```

Expected health status is `ok`. The capability and architecture registries are
empty until application code registers entries; empty catalogues are not an
installation failure.

## Frontend

Use `npm ci`, not `npm install`, for a lockfile-exact installation:

```powershell
Set-Location .\frontend
npm ci
npm run typecheck
npm run build
npm run dev
```

Open `http://localhost:5173`. The Vite development server proxies `/api` and
`/health` to `http://localhost:8000`; keep the backend running for live
catalogue and health views. Some cinematic narrative surfaces intentionally use
clearly marked fixtures.

## Scientific laboratory and Python SDK

The `discolab` package requires Python 3.12+:

```powershell
Set-Location .\discolab
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
$testRoot = Join-Path $PWD (".tmp-pytest-" + [guid]::NewGuid())
python -m pytest -q --basetemp $testRoot
Set-Location ..
```

The thread limits reduce oversubscription and improve repeatability of timing
measurements. They do not guarantee identical wall time across machines.

Run the generic Python SDK example:

```powershell
python .\sdk\examples\research_evidence.py
```

It creates a local `study/research-runs/` evidence tree. Inspect the returned
run identifier with:

```powershell
eigenbrains-sdk --root .\study inspect RUN-XXXXXXXXXXXX
eigenbrains-sdk --root .\study validate RUN-XXXXXXXXXXXX
```

Use the actual identifier printed by the example.

## Rust SDK

```powershell
cargo fmt --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml -- --check
cargo clippy --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml
cargo run --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml --example evidence -- .\study-rust
```

The Rust client launches the Python bridge. Ensure `discolab` is installed in
the Python selected by the client or use its explicit Python-path constructor
in source-checkout integrations.

## Julia SDK

```powershell
julia --project=.\sdk\julia -e 'using Pkg; Pkg.instantiate(); Pkg.test()'
julia --project=.\sdk\julia .\sdk\julia\examples\evidence.jl .\study-julia
```

Set `PYTHON` if the desired interpreter is not named `python`:

```powershell
$env:PYTHON = (Resolve-Path .\discolab\.venv\Scripts\python.exe)
```

## Omnigent discovery loop

Only proceed after the deterministic scientific core passes. The current
launcher is a Bash script and is best run from Git Bash:

```bash
cd discolab
export ANTHROPIC_API_KEY='set this in the shell; never commit it'
bash scripts/start_lab.sh main 6810
export DISCOLAB_HOME="$PWD/lab_home/main"
.venv/Scripts/python scripts/run_session.py \
  --port 6810 \
  --prompt "Run one development-stage discovery round and report all limitations."
.venv/Scripts/python -m discolab.cli trace
bash scripts/stop_lab.sh main
```

The human-approval gate fails closed: a confirmatory held-out run is declined
when nobody approves it. Do not bypass this protection for convenience.

## Configuration without secrets

Copy `.env.example` only if your local runner loads environment files safely;
otherwise set names directly in the shell. Supported non-secret settings
include:

- `APP_HOST`, `APP_PORT`, `CORS_ORIGINS`;
- `LOG_LEVEL`, `LOG_FORMAT`, `LOG_FILE_ENABLED`, `LOG_FILE_PATH`;
- `METRICS_OUTPUT_DIR`, `EVAL_OUTPUT_DIR`;
- provider model and base-URL selectors.

Credential variables include `OPENAI_API_KEY`, `GROQ_API_KEY`,
`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, and `OPENROUTER_API_KEY`. Never print
their values, include them in commands captured by provenance, or store them in
research artifacts.

## First-run acceptance checklist

- `scripts/verify.ps1` passes for every installed component.
- Backend tests pass offline.
- `/health` returns `status: ok`.
- Frontend typecheck and production build succeed.
- The browser loads the seven narrative chapters.
- `discolab` tests pass with deterministic seeds.
- A Python evidence run validates.
- Any installed Rust or Julia SDK passes its live bridge test.
- `git status --short` contains only changes you intentionally created.
