param(
    [ValidateSet("start", "stop", "status")]
    [string]$Action = "status"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $env:LOCALAPPDATA "cf-ai-card-runtime"
$PostgresBin = Join-Path $env:USERPROFILE ".pixi\envs\cf-ai-card-runtime\Library\bin"
$PostgresData = Join-Path $Runtime "postgres-data"
$RedisDir = Join-Path $Runtime "redis"
$ApiPython = Join-Path $Root "services\api\.venv\Scripts\python.exe"
$EmbeddingPython = Join-Path $Root "services\embedding\.venv\Scripts\python.exe"
$WorkerPython = Join-Path $Root "services\worker\.venv\Scripts\python.exe"

function Get-EnvironmentOrDefault([string]$Name, [string]$Default) {
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}

function Import-LocalEnvironment {
    $envFile = Join-Path $Root ".env.local"
    if (-not (Test-Path -LiteralPath $envFile)) {
        throw "Missing $envFile. Create it from .env.example before starting the runtime."
    }
    foreach ($line in Get-Content -LiteralPath $envFile) {
        if ($line -match "^([^#=]+)=(.*)$") {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process")
        }
    }
}

function Get-Listener([int]$Port) {
    Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Wait-Http(
    [string]$Url,
    [int]$Seconds = 30,
    [int]$RequestTimeoutSeconds = 2
) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        Start-Sleep -Milliseconds 500
        try {
            if ((
                Invoke-WebRequest `
                    -UseBasicParsing `
                    -Uri $Url `
                    -TimeoutSec $RequestTimeoutSeconds
            ).StatusCode -eq 200) {
                return
            }
        } catch {
            # Keep waiting until the deadline.
        }
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for $Url"
}

function Start-EmbeddingService {
    if (-not (Test-Path -LiteralPath $EmbeddingPython)) {
        throw "Embedding runtime is missing: $EmbeddingPython"
    }
    if ($null -ne (Get-Listener 8010)) { return }

    $environmentNames = @(
        "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
        "HF_HUB_DISABLE_XET", "HF_HUB_DISABLE_SYMLINKS_WARNING"
    )
    $savedEnvironment = @{}
    foreach ($name in $environmentNames) {
        $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    }

    try {
        $huggingFace = [Uri]"https://huggingface.co"
        $systemProxy = [System.Net.WebRequest]::DefaultWebProxy.GetProxy($huggingFace)
        if ($null -ne $systemProxy -and $systemProxy.AbsoluteUri -ne $huggingFace.AbsoluteUri) {
            $env:HTTP_PROXY = $systemProxy.AbsoluteUri
            $env:HTTPS_PROXY = $systemProxy.AbsoluteUri
        }
        $env:NO_PROXY = "127.0.0.1,localhost"
        $env:HF_HUB_DISABLE_XET = "1"
        $env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

        Start-Process -FilePath $EmbeddingPython `
            -ArgumentList @(
                "-m", "uvicorn", "app:app", "--app-dir", "services/embedding",
                "--host", "127.0.0.1", "--port", "8010"
            ) `
            -WorkingDirectory $Root `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $Runtime "embedding.stdout.log") `
            -RedirectStandardError (Join-Path $Runtime "embedding.stderr.log") | Out-Null
    } finally {
        foreach ($name in $environmentNames) {
            [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], "Process")
        }
    }
}

function Stop-ExpectedProcess([int]$Port, [string]$CommandPattern) {
    $listener = Get-Listener $Port
    if ($null -eq $listener) { return }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if ($null -eq $process -or $process.CommandLine -notmatch $CommandPattern) {
        throw "Refusing to stop the unexpected process listening on port $Port."
    }
    Stop-Process -Id $listener.OwningProcess -Force
}

function Get-CommandProcess([string]$CommandPattern) {
    Get-CimInstance Win32_Process |
        Where-Object { $null -ne $_.CommandLine -and $_.CommandLine -match $CommandPattern } |
        Select-Object -First 1
}

function Stop-ExpectedCommandProcesses([string]$CommandPattern) {
    $processes = Get-CimInstance Win32_Process |
        Where-Object { $null -ne $_.CommandLine -and $_.CommandLine -match $CommandPattern }
    foreach ($process in $processes) {
        Stop-Process -Id $process.ProcessId -Force
    }
}

function Show-Status {
    $rows = foreach ($service in @(
        @{ Name = "web"; Port = 4173 },
        @{ Name = "admin"; Port = 4174 },
        @{ Name = "api"; Port = 8000 },
        @{ Name = "embedding"; Port = 8010 },
        @{ Name = "worker"; Port = 8020 },
        @{ Name = "postgres"; Port = 5432 },
        @{ Name = "redis"; Port = 6379 }
    )) {
        $listener = Get-Listener $service.Port
        [PSCustomObject]@{
            Service = $service.Name
            Port = $service.Port
            Running = $null -ne $listener
            ProcessId = if ($null -ne $listener) { $listener.OwningProcess } else { $null }
        }
    }
    $rows | Format-Table -AutoSize
    try {
        $ready = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health/ready" -TimeoutSec 3
        Write-Host "API readiness: $($ready.data.status)"
    } catch {
        Write-Host "API readiness: unavailable"
    }
    try {
        $ready = Invoke-RestMethod -Uri "http://127.0.0.1:8010/health/ready" -TimeoutSec 3
        Write-Host "Embedding readiness: $($ready.data.status) ($($ready.data.model))"
    } catch {
        Write-Host "Embedding readiness: unavailable"
    }
}

function Start-Runtime {
    Import-LocalEnvironment
    New-Item -ItemType Directory -Force -Path $Runtime | Out-Null

    if (-not (Test-Path -LiteralPath (Join-Path $PostgresBin "pg_ctl.exe"))) {
        throw "PostgreSQL runtime is missing. Install the pixi environment cf-ai-card-runtime."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $PostgresData "PG_VERSION"))) {
        throw "PostgreSQL data directory is not initialized: $PostgresData"
    }
    if ($null -eq (Get-Listener 5432)) {
        $pgOptions = '"-h" "127.0.0.1" "-p" "5432" "-c" "password_encryption=scram-sha-256"'
        & (Join-Path $PostgresBin "pg_ctl.exe") `
            -D $PostgresData `
            -l (Join-Path $Runtime "postgres.log") `
            -o $pgOptions `
            -w start
        if ($LASTEXITCODE -ne 0) { throw "PostgreSQL failed to start." }
    }

    $savedPgPassword = [Environment]::GetEnvironmentVariable("PGPASSWORD", "Process")
    try {
        $env:PGPASSWORD = Get-EnvironmentOrDefault "POSTGRES_PASSWORD" "change-me-local-only"
        & (Join-Path $PostgresBin "psql.exe") `
            -h "127.0.0.1" `
            -p "5432" `
            -U (Get-EnvironmentOrDefault "POSTGRES_USER" "cf_ai_card") `
            -d (Get-EnvironmentOrDefault "POSTGRES_DB" "cf_ai_card") `
            -v "ON_ERROR_STOP=1" `
            -f (Join-Path $Root "infra\postgres\001_extensions.sql")
        if ($LASTEXITCODE -ne 0) { throw "PostgreSQL runtime roles failed to initialize." }
    } finally {
        [Environment]::SetEnvironmentVariable("PGPASSWORD", $savedPgPassword, "Process")
    }

    if ($null -eq (Get-Listener 6379)) {
        $redisServer = Join-Path $RedisDir "redis-server.exe"
        if (-not (Test-Path -LiteralPath $redisServer)) {
            throw "Redis runtime is missing: $redisServer"
        }
        $redisData = Join-Path $Runtime "redis-data"
        New-Item -ItemType Directory -Force -Path $redisData | Out-Null
        Start-Process -FilePath $redisServer `
            -ArgumentList @(
                (Join-Path $RedisDir "redis.windows.conf"),
                "--bind", "127.0.0.1", "--port", "6379",
                "--dir", $redisData, "--logfile", (Join-Path $Runtime "redis.log")
            ) `
            -WorkingDirectory $RedisDir `
            -WindowStyle Hidden | Out-Null
    }

    Start-EmbeddingService
    # The first launch may need to download and initialize the ~2 GB model.
    Wait-Http "http://127.0.0.1:8010/health/ready" 900

    Push-Location (Join-Path $Root "services\api")
    try {
        & $ApiPython -m alembic -c alembic.ini upgrade head
        if ($LASTEXITCODE -ne 0) { throw "Database migration failed." }
        & $ApiPython -m app.cli.seed_content `
            "..\..\packages\tenant-content\template.knowledge.json" `
            "..\..\packages\tenant-content\tuotu.knowledge.json"
        if ($LASTEXITCODE -ne 0) { throw "Knowledge seed failed." }
        & $ApiPython -m app.cli.index_embeddings
        if ($LASTEXITCODE -ne 0) { throw "Knowledge embedding index failed." }
    } finally {
        Pop-Location
    }

    if ($null -eq (Get-Listener 8000)) {
        Start-Process -FilePath $ApiPython `
            -ArgumentList @(
                "-m", "uvicorn", "app.main:app", "--app-dir", "services/api",
                "--host", "127.0.0.1", "--port", "8000"
            ) `
            -WorkingDirectory $Root `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $Runtime "api.stdout.log") `
            -RedirectStandardError (Join-Path $Runtime "api.stderr.log") | Out-Null
    }
    Wait-Http "http://127.0.0.1:8000/api/v1/health/ready"

    if (-not (Test-Path -LiteralPath $WorkerPython)) {
        throw "Worker runtime is missing: $WorkerPython"
    }
    if ($null -eq (Get-Listener 8020)) {
        $savedPythonPath = [Environment]::GetEnvironmentVariable("PYTHONPATH", "Process")
        try {
            $env:PYTHONPATH = @(
                (Join-Path $Root "services\api"),
                (Join-Path $Root "services\worker")
            ) -join ";"
            if ($null -eq (Get-CommandProcess "celery.*cf_worker.*\sbeat(\s|$)")) {
                Start-Process -FilePath $WorkerPython `
                    -ArgumentList @(
                        "-m", "celery", "-A", "cf_worker.celery_app:celery_app",
                        "beat", "--loglevel=INFO",
                        "--schedule", (Join-Path $Runtime "celerybeat-schedule")
                    ) `
                    -WorkingDirectory (Join-Path $Root "services\worker") `
                    -WindowStyle Hidden `
                    -RedirectStandardOutput (Join-Path $Runtime "worker-beat.stdout.log") `
                    -RedirectStandardError (Join-Path $Runtime "worker-beat.stderr.log") |
                    Out-Null
            }
            Start-Process -FilePath $WorkerPython `
                -ArgumentList @(
                    "-m", "celery", "-A", "cf_worker.celery_app:celery_app",
                    "worker", "--pool=solo", "--loglevel=INFO",
                    "--queues=outbox.poll,outbox.process"
                ) `
                -WorkingDirectory (Join-Path $Root "services\worker") `
                -WindowStyle Hidden `
                -RedirectStandardOutput (Join-Path $Runtime "worker.stdout.log") `
                -RedirectStandardError (Join-Path $Runtime "worker.stderr.log") | Out-Null
        } finally {
            [Environment]::SetEnvironmentVariable("PYTHONPATH", $savedPythonPath, "Process")
        }
    }
    Wait-Http "http://127.0.0.1:8020/health/ready" 60 5

    if ($null -eq (Get-Listener 4173)) {
        $command = '"C:\Program Files\nodejs\corepack.cmd" pnpm web:dev'
        Start-Process -FilePath "$env:SystemRoot\System32\cmd.exe" `
            -ArgumentList "/d", "/s", "/c", "`"$command`"" `
            -WorkingDirectory $Root `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $Runtime "web.stdout.log") `
            -RedirectStandardError (Join-Path $Runtime "web.stderr.log") | Out-Null
    }
    Wait-Http "http://127.0.0.1:4173/c/tuotu"

    if ($null -eq (Get-Listener 4174)) {
        $adminCommand = '"C:\Program Files\nodejs\corepack.cmd" pnpm admin:dev'
        Start-Process -FilePath "$env:SystemRoot\System32\cmd.exe" `
            -ArgumentList "/d", "/s", "/c", "`"$adminCommand`"" `
            -WorkingDirectory $Root `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $Runtime "admin.stdout.log") `
            -RedirectStandardError (Join-Path $Runtime "admin.stderr.log") | Out-Null
    }
    Wait-Http "http://127.0.0.1:4174/"
    Show-Status
}

function Stop-Runtime {
    Stop-ExpectedProcess 4173 "card-web|vite"
    Stop-ExpectedProcess 4174 "admin-web|vite"
    Stop-ExpectedProcess 8000 "uvicorn.*app\.main"
    Stop-ExpectedProcess 8010 "uvicorn.*app:app.*services[/\\]embedding"
    Stop-ExpectedProcess 8020 "celery.*cf_worker"
    Stop-ExpectedCommandProcesses "celery.*cf_worker.*\sbeat(\s|$)"

    if ($null -ne (Get-Listener 6379)) {
        $redisCli = Join-Path $RedisDir "redis-cli.exe"
        if (Test-Path -LiteralPath $redisCli) {
            & $redisCli -h 127.0.0.1 -p 6379 shutdown | Out-Null
        }
    }
    if ($null -ne (Get-Listener 5432)) {
        & (Join-Path $PostgresBin "pg_ctl.exe") -D $PostgresData -w stop -m fast
    }
    Show-Status
}

switch ($Action) {
    "start" { Start-Runtime }
    "stop" { Stop-Runtime }
    "status" { Show-Status }
}
