# Contributing

Contributions should make the system more measurable, reproducible, or usable
without weakening evidence boundaries. Small, reviewable changes are preferred.

## Before editing

```powershell
git status --short
git branch --show-current
git fetch origin
```

Use an isolated worktree when another contributor or agent is active. Never
switch branches in a checkout another process is using. Existing changes belong
to their author; do not stage, revert, format, or delete them unless ownership
is explicit.

## Repository boundaries

| Change | Primary files | Required synchronization |
|---|---|---|
| HTTP endpoint | `backend/app/api/` | backend tests, frontend types/client, API docs |
| Provider | `backend/app/providers/` | instrumentation, mocked adapter tests, pricing provenance |
| Policy/fallback | `backend/app/capabilities/`, `fallback/` | audit events and hard-constraint tests |
| Benchmark method | `backend/app/benchmark/`, `benchmark/` | frozen config, raw/derived distinction, methodology |
| Scientific method | `discolab/prereg.yaml`, numerical core | protocol version, invariants, result compatibility |
| Agent permission | Omnigent configs and MCP allow-lists | least-privilege review and end-to-end test |
| SDK protocol | Python RPC plus `sdk/protocol/` | Rust/Julia wrappers, live bridge tests, contract docs |
| Frontend view | `frontend/src/` | typecheck, build, accessibility, visual QA |

Do not place scientific logic in the UI or language wrappers. Python remains the
authoritative implementation for shared SDK semantics.

## Implementation standards

- Make invalid state unrepresentable or fail loudly at the boundary.
- Keep raw observations immutable.
- Use explicit units and `None`/`null` for unknown quantities.
- Pass model calls through shared instrumentation.
- Keep provider credentials environment-only.
- Add deterministic tests for every state transition and failure mode.
- Seed stochastic tests and resample the correct unit.
- Avoid hidden retries in experimental code.
- Prefer standard, inspectable formats over opaque serialization.
- Document non-obvious decisions near the implementation and in the relevant
  guide.

## Testing matrix

### Backend

```powershell
Set-Location .\backend
$env:PYTHONPATH = "."
$testRoot = Join-Path $PWD (".tmp-pytest-" + [guid]::NewGuid())
python -m pytest tests -q --basetemp $testRoot
Set-Location ..
```

### Discovery lab and Python SDK

```powershell
Set-Location .\discolab
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
$testRoot = Join-Path $PWD (".tmp-pytest-" + [guid]::NewGuid())
python -m pytest -q --basetemp $testRoot
Set-Location ..
```

### Frontend

```powershell
Set-Location .\frontend
npm ci
npm run typecheck
npm run build
Set-Location ..
```

### Rust

```powershell
cargo fmt --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml -- --check
cargo clippy --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml
```

### Julia

```powershell
julia --project=.\sdk\julia -e 'using Pkg; Pkg.instantiate(); Pkg.test()'
```

Run the smallest relevant set while iterating and the full affected matrix
before handoff. Live provider calls are never part of the default suite.

## Adding an experiment

1. Write a falsifiable hypothesis and null.
2. Define experimental unit, comparator, primary metric, unit, and SESOI.
3. Freeze splits, seeds, analysis, exclusions, and stopping rule.
4. Add semantic output schemas.
5. Run development data only.
6. Validate failures as well as success paths.
7. Obtain explicit approval before held-out or paid execution.
8. Preserve raw observations and generate analysis from them.
9. Report uncertainty and unresolved comparisons.
10. Reproduce at least one run independently.

## Documentation standards

- Link to repository-relative files.
- State the directory from which a command runs.
- Distinguish PowerShell from Bash.
- Avoid fixed test counts unless generated and maintained automatically.
- Label sample commands that spend money or reveal held-out data.
- Include limitations adjacent to claims.
- Prefer equations plus plain-language interpretation.
- Use stable names from code, not informal aliases.

## Commits

Use small conventional commits:

```text
feat(sdk): add content-addressed evidence export
fix(stats): preserve run clustering in bootstrap
docs(research): document held-out approval protocol
test(policy): reject expired capability lease
```

The body should explain the invariant protected and the verification performed.
Never mention assistant identities in commit messages.

Before pushing:

```powershell
git diff --check
git status --short
git log -3 --oneline
```

Never force-push a shared branch. Never commit credentials, local toolchain
caches, virtual environments, `node_modules`, or generated build trees.
