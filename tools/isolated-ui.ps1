param(
    [ValidateSet("start", "stop", "status")]
    [string]$Action = "status",
    [int]$CardPort = 4318,
    [int]$AdminPort = 4319,
    [int]$ApiPort = 8030,
    [string]$BackendEnvironmentFile = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $env:LOCALAPPDATA "cf-ai-card-ui-prototype"
$Corepack = Join-Path $env:ProgramFiles "nodejs\corepack.cmd"
$ApiPython = Join-Path $Root "services\api\.venv\Scripts\python.exe"

function Get-Listener([int]$Port) {
    Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Wait-Http([string]$Url, [int]$Seconds = 30) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        try {
            if ((Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2).StatusCode -eq 200) {
                return
            }
        } catch {
            Start-Sleep -Milliseconds 350
        }
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for $Url"
}

function Start-Vite(
    [string]$Package,
    [int]$Port,
    [string]$LogName
) {
    if ($null -ne (Get-Listener $Port)) { return }
    $command = "`"$Corepack`" pnpm --filter $Package exec vite --host 127.0.0.1 --port $Port --strictPort"
    Start-Process -FilePath "$env:SystemRoot\System32\cmd.exe" `
        -ArgumentList "/d", "/s", "/c", "`"$command`"" `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Runtime "$LogName.stdout.log") `
        -RedirectStandardError (Join-Path $Runtime "$LogName.stderr.log") |
        Out-Null
}

function Import-EnvironmentFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Backend environment file does not exist: $Path"
    }
    $saved = @{}
    foreach ($line in Get-Content -LiteralPath $Path -Encoding utf8) {
        if ($line -notmatch "^([^#=]+)=(.*)$") { continue }
        $name = $Matches[1]
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, $Matches[2], "Process")
    }
    return $saved
}

function Restore-Environment([hashtable]$Saved) {
    foreach ($name in $Saved.Keys) {
        [Environment]::SetEnvironmentVariable($name, $Saved[$name], "Process")
    }
}

function Start-Api([string]$EnvironmentFile) {
    if ($null -ne (Get-Listener $ApiPort)) { return }
    if (-not (Test-Path -LiteralPath $ApiPython)) {
        throw "Isolated API runtime is missing: $ApiPython"
    }
    $saved = Import-EnvironmentFile $EnvironmentFile
    $extraNames = @("CORS_ALLOWED_ORIGINS", "PUBLIC_CARD_BASE_URL")
    foreach ($name in $extraNames) {
        if (-not $saved.ContainsKey($name)) {
            $saved[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        }
    }
    try {
        $env:CORS_ALLOWED_ORIGINS = "[`"http://127.0.0.1:$CardPort`",`"http://127.0.0.1:$AdminPort`",`"http://localhost:$CardPort`",`"http://localhost:$AdminPort`"]"
        $env:PUBLIC_CARD_BASE_URL = "http://127.0.0.1:$CardPort"
        Start-Process -FilePath $ApiPython `
            -ArgumentList @(
                "-m", "uvicorn", "app.main:app", "--app-dir", "services/api",
                "--host", "127.0.0.1", "--port", "$ApiPort"
            ) `
            -WorkingDirectory $Root `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $Runtime "api.stdout.log") `
            -RedirectStandardError (Join-Path $Runtime "api.stderr.log") |
            Out-Null
    } finally {
        Restore-Environment $saved
    }
}

function Stop-Vite([int]$Port) {
    $listener = Get-Listener $Port
    if ($null -eq $listener) { return }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if (
        $null -eq $process -or
        $process.CommandLine -notmatch [regex]::Escape($Root) -or
        $process.CommandLine -notmatch "vite"
    ) {
        throw "Refusing to stop an unexpected process on port $Port."
    }
    Stop-Process -Id $listener.OwningProcess -Force
}

function Stop-Api {
    $listener = Get-Listener $ApiPort
    if ($null -eq $listener) { return }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if (
        $null -eq $process -or
        $process.CommandLine -notmatch [regex]::Escape($Root) -or
        $process.CommandLine -notmatch "uvicorn.*app\.main"
    ) {
        throw "Refusing to stop an unexpected process on port $ApiPort."
    }
    Stop-Process -Id $listener.OwningProcess -Force
}

function Show-Status {
    @(
        [PSCustomObject]@{
            Service = "isolated API"
            Url = "http://127.0.0.1:$ApiPort/api/v1/health/ready"
            Running = $null -ne (Get-Listener $ApiPort)
        },
        [PSCustomObject]@{
            Service = "blank enterprise card"
            Url = "http://127.0.0.1:$CardPort/c/blank-enterprise"
            Running = $null -ne (Get-Listener $CardPort)
        },
        [PSCustomObject]@{
            Service = "isolated platform admin"
            Url = "http://127.0.0.1:$AdminPort/"
            Running = $null -ne (Get-Listener $AdminPort)
        }
    ) | Format-Table -AutoSize
}

switch ($Action) {
    "start" {
        New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
        $environmentFile = if ($BackendEnvironmentFile) {
            $BackendEnvironmentFile
        } else {
            Join-Path $Root ".env.local"
        }
        Start-Api $environmentFile
        Wait-Http "http://127.0.0.1:$ApiPort/api/v1/health/ready"
        $savedAdminUrl = [Environment]::GetEnvironmentVariable(
            "VITE_ADMIN_BASE_URL",
            "Process"
        )
        $savedProxyTarget = [Environment]::GetEnvironmentVariable(
            "VITE_DEV_API_PROXY_TARGET",
            "Process"
        )
        $savedBlankTemplate = [Environment]::GetEnvironmentVariable(
            "VITE_ENABLE_BLANK_ENTERPRISE_TEMPLATE",
            "Process"
        )
        try {
            $env:VITE_ADMIN_BASE_URL = "http://127.0.0.1:$AdminPort/"
            $env:VITE_DEV_API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
            $env:VITE_ENABLE_BLANK_ENTERPRISE_TEMPLATE = "true"
            Start-Vite "@cf/card-web" $CardPort "card"
            Start-Vite "@cf/admin-web" $AdminPort "admin"
        } finally {
            [Environment]::SetEnvironmentVariable(
                "VITE_ADMIN_BASE_URL",
                $savedAdminUrl,
                "Process"
            )
            [Environment]::SetEnvironmentVariable(
                "VITE_DEV_API_PROXY_TARGET",
                $savedProxyTarget,
                "Process"
            )
            [Environment]::SetEnvironmentVariable(
                "VITE_ENABLE_BLANK_ENTERPRISE_TEMPLATE",
                $savedBlankTemplate,
                "Process"
            )
        }
        Wait-Http "http://127.0.0.1:$CardPort/c/blank-enterprise"
        Wait-Http "http://127.0.0.1:$AdminPort/"
        Show-Status
    }
    "stop" {
        Stop-Vite $CardPort
        Stop-Vite $AdminPort
        Stop-Api
        Show-Status
    }
    "status" { Show-Status }
}
