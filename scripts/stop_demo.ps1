param(
    [int]$ApiPort = 8000,
    [int]$UiPort = 8501,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Get-DemoStatePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    return Join-Path $RepoRoot ".tmp\paperlens_demo_state.json"
}

function Get-ProcessCommandLine {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId
    )

    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $processInfo) {
        return ""
    }
    if ($null -eq $processInfo.CommandLine) {
        return ""
    }
    return [string]$processInfo.CommandLine
}

function Get-ChildProcessRecords {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ParentPid,
        [int]$Depth = 1
    )

    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ParentPid" -ErrorAction SilentlyContinue)
    $results = @()
    foreach ($child in $children) {
        $results += [PSCustomObject]@{
            Pid   = [int]$child.ProcessId
            Depth = $Depth
        }
        $results += Get-ChildProcessRecords -ParentPid ([int]$child.ProcessId) -Depth ($Depth + 1)
    }
    return $results
}

function Add-TargetRecord {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$TargetMap,
        [Parameter(Mandatory = $true)]
        [int]$TargetPid,
        [Parameter(Mandatory = $true)]
        [string]$Reason,
        [int]$Depth = 0
    )

    if ($TargetPid -le 0 -or $TargetPid -eq $PID) {
        return
    }

    if (-not $TargetMap.ContainsKey($TargetPid)) {
        $TargetMap[$TargetPid] = [PSCustomObject]@{
            Pid     = $TargetPid
            Depth   = $Depth
            Reasons = New-Object System.Collections.Generic.List[string]
        }
    }

    if ($Depth -gt $TargetMap[$TargetPid].Depth) {
        $TargetMap[$TargetPid].Depth = $Depth
    }

    if (-not $TargetMap[$TargetPid].Reasons.Contains($Reason)) {
        $TargetMap[$TargetPid].Reasons.Add($Reason) | Out-Null
    }
}

function Get-ListeningProcessRecords {
    param(
        [Parameter(Mandatory = $true)]
        [int[]]$Ports
    )

    $records = New-Object System.Collections.Generic.List[object]

    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        foreach ($port in $Ports) {
            $connections = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
            foreach ($connection in $connections) {
                $records.Add([PSCustomObject]@{
                    Port = [int]$port
                    Pid  = [int]$connection.OwningProcess
                })
            }
        }
    }

    if ($records.Count -eq 0) {
        $lines = @(netstat -ano -p tcp)
        foreach ($line in $lines) {
            if ($line -match '^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$') {
                $port = [int]$matches[1]
                $owningPid = [int]$matches[2]
                if ($Ports -contains $port) {
                    $records.Add([PSCustomObject]@{
                        Port = $port
                        Pid  = $owningPid
                    })
                }
            }
        }
    }

    return $records | Sort-Object Port,Pid -Unique
}

