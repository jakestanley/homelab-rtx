param(
    [int]$Port,
    [string]$PythonExe
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path $scriptDir -Parent

function Get-DotEnvValue {
    param(
        [string]$Path,
        [string]$Key
    )
    if (-not (Test-Path $Path)) {
        return $null
    }
    foreach ($line in Get-Content $Path) {
        if ($line -match '^[\s#]') {
            continue
        }
        $parts = $line -split '=', 2
        if ($parts.Count -lt 2) {
            continue
        }
        if ($parts[0].Trim() -eq $Key) {
            return $parts[1].Trim()
        }
    }
    return $null
}

function Test-RepoPreflight {
    param(
        [string]$Path,
        [string]$Name
    )

    if (-not (Test-Path $Path)) {
        return "Missing repo: $Name ($Path)"
    }

    $insideRepo = & git -C $Path rev-parse --is-inside-work-tree 2>$null
    if ($LASTEXITCODE -ne 0 -or $insideRepo -ne "true") {
        return "Not a git repo: $Name ($Path)"
    }

    $status = & git -C $Path status --porcelain
    if ($status) {
        return "Repo has uncommitted changes: $Name ($Path)"
    }

    $defaultRef = & git -C $Path symbolic-ref refs/remotes/origin/HEAD 2>$null
    if ($LASTEXITCODE -eq 0 -and $defaultRef) {
        $defaultBranch = $defaultRef -replace '^refs/remotes/origin/', ''
        $currentBranch = & git -C $Path rev-parse --abbrev-ref HEAD
        if ($currentBranch -ne $defaultBranch) {
            return "Repo not on default branch ($defaultBranch): $Name ($Path)"
        }
        $statusShort = & git -C $Path status -sb
        if ($statusShort -match 'ahead|behind') {
            return "Repo not at default branch HEAD: $Name ($Path)"
        }
    } else {
        return "Unable to determine default branch: $Name ($Path)"
    }

    return $null
}

$parentDir = Split-Path $repoRoot -Parent
$preflightIssues = @()
$preflightIssues += Test-RepoPreflight -Path (Join-Path $parentDir "homelab-infra") -Name "homelab-infra"
$preflightIssues += Test-RepoPreflight -Path (Join-Path $parentDir "homelab-standards") -Name "homelab-standards"
$preflightIssues = $preflightIssues | Where-Object { $_ }

if ($preflightIssues.Count -gt 0) {
    Write-Warning "Preflight checks failed:"
    foreach ($issue in $preflightIssues) {
        Write-Warning "- $issue"
    }
    $confirm = Read-Host "Continue anyway? (y/N)"
    if ($confirm -ne "y") {
        exit 1
    }
}

$envFile = Join-Path $repoRoot ".env"
$resolvedPort = $Port
if (-not $resolvedPort) {
    $resolvedPort = $env:RTX_PORT
}
if (-not $resolvedPort) {
    $resolvedPort = Get-DotEnvValue -Path $envFile -Key "RTX_PORT"
}
if (-not $resolvedPort) {
    $resolvedPort = 20031
}

$ruleName = "homelab-rtx (TCP $resolvedPort)"
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if ($isAdmin) {
    $existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    if (-not $existingRule) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $resolvedPort -Profile Private | Out-Null
    }
} else {
    Write-Warning "Not running elevated; firewall rule may be missing."
    Write-Host "Run the following in an elevated PowerShell prompt to allow inbound TCP $resolvedPort on Private profile:"
    Write-Host "New-NetFirewallRule -DisplayName \"$ruleName\" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $resolvedPort -Profile Private"
}

$venvPath = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvActivate = Join-Path $venvPath "Scripts\Activate.ps1"

function Resolve-PythonPath {
    param(
        [string]$Path
    )
    if (-not $Path) {
        return $null
    }
    if ($Path -match '^/([a-zA-Z])/') {
        $drive = $matches[1].ToUpper()
        return ($Path -replace '^/([a-zA-Z])/', "$drive`:\")
    }
    return $Path
}

if (-not (Test-Path $venvPython)) {
    $bootstrapCommand = $null
    $resolvedPythonExe = Resolve-PythonPath -Path $PythonExe
    $resolvedEnvPython = Resolve-PythonPath -Path $env:RTX_PYTHON_EXE
    if ($resolvedPythonExe) {
        $bootstrapCommand = @($resolvedPythonExe)
    } elseif ($resolvedEnvPython) {
        $bootstrapCommand = @($resolvedEnvPython)
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $bootstrapCommand = @("python")
    }

    if (-not $bootstrapCommand) {
        throw "Python not found. Install Python 3 and re-run, or pass -PythonExe / set RTX_PYTHON_EXE."
    }

    & @bootstrapCommand -m venv $venvPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
        throw "Failed to create virtual environment at $venvPath."
    }
}

if (Test-Path $venvActivate) {
    . $venvActivate
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m pip install -r (Join-Path $repoRoot "requirements.txt")
} else {
    & $venvPython -m pip install -r (Join-Path $repoRoot "requirements.txt")
}
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install dependencies."
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python (Join-Path $repoRoot "app.py")
} else {
    & $venvPython (Join-Path $repoRoot "app.py")
}
