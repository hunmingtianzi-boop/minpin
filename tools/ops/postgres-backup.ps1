[CmdletBinding()]
param(
    [string]$DatabaseUrl = $env:MIGRATION_DATABASE_URL,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "../../artifacts/backups"),
    [ValidateRange(1, 3650)]
    [int]$RetentionDays = 30
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
        throw "MIGRATION_DATABASE_URL is not a valid PostgreSQL URL."
    }
    if ($uri.Scheme -notin @("postgresql", "postgres")) {
        throw "Only PostgreSQL URLs are supported."
    }
    $userInfo = $uri.UserInfo.Split(':', 2)
    if ($userInfo.Count -ne 2 -or [string]::IsNullOrWhiteSpace($userInfo[0])) {
        throw "The PostgreSQL URL must include a username and password."
    }
    $database = [System.Uri]::UnescapeDataString($uri.AbsolutePath.TrimStart('/'))
    if ([string]::IsNullOrWhiteSpace($database)) {
        throw "The PostgreSQL URL must include a database name."
    }
    return [pscustomobject]@{
        Host = $uri.Host
        Port = if ($uri.IsDefaultPort) { 5432 } else { $uri.Port }
        Username = [System.Uri]::UnescapeDataString($userInfo[0])
        Password = [System.Uri]::UnescapeDataString($userInfo[1])
        Database = $database
    }
}

if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    throw "MIGRATION_DATABASE_URL or -DatabaseUrl is required."
}
$pgDump = Get-Command pg_dump -ErrorAction Stop
$connection = ConvertFrom-PostgresUrl -Value $DatabaseUrl

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$backupRoot = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $OutputDirectory).Path)
$safePrefix = $backupRoot.TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
) + [System.IO.Path]::DirectorySeparatorChar

$timestamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$baseName = "cf-ai-card-$timestamp"
$partialPath = Join-Path $backupRoot "$baseName.dump.partial"
$backupPath = Join-Path $backupRoot "$baseName.dump"
$manifestPath = Join-Path $backupRoot "$baseName.manifest.json"

$previousPassword = $env:PGPASSWORD
try {
    $env:PGPASSWORD = $connection.Password
    $dumpArguments = @(
        "--host", $connection.Host,
        "--port", [string]$connection.Port,
        "--username", $connection.Username,
        "--dbname", $connection.Database,
        "--format", "custom",
        "--compress", "9",
        "--no-owner",
        "--no-privileges",
        "--file", $partialPath
    )
    & $pgDump.Source @dumpArguments
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump failed with exit code $LASTEXITCODE."
    }
}
finally {
    $env:PGPASSWORD = $previousPassword
}

$partial = Get-Item -LiteralPath $partialPath
if ($partial.Length -le 0) {
    Remove-Item -LiteralPath $partialPath -Force
    throw "pg_dump produced an empty backup."
}
Move-Item -LiteralPath $partialPath -Destination $backupPath

$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $backupPath
$createdAt = [DateTimeOffset]::UtcNow
$manifest = [ordered]@{
    schema_version = 1
    created_at_utc = $createdAt.ToString("o")
    database_host = $connection.Host
    database_name = $connection.Database
    backup_file = [System.IO.Path]::GetFileName($backupPath)
    bytes = (Get-Item -LiteralPath $backupPath).Length
    sha256 = $hash.Hash.ToLowerInvariant()
    retention_days = $RetentionDays
    rpo_objective_hours = 24
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding utf8

$cutoff = [DateTimeOffset]::UtcNow.AddDays(-$RetentionDays)
$expired = Get-ChildItem -LiteralPath $backupRoot -File |
    Where-Object {
        $_.Name -like "cf-ai-card-*.dump" -or $_.Name -like "cf-ai-card-*.manifest.json"
    } |
    Where-Object { $_.LastWriteTimeUtc -lt $cutoff.UtcDateTime }
foreach ($file in $expired) {
    $target = [System.IO.Path]::GetFullPath($file.FullName)
    if (-not $target.StartsWith($safePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a retention target outside the backup directory."
    }
    Remove-Item -LiteralPath $target -Force
}

Write-Output $manifestPath
