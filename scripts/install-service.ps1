param(
    [string]$ServiceName,
    [string]$PythonExe,
    [switch]$Start,
    [switch]$Stop,
    [switch]$Uninstall
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path $scriptDir -Parent

if (-not $ServiceName) {
    $ServiceName = Split-Path $repoRoot -Leaf
}

$logsDir = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$nssm = Get-Command nssm -ErrorAction SilentlyContinue
if (-not $nssm) {
    throw "nssm not found on PATH. Install nssm and re-run."
}

$serviceExists = $false
$nssmStatus = & nssm status $ServiceName 2>$null
if ($LASTEXITCODE -eq 0) {
    $serviceExists = $true
}

if ($Uninstall) {
    if ($serviceExists) {
        & nssm stop $ServiceName | Out-Null
        & nssm remove $ServiceName confirm | Out-Null
    }
    return
}

$psExe = (Get-Command powershell).Source
$upScript = Join-Path $repoRoot "scripts\up.ps1"
$appParams = "-NoProfile -ExecutionPolicy Bypass -File `"$upScript`""
$resolvedPython = $PythonExe
if (-not $resolvedPython) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $resolvedPython = $pythonCommand.Source
    }
}
if ($resolvedPython) {
    $appParams = "$appParams -PythonExe `"$resolvedPython`""
}

if (-not $serviceExists) {
    & nssm install $ServiceName $psExe | Out-Null
}

& nssm set $ServiceName AppDirectory $repoRoot | Out-Null
& nssm set $ServiceName AppParameters $appParams | Out-Null
if ($resolvedPython) {
    & nssm set $ServiceName AppEnvironmentExtra "RTX_PYTHON_EXE=$resolvedPython" | Out-Null
}
& nssm set $ServiceName AppStdout (Join-Path $logsDir "nssm-stdout.log") | Out-Null
& nssm set $ServiceName AppStderr (Join-Path $logsDir "nssm-stderr.log") | Out-Null

if ($Stop) {
    & nssm stop $ServiceName | Out-Null
    return
}

if ($Start) {
    $state = (& nssm status $ServiceName).Trim()
    if ($state -ne "SERVICE_STOPPED") {
        & nssm restart $ServiceName | Out-Null
    } else {
        & nssm start $ServiceName | Out-Null
    }
}
