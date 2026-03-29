# Start the full stack (Postgres, Redis, API, Celery worker)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
docker compose up --build -d @args
Write-Host "API: http://localhost:8000  |  Docs: http://localhost:8000/docs"
Write-Host "Logs: docker compose logs -f"
