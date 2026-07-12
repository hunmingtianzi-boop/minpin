$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "services\api\.venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "API virtual environment is missing: $python"
}

& $python @args
exit $LASTEXITCODE