function Test-IsExpectedDemoProcess {
    param(
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Process,
        [string]$CommandLine
    )

    if ($Process.MainWindowTitle -in @("PaperLens API", "PaperLens UI")) {
        return $true
    }

    $name = $Process.ProcessName.ToLowerInvariant()
    $command = [string]$CommandLine
    if ($null -eq $CommandLine) {
        $command = ""
    }
    $command = $command.ToLowerInvariant()

    if ($name -like "python*" -and $command.Contains("app.api.main:app")) {
        return $true
    }
    if ($name -like "python*" -and $command.Contains("ui/app.py")) {
        return $true
    }
    if ($name -eq "powershell" -and $command.Contains("paperlens")) {
        return $true
    }
    if ($name -like "python*") {
        return $true
    }

    return $false
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$statePath = Get-DemoStatePath -RepoRoot $repoRoot
$targetMap = @{}
$stateLoaded = $false
$managedPorts = New-Object System.Collections.Generic.List[int]

if (Test-Path -LiteralPath $statePath) {
    try {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $stateLoaded = $true

        $apiManaged = $false
        if ($state.PSObject.Properties.Name -contains "api_managed") {
            $apiManaged = [bool]$state.api_managed
        }
        elseif ($state.api_window_pid) {
            $apiManaged = $true
        }

        $uiManaged = $false
        if ($state.PSObject.Properties.Name -contains "ui_managed") {
            $uiManaged = [bool]$state.ui_managed
        }
        elseif ($state.ui_window_pid) {
            $uiManaged = $true
        }

        if ($apiManaged -and $state.api_port) {
            $managedPorts.Add([int]$state.api_port) | Out-Null
        }
        if ($uiManaged -and $state.ui_port) {
            $managedPorts.Add([int]$state.ui_port) | Out-Null
        }

        foreach ($windowPid in @($state.api_window_pid, $state.ui_window_pid)) {
            if ($windowPid) {
                Add-TargetRecord -TargetMap $targetMap -TargetPid ([int]$windowPid) -Reason "state_window" -Depth 0
                $children = Get-ChildProcessRecords -ParentPid ([int]$windowPid)
                foreach ($child in $children) {
                    Add-TargetRecord -TargetMap $targetMap -TargetPid $child.Pid -Reason "state_child" -Depth $child.Depth
                }
            }
        }
    }
    catch {
        Write-Host "State file exists but could not be parsed: $statePath" -ForegroundColor Yellow
    }
}

$portsToInspect = @($ApiPort, $UiPort)
if ($stateLoaded) {
    if ($managedPorts.Count -gt 0) {
        $portsToInspect = $managedPorts.ToArray()
    }
    else {
        $portsToInspect = @()
    }
}

$listenerRecords = Get-ListeningProcessRecords -Ports $portsToInspect
foreach ($listenerRecord in $listenerRecords) {
    $process = Get-Process -Id $listenerRecord.Pid -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        continue
    }

    $commandLine = Get-ProcessCommandLine -ProcessId $listenerRecord.Pid
    if (Test-IsExpectedDemoProcess -Process $process -CommandLine $commandLine) {
        Add-TargetRecord -TargetMap $targetMap -TargetPid $listenerRecord.Pid -Reason "port_listener" -Depth 0
    }
}

$targets = $targetMap.Values | Sort-Object `
    @{ Expression = "Depth"; Descending = $true }, `
    @{ Expression = "Pid"; Descending = $false }

if (-not $targets) {
    Write-Host "No matching PaperLens demo processes found for ports $ApiPort / $UiPort." -ForegroundColor Yellow
    if (Test-Path -LiteralPath $statePath) {
        Remove-Item -LiteralPath $statePath -Force
    }
    exit 0
}

$displayRows = foreach ($target in $targets) {
    $process = Get-Process -Id $target.Pid -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        continue
    }

    [PSCustomObject]@{
        Pid        = $target.Pid
        Name       = $process.ProcessName
        Window     = $process.MainWindowTitle
        Depth      = $target.Depth
        Reasons    = ($target.Reasons -join ",")
        CommandLine = Get-ProcessCommandLine -ProcessId $target.Pid
    }
}

if ($DryRun) {
    if ($displayRows) {
        Write-Host "Planned PaperLens stop targets:" -ForegroundColor Cyan
        $displayRows | Format-Table -AutoSize
    }
    else {
        Write-Host "No managed PaperLens demo processes are currently running for the requested ports." -ForegroundColor Yellow
    }
    Write-Host "State file: $statePath" -ForegroundColor DarkGray
    exit 0
}

foreach ($target in $targets) {
    $process = Get-Process -Id $target.Pid -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        continue
    }

    Stop-Process -Id $target.Pid -Force -ErrorAction SilentlyContinue
}

if (Test-Path -LiteralPath $statePath) {
    Remove-Item -LiteralPath $statePath -Force
}

$stoppedPorts = if ($stateLoaded -and $managedPorts.Count -gt 0) {
    ($managedPorts | Sort-Object -Unique) -join " / "
}
else {
    "$ApiPort / $UiPort"
}

Write-Host "Stopped managed PaperLens demo processes for ports $stoppedPorts." -ForegroundColor Green
