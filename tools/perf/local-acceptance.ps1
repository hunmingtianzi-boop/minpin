[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8000/api/v1",
    [string]$CardSlug = "tuotu",
    [string]$AdminAccount = $env:ADMIN_BOOTSTRAP_ACCOUNT,
    [string]$AdminPassword = $env:ADMIN_BOOTSTRAP_PASSWORD,
    [ValidateRange(1, 100)]
    [int]$TargetConcurrency = 5,
    [ValidateRange(2, 4)]
    [int]$PeakMultiplier = 2,
    [ValidateRange(1, 10000)]
    [int]$HttpRequests = 100,
    [ValidateRange(1, 1000)]
    [int]$RagRequestsPerScenario = 10,
    [ValidateRange(0, 1000)]
    [int]$WarmupRequests = 2,
    [ValidateRange(1, 120)]
    [int]$TimeoutSeconds = 20,
    [string]$OutputDirectory = "",
    [switch]$SkipStart,
    [switch]$Formal
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../.."))
$Python = Join-Path $Root "services/api/.venv/Scripts/python.exe"
$QuestionFile = Join-Path $Root "packages/evals/tuotu.v2.json"
$LocalEnvironment = Join-Path $Root ".env.local"
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $Root "artifacts/perf/local-acceptance"
}

function Get-LocalEnvironmentValue {
    param([Parameter(Mandatory = $true)][string]$Name)

    if (-not (Test-Path -LiteralPath $LocalEnvironment)) {
        return $null
    }
    $prefix = "$Name="
    $line = Get-Content -LiteralPath $LocalEnvironment -Encoding utf8 |
        Where-Object { $_.StartsWith($prefix, [System.StringComparison]::Ordinal) } |
        Select-Object -Last 1
    if ($null -eq $line) {
        return $null
    }
    return $line.Substring($prefix.Length)
}

function Invoke-PerfGate {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    & $Python -m tools.perf.cli @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Performance gate failed: $Name (exit $LASTEXITCODE)."
    }
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "API Python runtime is missing: $Python"
}
if (-not (Test-Path -LiteralPath $QuestionFile)) {
    throw "RAG question set is missing: $QuestionFile"
}
if ($Formal) {
    if ($HttpRequests -lt 200 -or $RagRequestsPerScenario -lt 50) {
        throw "Formal mode requires at least 200 HTTP and 50 RAG samples per scenario."
    }
    if ($BaseUrl -match '^http://(127\.0\.0\.1|localhost)') {
        throw "Formal mode must target an isolated staging or capacity environment."
    }
}

if ([string]::IsNullOrWhiteSpace($AdminAccount)) {
    $AdminAccount = Get-LocalEnvironmentValue -Name "ADMIN_BOOTSTRAP_ACCOUNT"
}
if ([string]::IsNullOrWhiteSpace($AdminPassword)) {
    $AdminPassword = Get-LocalEnvironmentValue -Name "ADMIN_BOOTSTRAP_PASSWORD"
}
if ([string]::IsNullOrWhiteSpace($AdminAccount) -or
    [string]::IsNullOrWhiteSpace($AdminPassword)) {
    throw "Admin credentials must come from parameters, environment variables, or .env.local."
}

if (-not $SkipStart) {
    Push-Location $Root
    try {
        & corepack pnpm local:start
        if ($LASTEXITCODE -ne 0) {
            throw "Local runtime failed to start."
        }
    }
    finally {
        Pop-Location
    }
}

