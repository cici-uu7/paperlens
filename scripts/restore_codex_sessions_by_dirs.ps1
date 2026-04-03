[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Cwd,

    [string]$SourceProvider = "custom",

    [string]$TargetProvider = "openai",

    [switch]$OtherProviders,

    [switch]$DryRun,

    [switch]$StopOnError
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$cloneScript = Join-Path $scriptRoot "clone_codex_sessions.py"
if (-not (Test-Path -LiteralPath $cloneScript)) {
    throw "Missing clone script: $cloneScript"
}

$python = Get-Command python -ErrorAction Stop
$resolvedDirs = New-Object System.Collections.Generic.List[string]

foreach ($dir in $Cwd) {
    $resolved = Resolve-Path -LiteralPath $dir -ErrorAction Stop
    foreach ($match in $resolved) {
        $resolvedDirs.Add($match.Path)
    }
}

$resumeIndex = @{}
$hadFailure = $false

foreach ($dir in $resolvedDirs) {
    Write-Host ""
    Write-Host ("==> " + $dir) -ForegroundColor Cyan

    $args = @(
        $cloneScript,
        "--cwd", $dir,
        "--target-provider", $TargetProvider
    )
    if ($OtherProviders) {
        $args += "--other-providers"
    }
    else {
        $args += "--source-provider"
        $args += $SourceProvider
    }
    if ($DryRun) {
        $args += "--dry-run"
    }

    $output = & $python.Source @args 2>&1
    $exitCode = $LASTEXITCODE

    foreach ($line in $output) {
        Write-Host $line
        $text = $line.ToString()

        if ($text -match '^\[exists\]\s+([0-9a-fA-F-]+)\b') {
            if (-not $resumeIndex.ContainsKey($dir)) {
                $resumeIndex[$dir] = New-Object System.Collections.Generic.HashSet[string]
            }
            [void]$resumeIndex[$dir].Add($Matches[1])
            continue
        }

        if ($text -match '^\s*codex resume\s+([0-9a-fA-F-]+)\s*$') {
            if (-not $resumeIndex.ContainsKey($dir)) {
                $resumeIndex[$dir] = New-Object System.Collections.Generic.HashSet[string]
            }
            [void]$resumeIndex[$dir].Add($Matches[1])
        }
    }

    if ($exitCode -ne 0) {
        $hadFailure = $true
        if ($StopOnError) {
            exit $exitCode
        }
    }
}

Write-Host ""
if ($DryRun) {
    Write-Host "Dry run complete."
}
else {
    Write-Host "Restore complete."
}

if ($resumeIndex.Count -gt 0) {
    Write-Host ""
    Write-Host "Resume commands:"
    foreach ($dir in $resolvedDirs) {
        if (-not $resumeIndex.ContainsKey($dir)) {
            continue
        }
        foreach ($sessionId in $resumeIndex[$dir]) {
            Write-Host ("[" + $dir + "] codex resume " + $sessionId)
        }
    }
}
elseif (-not $hadFailure) {
    Write-Host "No matching sessions were found."
}

if ($hadFailure) {
    exit 1
}
