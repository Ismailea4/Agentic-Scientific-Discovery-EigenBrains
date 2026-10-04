# Troubleshooting

Diagnose from the narrowest boundary outward: environment, unit tests, local
process, protocol, then external provider. Preserve the exact command and
structured error; do not expose credentials while asking for help.

## PowerShell blocks `scripts/verify.ps1`

Run the repository verifier with a process-scoped policy bypass:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

This invocation does not weaken the persistent user or machine execution
policy. Do not change the global policy merely to run the verifier.

## Python cannot import `app` or `discolab`

Backend commands must run from `backend/` with `PYTHONPATH=.` or with the package
installed. SDK/lab commands require an editable `discolab` installation:

```powershell
python -m pip install -e .\discolab
python -c "import discolab; print(discolab.__file__)"
```

Verify that `python` is the expected environment:

```powershell
Get-Command python
python -c "import sys; print(sys.executable)"
```

## Pytest cannot use the system temporary directory

Provide a unique workspace-local base directory:

```powershell
$testRoot = Join-Path $PWD (".tmp-pytest-" + [guid]::NewGuid())
python -m pytest -q --basetemp $testRoot
```

Do not reuse a valuable directory as `--basetemp`; pytest may clear an existing
base directory.

## Numerical tests are slow or appear hung

Limit numerical-library threads before starting tests:

```powershell
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
```

Check for orphaned Python workers from an interrupted earlier run. Do not kill a
process until its command and ownership are identified.

## Frontend is blank

```powershell
Set-Location .\frontend
npm ci
npm run typecheck
npm run build
npm run dev
```

Then inspect:

- terminal build error;
- browser console;
- network requests to `/api` and `/health`;
- Vite port and URL;
- whether the backend is running on port 8000.

Use `npm ci` after lockfile changes. Do not commit `node_modules`.

## Backend health works but catalogues are empty

This is expected on a new process. Registries are in-memory and start empty.
The UI must distinguish “no registered evidence” from a network failure.

## Rust toolchain is installed but `cargo` is not found

For a toolchain installed on `F:` in the documented layout:

```powershell
$env:CARGO_HOME = "F:\toolchains\rust\cargo"
$env:RUSTUP_HOME = "F:\toolchains\rust\rustup"
$env:Path = "$env:CARGO_HOME\bin;$env:Path"
rustc --version
cargo --version
```

Persist the two home variables and Cargo bin path at user scope if desired.

## Julia reports a package UUID mismatch

Verify `Project.toml` uses the registry UUID. For JSON, the maintained package
used by this project is `JSON` with UUID
`682c06a0-de6a-54ab-a142-c8b1cf79cde6`. Do not substitute a guessed UUID.

Then instantiate:

```powershell
$env:JULIA_DEPOT_PATH = "F:\toolchains\julia-depot"
julia --project=.\sdk\julia -e 'using Pkg; Pkg.instantiate(); Pkg.test()'
```

## Julia depot permission failure

The depot must be writable because Julia creates locks, logs, compiled caches,
and package metadata. Point `JULIA_DEPOT_PATH` to a directory owned by the
current user. If a sandboxed runner needs a configured external depot, grant
only that test process the necessary write access.

## Rust fails while downloading crates

If dependencies are already cached, test without network:

```powershell
cargo test --offline --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml
```

If they are not cached, verify network and certificate configuration. Do not
disable TLS verification.

## Rust/Julia bridge closes without a response

Confirm:

1. selected Python can import `discolab`;
2. bridge stdout contains only JSONL responses;
3. Python errors appear on stderr;
4. protocol version matches the client;
5. the lab root is writable;
6. the open run belongs to the same bridge process.

Use the live bridge tests to isolate the failure before debugging research code.

## Omnigent host does not come online on Windows

Read, without publishing, the lab-local server and host logs under
`discolab/lab_home/<name>/.omnigent/`. Confirm Git Bash is used, the lab virtual
environment appears first on `PATH`, and `PYTHONUTF8=1` is active. The launcher
removes unrelated `srt` executables that Omnigent can mistake for a sandbox
runtime.

If native Windows fails at the runtime boundary after a reasonable diagnosis,
use WSL with Python 3.12 rather than weakening sandbox or policy behavior.

## Held-out execution is refused

This is a protection, not a bug. A confirmatory run requires:

- completed development-stage evidence for the hypothesis;
- an eligible selected experiment;
- explicit human approval.

Do not modify the guard or relabel held-out landscapes. If approval is declined
or times out, record that outcome and continue with development work only.

## Provider returns 429, 400, or intermittent failures

- `429` generally indicates rate or quota limitation, not an invalid key.
- `400` may indicate model availability, request shape, or provider policy.
- Intermittent failures remain provider-availability observations.

Never print the key while diagnosing. Preserve provider, model, HTTP status,
timestamp, and sanitized error class. Respect retry, request, concurrency, and
spend ceilings.

## Evidence validation reports a hash mismatch

Stop using the run as evidence. Do not update the manifest to match the changed
file. Preserve the state, identify the altered artifact, inspect lineage, mark
the run invalid/rejected as supported, and rerun under a new ID.

## Git credential manager does not appear

Retry the same narrow `git push origin <branch>` after confirming the branch and
remote. Do not embed credentials in the remote URL and never force-push to solve
an authentication prompt issue.