$loginBody = @{
    account = $AdminAccount
    credential = $AdminPassword
    method = "password"
} | ConvertTo-Json
$login = Invoke-RestMethod `
    -Method Post `
    -Uri "$($BaseUrl.TrimEnd('/'))/auth/login" `
    -ContentType "application/json" `
    -Body $loginBody `
    -TimeoutSec $TimeoutSeconds
$accessToken = [string]$login.data.access_token
if ([string]::IsNullOrWhiteSpace($accessToken)) {
    throw "Admin login did not return an access token."
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$outputRoot = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $OutputDirectory).Path)
$timestamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$peakConcurrency = $TargetConcurrency * $PeakMultiplier
$previousAuthorization = $env:PERF_AUTHORIZATION

try {
    $env:PERF_AUTHORIZATION = "Bearer $accessToken"
    Push-Location $Root
    try {
        Invoke-PerfGate -Name "public-card" -Arguments @(
            "http",
            "--url", "$($BaseUrl.TrimEnd('/'))/public/cards/$CardSlug",
            "--profile", "public-card",
            "--requests", [string]$HttpRequests,
            "--concurrency", [string]$TargetConcurrency,
            "--warmup-requests", [string]$WarmupRequests,
            "--timeout-seconds", [string]$TimeoutSeconds,
            "--max-error-rate", "0",
            "--scenario", "local-public-card-target",
            "--output", (Join-Path $outputRoot "public-card-$timestamp.json")
        )
        Invoke-PerfGate -Name "admin-list" -Arguments @(
            "http",
            "--url", "$($BaseUrl.TrimEnd('/'))/admin/cards?limit=50&offset=0",
            "--profile", "admin-list",
            "--header-env", "Authorization=PERF_AUTHORIZATION",
            "--requests", [string]$HttpRequests,
            "--concurrency", [string]$TargetConcurrency,
            "--warmup-requests", [string]$WarmupRequests,
            "--timeout-seconds", [string]$TimeoutSeconds,
            "--max-error-rate", "0",
            "--scenario", "local-admin-list-target",
            "--output", (Join-Path $outputRoot "admin-list-$timestamp.json")
        )
        Invoke-PerfGate -Name "rag-target" -Arguments @(
            "rag",
            "--base-url", $BaseUrl,
            "--card-slug", $CardSlug,
            "--questions", $QuestionFile,
            "--requests", [string]$RagRequestsPerScenario,
            "--concurrency", [string]$TargetConcurrency,
            # Each RAG warm-up is a real public chat request and therefore
            # consumes the same IP/card protection budget as measured traffic.
            # Keep RAG scenarios independent of HTTP warm-ups so the default
            # target + peak run stays within the configured 20/minute budget.
            "--warmup-requests", "0",
            "--timeout-seconds", [string]$TimeoutSeconds,
            "--max-error-rate", "0.01",
            "--scenario", "local-rag-target",
            "--output", (Join-Path $outputRoot "rag-target-$timestamp.json")
        )
        Invoke-PerfGate -Name "rag-peak" -Arguments @(
            "rag",
            "--base-url", $BaseUrl,
            "--card-slug", $CardSlug,
            "--questions", $QuestionFile,
            "--requests", [string]$RagRequestsPerScenario,
            "--concurrency", [string]$peakConcurrency,
            "--warmup-requests", "0",
            "--timeout-seconds", [string]$TimeoutSeconds,
            "--max-error-rate", "0.01",
            "--scenario", "local-rag-peak",
            "--output", (Join-Path $outputRoot "rag-peak-$timestamp.json")
        )
    }
    finally {
        Pop-Location
    }
}
finally {
    $env:PERF_AUTHORIZATION = $previousAuthorization
}

$reports = Get-ChildItem -LiteralPath $outputRoot -Filter "*-$timestamp.json" |
    Sort-Object Name |
    ForEach-Object {
        $report = Get-Content -LiteralPath $_.FullName -Raw -Encoding utf8 | ConvertFrom-Json
        [ordered]@{
            file = $_.Name
            scenario = $report.scenario
            passed = [bool]$report.gate.passed
            samples = [int]$report.metrics.samples
            error_rate = [double]$report.metrics.error_rate
            latency_p95_ms = [double]$report.metrics.latency_ms.p95
            ttft_p95_ms = if ($report.mode -eq "rag") {
                [double]$report.metrics.ttft_ms.p95
            } else {
                $null
            }
        }
    }
$manifest = [ordered]@{
    schema_version = 1
    generated_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    classification = if ($Formal) { "formal_capacity_acceptance" } else {
        "local_engineering_baseline"
    }
    target_concurrency = $TargetConcurrency
    peak_concurrency = $peakConcurrency
    reports = @($reports)
    passed = (@($reports | Where-Object { -not $_.passed }).Count -eq 0)
}
$manifestPath = Join-Path $outputRoot "manifest-$timestamp.json"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8
Write-Output $manifestPath
