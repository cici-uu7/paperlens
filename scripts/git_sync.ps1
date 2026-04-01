param(
    [string]$Message = "",
    [switch]$SkipTests,
    [switch]$NoPush,
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    & git @Args
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Args -join ' ') failed with exit code $LASTEXITCODE"
    }
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
Set-Location $repoRoot

$insideRepo = (& git rev-parse --is-inside-work-tree 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $insideRepo -ne "true") {
    throw "The current directory is not inside a git repository: $repoRoot"
}

$branch = (& git branch --show-current).Trim()
if (-not $branch) {
    throw "Could not determine the current branch."
}

$remoteUrl = (& git remote get-url origin 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or -not $remoteUrl) {
    throw "Remote 'origin' is not configured. Add it before using this script."
}

if (-not $Message) {
    $Message = "sync: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
}

$python = $PythonPath.Trim()
if (-not $python) {
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $python = $venvPython
    }
}

if (-not $SkipTests) {
    if ($python) {
        Write-Host "[1/4] Running tests with $python" -ForegroundColor Cyan
        & $python -m pytest -q
        if ($LASTEXITCODE -ne 0) {
            throw "Tests failed. Re-run with -SkipTests if you intentionally want to bypass validation."
        }
    }
    else {
        Write-Host "[1/4] No Python runtime found. Skipping tests." -ForegroundColor Yellow
    }
}
else {
    Write-Host "[1/4] Skipping tests by request." -ForegroundColor Yellow
}

Write-Host "[2/4] Staging changes" -ForegroundColor Cyan
Invoke-Git -Args @("add", "-A")

$cachedDiff = (& git diff --cached --name-only).Trim()
if (-not $cachedDiff) {
    Write-Host "No staged changes found. Nothing to commit." -ForegroundColor Yellow
    exit 0
}

Write-Host "[3/4] Creating commit: $Message" -ForegroundColor Cyan
Invoke-Git -Args @("commit", "-m", $Message)

if ($NoPush) {
    Write-Host "Commit created locally. Push skipped by request." -ForegroundColor Green
    exit 0
}

Write-Host "[4/4] Pushing branch '$branch' to origin" -ForegroundColor Cyan
$upstream = (& git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>$null).Trim()
if ($LASTEXITCODE -eq 0 -and $upstream) {
    Invoke-Git -Args @("push")
}
else {
    Invoke-Git -Args @("push", "-u", "origin", $branch)
}

Write-Host "Sync complete." -ForegroundColor Green
