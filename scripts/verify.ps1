[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$CoreOnly,
    [switch]$ClaimsOnly,
    [switch]$Interop,
    [switch]$ReproduceAcceleration,
    [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMdd-HHmmss")
$verificationRoot = Join-Path $repoRoot ".verification\$stamp"
$failures = [System.Collections.Generic.List[string]]::new()
$results = [System.Collections.Generic.List[object]]::new()

if ($Interop -and ($CoreOnly -or $ClaimsOnly)) {
    throw "-Interop requires the full profile; do not combine it with -CoreOnly or -ClaimsOnly"
}

function Invoke-Check {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][scriptblock]$Action
    )
    Write-Host "`n==> $Name" -ForegroundColor Cyan
    $started = [DateTimeOffset]::UtcNow
    try {
        & $Action
        if ($LASTEXITCODE -ne 0) {
            throw "process exited with code $LASTEXITCODE"
        }
        $elapsed = ([DateTimeOffset]::UtcNow - $started).TotalSeconds
        $results.Add([pscustomobject]@{ Name = $Name; Status = "PASS"; Seconds = [math]::Round($elapsed, 2) })
    }
    catch {
        $elapsed = ([DateTimeOffset]::UtcNow - $started).TotalSeconds
        $message = "$Name`: $($_.Exception.Message)"
        $failures.Add($message)
        $results.Add([pscustomobject]@{ Name = $Name; Status = "FAIL"; Seconds = [math]::Round($elapsed, 2) })
        Write-Host $message -ForegroundColor Red
    }
}

function Require-Command {
    param([Parameter(Mandatory)][string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "required command '$Name' is not available"
    }
}

function Resolve-NpmCommand {
    $command = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $command) {
        $command = Get-Command npm -ErrorAction SilentlyContinue
    }
    if (-not $command) {
        throw "required command 'npm' is not available"
    }
    return $command.Source
}

New-Item -ItemType Directory -Force -Path $verificationRoot | Out-Null
$originalLocation = Get-Location
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
$env:PYTHONPATH = (Join-Path $repoRoot "discolab")

try {
    Set-Location $repoRoot
    Require-Command python

    if ($Install) {
        Invoke-Check "Install backend dependencies" {
            python -m pip install -r .\backend\requirements-dev.txt
        }
        Invoke-Check "Install discolab and SDK" {
            python -m pip install -e ".\discolab[dev]"
        }
        if (-not $CoreOnly) {
            Invoke-Check "Install frontend dependencies" {
                $npmCommand = Resolve-NpmCommand
                Push-Location .\frontend
                try { & $npmCommand ci } finally { Pop-Location }
            }
        }
    }

    $evidenceArgs = @("-m", "scripts.verify_evidence", "--root", $repoRoot)
    if ($ClaimsOnly) { $evidenceArgs += "--claims-only" }
    Invoke-Check "Evidence claims, sealed study, and deterministic reproduction" {
        python @evidenceArgs
    }

    if ($ReproduceAcceleration) {
        $accelerationOutput = Join-Path $verificationRoot "acceleration-reproduction"
        Invoke-Check "Full selective-escalation reproduction" {
            Push-Location .\discolab
            try {
                python -m discolab.escalation --out $accelerationOutput
            }
            finally { Pop-Location }
            python -m scripts.verify_evidence --root $repoRoot --claims-only `
                --acceleration-summary (Join-Path $accelerationOutput "summary.json")
        }
    }

    if (-not $ClaimsOnly) {
        Invoke-Check "Backend tests" {
            Push-Location .\backend
            try {
                $base = Join-Path $verificationRoot "pytest-backend"
                python -m pytest tests -q -p no:cacheprovider --basetemp $base
            }
            finally { Pop-Location }
        }
        Invoke-Check "Discovery lab and Python SDK tests" {
            Push-Location .\discolab
            try {
                $base = Join-Path $verificationRoot "pytest-discolab"
                python -m pytest -q -p no:cacheprovider --basetemp $base
            }
            finally { Pop-Location }
        }

        if (-not $CoreOnly) {
            Invoke-Check "Frontend typecheck and production build" {
                $npmCommand = Resolve-NpmCommand
                Push-Location .\frontend
                try {
                    & $npmCommand run typecheck
                    if ($LASTEXITCODE -ne 0) { throw "frontend typecheck failed" }
                    & $npmCommand run build
                }
                finally { Pop-Location }
            }
            Invoke-Check "Rust formatting, lint and tests" {
                Require-Command cargo
                cargo fmt --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml -- --check
                if ($LASTEXITCODE -ne 0) { throw "cargo fmt failed" }
                cargo clippy --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml --all-targets -- -D warnings
                if ($LASTEXITCODE -ne 0) { throw "cargo clippy failed" }
                cargo test --manifest-path .\sdk\rust\eigenbrains-sdk\Cargo.toml
            }
            Invoke-Check "Julia tests" {
                Require-Command julia
                julia --project=.\sdk\julia -e 'using Pkg; Pkg.instantiate(); Pkg.test()'
            }
            if ($Interop) {
                Invoke-Check "Python-Rust-Julia interoperability proof" {
                    python -m sdk.interop.demo --root (Join-Path $verificationRoot "interop")
                }
            }
        }
    }
}
finally {
    Set-Location $originalLocation
    Write-Host "`nVerification summary" -ForegroundColor Cyan
    $results | Format-Table -AutoSize
    if (-not $KeepArtifacts -and (Test-Path -LiteralPath $verificationRoot)) {
        $resolvedRoot = (Resolve-Path -LiteralPath $repoRoot).Path
        $resolvedTarget = (Resolve-Path -LiteralPath $verificationRoot).Path
        if (-not $resolvedTarget.StartsWith((Join-Path $resolvedRoot ".verification"), [StringComparison]::OrdinalIgnoreCase)) {
            throw "refusing to remove verification output outside the repository"
        }
        Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
    }
}

if ($failures.Count -gt 0) {
    Write-Host "`n$($failures.Count) verification step(s) failed:" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "- $_" -ForegroundColor Red }
    exit 1
}

Write-Host "`nAll requested offline verification steps passed." -ForegroundColor Green
