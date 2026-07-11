[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [string]$TargetDatabaseUrl = $env:RESTORE_DATABASE_URL,
    [string]$ReportDirectory = (Join-Path $PSScriptRoot "../../artifacts/restore-rehearsals"),
    [ValidateRange(1, 168)]
    [int]$RpoObjectiveHours = 24,
    [ValidateRange(60, 86400)]
    [int]$RtoObjectiveSeconds = 14400,
    [ValidateRange(0, 1000000)]
    [int]$MinimumTenants = 1,
    [ValidateRange(0, 1000000)]
    [int]$MinimumCompanies = 1,
    [string]$ExpectedAlembicVersion = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function ConvertFrom-PostgresUrl {
    param([Parameter(Mandatory = $true)][string]$Value)

    $normalized = $Value -replace '^postgresql\+[^:]+://', 'postgresql://'
    try {
        $uri = [System.Uri]$normalized
    }
    catch {
        throw "RESTORE_DATABASE_URL is not a valid PostgreSQL URL."
    }
    if ($uri.Scheme -notin @("postgresql", "postgres")) {
        throw "Only PostgreSQL URLs are supported."
    }
    $userInfo = $uri.UserInfo.Split(':', 2)
    if ($userInfo.Count -ne 2 -or [string]::IsNullOrWhiteSpace($userInfo[0])) {
        throw "The PostgreSQL URL must include a username and password."
    }
    $database = [System.Uri]::UnescapeDataString($uri.AbsolutePath.TrimStart('/'))
    if ($database -notmatch '(_restore_test|_restore_rehearsal)$') {
        throw "Restore is allowed only into a database ending _restore_test or _restore_rehearsal."
    }
    return [pscustomobject]@{
        Host = $uri.Host
        Port = if ($uri.IsDefaultPort) { 5432 } else { $uri.Port }
        Username = [System.Uri]::UnescapeDataString($userInfo[0])
        Password = [System.Uri]::UnescapeDataString($userInfo[1])
        Database = $database
    }
}

if ([string]::IsNullOrWhiteSpace($TargetDatabaseUrl)) {
    throw "RESTORE_DATABASE_URL or -TargetDatabaseUrl is required."
}
$resolvedBackup = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $BackupFile).Path)
$pgRestore = Get-Command pg_restore -ErrorAction Stop
$psql = Get-Command psql -ErrorAction Stop
$connection = ConvertFrom-PostgresUrl -Value $TargetDatabaseUrl

$manifestPath = [System.IO.Path]::ChangeExtension($resolvedBackup, ".manifest.json")
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "The backup manifest is missing: $manifestPath"
}
$manifest = Get-Content -Raw -LiteralPath $manifestPath -Encoding utf8 | ConvertFrom-Json
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedBackup).Hash.ToLowerInvariant()
if (-not [System.StringComparer]::OrdinalIgnoreCase.Equals($actualHash, [string]$manifest.sha256)) {
    throw "Backup checksum verification failed."
}
$backupCreatedAt = [DateTimeOffset]::Parse([string]$manifest.created_at_utc)
$rpoHoursObserved = ([DateTimeOffset]::UtcNow - $backupCreatedAt).TotalHours

$arguments = @(
    "--host", $connection.Host,
    "--port", [string]$connection.Port,
    "--username", $connection.Username,
    "--dbname", $connection.Database
)
$timer = [System.Diagnostics.Stopwatch]::StartNew()
$previousPassword = $env:PGPASSWORD
try {
    $env:PGPASSWORD = $connection.Password
    $restoreArguments = @(
        $arguments
        "--clean"
        "--if-exists"
        "--single-transaction"
        "--exit-on-error"
        "--no-owner"
        "--no-privileges"
        $resolvedBackup
    )
    & $pgRestore.Source @restoreArguments
    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore failed with exit code $LASTEXITCODE."
    }

    $verificationSql = @"
SELECT json_build_object(
  'alembic_version', COALESCE((SELECT version_num FROM alembic_version LIMIT 1), ''),
  'tenants', (SELECT count(*) FROM tenants),
  'companies', (SELECT count(*) FROM companies),
  'cards', (SELECT count(*) FROM cards),
  'knowledge_documents', (SELECT count(*) FROM knowledge_documents),
  'outbox_events', (SELECT count(*) FROM outbox_events)
)::text;
"@
    $queryOutput = & $psql.Source @arguments --tuples-only --no-align --set ON_ERROR_STOP=1 --command $verificationSql
    if ($LASTEXITCODE -ne 0) {
        throw "Post-restore verification failed with exit code $LASTEXITCODE."
    }
}
finally {
    $env:PGPASSWORD = $previousPassword
    $timer.Stop()
}

$verificationLine = ($queryOutput | Where-Object { $_ -match '^\{' } | Select-Object -Last 1)
if ([string]::IsNullOrWhiteSpace($verificationLine)) {
    throw "Post-restore verification did not return a JSON result."
}
$verification = $verificationLine | ConvertFrom-Json
$versionMatches = [string]::IsNullOrWhiteSpace($ExpectedAlembicVersion) -or (
    [string]$verification.alembic_version -eq $ExpectedAlembicVersion
)
$passed = (
    $rpoHoursObserved -le $RpoObjectiveHours -and
    $timer.Elapsed.TotalSeconds -le $RtoObjectiveSeconds -and
    [int]$verification.tenants -ge $MinimumTenants -and
    [int]$verification.companies -ge $MinimumCompanies -and
    $versionMatches
)

New-Item -ItemType Directory -Path $ReportDirectory -Force | Out-Null
$reportRoot = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $ReportDirectory).Path)
$reportPath = Join-Path $reportRoot (
    "restore-rehearsal-{0}.json" -f [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ")
)
$report = [ordered]@{
    schema_version = 1
    completed_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    target_database = $connection.Database
    backup_sha256 = $actualHash
    rpo_objective_hours = $RpoObjectiveHours
    rpo_observed_hours = [Math]::Round($rpoHoursObserved, 4)
    rto_objective_seconds = $RtoObjectiveSeconds
    restore_observed_seconds = [Math]::Round($timer.Elapsed.TotalSeconds, 3)
    verification = $verification
    passed = $passed
}
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding utf8
if (-not $passed) {
    throw "Restore completed but the RPO/RTO or data verification gate failed. Report: $reportPath"
}

Write-Output $reportPath
