param(
    [int]$ApiPort = 8000,
    [int]$UiPort = 8501,
    [ValidateSet("api", "auto", "local")]
    [string]$UiMode = "api",
    [int]$StartupTimeoutSeconds = 30,
    [switch]$NoBrowser,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Test-TcpPortInUse {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    foreach ($listener in $listeners) {
        if ($listener.Port -eq $Port) {
            return $true
        }
    }
    return $false
}

function Test-HttpReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        $request = [System.Net.WebRequest]::Create($Url)
        $request.Method = "GET"
        $request.Timeout = 2000
        $response = $request.GetResponse()
        $response.Close()
        return $true
    }
    catch {
        return $false
    }
}

function Wait-HttpReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpReady -Url $Url) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Test-PaperLensApiReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        $response = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 3
        return ($response.status -eq "ok" -and $null -ne $response.answer_backend)
    }
    catch {
        return $false
    }
}

function Convert-ToEncodedPowerShellCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WindowTitle,
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string]$PythonPath,
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    $escapedTitle = $WindowTitle.Replace("'", "''")
    $escapedRepoRoot = $RepoRoot.Replace("'", "''")
    $escapedPython = $PythonPath.Replace("'", "''")
    $renderedArgs = ($Args | ForEach-Object { "'$($_.Replace("'", "''"))'" }) -join " "
    $command = @"
`$Host.UI.RawUI.WindowTitle = '$escapedTitle'
Set-Location -LiteralPath '$escapedRepoRoot'
& '$escapedPython' $renderedArgs
if (`$LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Command exited with code `$LASTEXITCODE." -ForegroundColor Red
}
"@

    return [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
}

function Start-ServerWindow {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WindowTitle,
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string]$PythonPath,
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    $encodedCommand = Convert-ToEncodedPowerShellCommand `
        -WindowTitle $WindowTitle `
        -RepoRoot $RepoRoot `
        -PythonPath $PythonPath `
        -Args $Args

    return Start-Process `
        -FilePath "powershell.exe" `
        -WorkingDirectory $RepoRoot `
        -ArgumentList @(
            "-NoLogo",
            "-NoProfile",
            "-NoExit",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            $encodedCommand
        ) `
        -PassThru
}

function Get-DemoStatePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    return Join-Path $RepoRoot ".tmp\paperlens_demo_state.json"
}

function Save-DemoState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [int]$ApiPort,
        [Parameter(Mandatory = $true)]
        [int]$UiPort,
        [Parameter(Mandatory = $true)]
        [string]$ApiUrl,
        [Parameter(Mandatory = $true)]
        [string]$UiLaunchUrl,
        [int]$ApiWindowPid = 0,
        [int]$UiWindowPid = 0,
        [bool]$ApiManaged = $false,
        [bool]$UiManaged = $false
    )

    $statePath = Get-DemoStatePath -RepoRoot $RepoRoot
    $stateDir = Split-Path -Parent $statePath
    if (-not (Test-Path -LiteralPath $stateDir)) {
        New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
    }

    $payload = [ordered]@{
        started_at      = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        api_port        = $ApiPort
        ui_port         = $UiPort
        api_url         = $ApiUrl
        ui_launch_url   = $UiLaunchUrl
        api_managed     = $ApiManaged
        ui_managed      = $UiManaged
        api_window_pid  = if ($ApiWindowPid -gt 0) { $ApiWindowPid } else { $null }
        ui_window_pid   = if ($UiWindowPid -gt 0) { $UiWindowPid } else { $null }
    }

    $payload | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
}

function Get-ChromePath {
    $candidates = @(
        "C:\Program Files\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    $chromeCommand = Get-Command chrome.exe -ErrorAction SilentlyContinue
    if ($chromeCommand) {
        return $chromeCommand.Source
    }

    return $null
}

function Open-UiBrowser {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    $chromePath = Get-ChromePath
    if ($chromePath) {
        Start-Process -FilePath $chromePath -ArgumentList @("--new-window", $Url) | Out-Null
        return "Chrome"
    }

    Start-Process -FilePath $Url | Out-Null
    return "default browser"
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python runtime not found at $pythonPath. Create .venv and install dependencies first."
}

$apiBaseUrl = "http://127.0.0.1:$ApiPort"
$apiHealthUrl = "$apiBaseUrl/health"
$uiBaseUrl = "http://127.0.0.1:$UiPort/"
$uiLaunchUrl = "${uiBaseUrl}?mode=$UiMode&api_base_url=$([uri]::EscapeDataString($apiBaseUrl))"

$apiArgs = @(
    "-m",
    "uvicorn",
    "app.api.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    $ApiPort.ToString(),
    "--reload"
)

$uiArgs = @(
    "-m",
    "streamlit",
    "run",
    "ui/app.py",
    "--server.headless",
    "true",
    "--server.address",
    "127.0.0.1",
    "--server.port",
    $UiPort.ToString()
)

$apiPortInUse = Test-TcpPortInUse -Port $ApiPort
$uiPortInUse = Test-TcpPortInUse -Port $UiPort
$apiReusable = $false
if ($apiPortInUse) {
    $apiReusable = Test-PaperLensApiReady -Url $apiHealthUrl
}

if ($DryRun) {
    Write-Host "Repo root: $repoRoot" -ForegroundColor Cyan
    Write-Host "Python: $pythonPath" -ForegroundColor Cyan
    Write-Host "API URL: $apiBaseUrl" -ForegroundColor Cyan
    Write-Host "UI URL: $uiLaunchUrl" -ForegroundColor Cyan
    Write-Host "API command: & '$pythonPath' $($apiArgs -join ' ')" -ForegroundColor DarkGray
    Write-Host "UI command:  & '$pythonPath' $($uiArgs -join ' ')" -ForegroundColor DarkGray
    Write-Host "API port in use: $apiPortInUse" -ForegroundColor DarkGray
    Write-Host "UI port in use: $uiPortInUse" -ForegroundColor DarkGray
    if ($apiPortInUse) {
        Write-Host "API looks reusable: $apiReusable" -ForegroundColor DarkGray
    }
    exit 0
}

$apiWindowProcess = $null
$uiWindowProcess = $null
$apiManaged = $false
$uiManaged = $false

if ($apiPortInUse -or $uiPortInUse) {
    if ($apiPortInUse -and $uiPortInUse) {
        if (-not $apiReusable) {
            throw "Port $ApiPort is already in use by a service that does not look like the PaperLens API."
        }
        Write-Host "API and UI ports are already in use. Reusing the existing services." -ForegroundColor Yellow
    }
    elseif ($apiPortInUse -and -not $uiPortInUse) {
        if (-not $apiReusable) {
            throw "Port $ApiPort is already in use by a service that does not look like the PaperLens API."
        }

        Write-Host "API port $ApiPort is already serving PaperLens. Reusing the existing API and starting only the UI." -ForegroundColor Yellow
        Write-Host "Starting PaperLens UI on http://127.0.0.1:$UiPort/" -ForegroundColor Cyan
        $uiWindowProcess = Start-ServerWindow -WindowTitle "PaperLens UI" -RepoRoot $repoRoot -PythonPath $pythonPath -Args $uiArgs
        $uiManaged = $true

        Save-DemoState `
            -RepoRoot $repoRoot `
            -ApiPort $ApiPort `
            -UiPort $UiPort `
            -ApiUrl $apiBaseUrl `
            -UiLaunchUrl $uiLaunchUrl `
            -ApiManaged $apiManaged `
            -UiManaged $uiManaged `
            -ApiWindowPid 0 `
            -UiWindowPid $uiWindowProcess.Id
    }
    elseif (-not $apiPortInUse -and $uiPortInUse) {
        throw "Port $UiPort is already in use. Stop the conflicting process or run with a different port."
    }
    else {
        throw "One or more requested ports are already in use."
    }
}
else {
    Write-Host "Starting PaperLens API on $apiBaseUrl" -ForegroundColor Cyan
    $apiWindowProcess = Start-ServerWindow -WindowTitle "PaperLens API" -RepoRoot $repoRoot -PythonPath $pythonPath -Args $apiArgs
    $apiManaged = $true

    Write-Host "Starting PaperLens UI on http://127.0.0.1:$UiPort/" -ForegroundColor Cyan
    $uiWindowProcess = Start-ServerWindow -WindowTitle "PaperLens UI" -RepoRoot $repoRoot -PythonPath $pythonPath -Args $uiArgs
    $uiManaged = $true

    Save-DemoState `
        -RepoRoot $repoRoot `
        -ApiPort $ApiPort `
        -UiPort $UiPort `
        -ApiUrl $apiBaseUrl `
        -UiLaunchUrl $uiLaunchUrl `
        -ApiManaged $apiManaged `
        -UiManaged $uiManaged `
        -ApiWindowPid $apiWindowProcess.Id `
        -UiWindowPid $uiWindowProcess.Id
}

$apiReady = Wait-HttpReady -Url $apiHealthUrl -TimeoutSeconds $StartupTimeoutSeconds
$uiReady = Wait-HttpReady -Url $uiBaseUrl -TimeoutSeconds $StartupTimeoutSeconds

if ($apiReady) {
    Write-Host "API ready: $apiHealthUrl" -ForegroundColor Green
}
else {
    Write-Host "API did not become ready within $StartupTimeoutSeconds seconds." -ForegroundColor Yellow
}

if ($uiReady) {
    Write-Host "UI ready: $uiBaseUrl" -ForegroundColor Green
}
else {
    Write-Host "UI did not become ready within $StartupTimeoutSeconds seconds." -ForegroundColor Yellow
}

if (-not $NoBrowser -and $uiReady) {
    $browserName = Open-UiBrowser -Url $uiLaunchUrl
    Write-Host "Opened ${browserName}: $uiLaunchUrl" -ForegroundColor Green
}
elseif (-not $NoBrowser) {
    Write-Host "Skipping browser launch because the UI endpoint is not ready yet." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "PaperLens startup summary" -ForegroundColor Cyan
Write-Host "  API: $apiBaseUrl"
Write-Host "  UI:  $uiLaunchUrl"
Write-Host "Close the dedicated API/UI PowerShell windows to stop the services."
