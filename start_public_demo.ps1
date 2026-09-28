$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontend = Join-Path $projectRoot "frontend"
$backend = Join-Path $projectRoot "backend"
$python = Join-Path $projectRoot "venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) { throw "Project Python environment was not found at $python" }
if (-not (Test-Path -LiteralPath (Join-Path $backend ".env"))) { throw "Create backend\.env with DATABASE_URL and a strong SECRET_KEY before starting." }

Write-Host "Building the website for same-origin hosting..."
Push-Location $frontend
try { npm run build; if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." } }
finally { Pop-Location }

$postgres = Test-NetConnection 127.0.0.1 -Port 5432 -InformationLevel Quiet
if (-not $postgres) { throw "PostgreSQL is not reachable on 127.0.0.1:5432. Start the PostgreSQL Windows service first." }

Write-Host "Starting the local Qdrant and Ollama containers..."
Push-Location $projectRoot
try { docker compose up -d; if ($LASTEXITCODE -ne 0) { throw "Docker services could not start. Open Docker Desktop and retry." } }
finally { Pop-Location }

$oldDemo = $env:PUBLIC_DEMO_MODE
$oldDocs = $env:DOCS_ENABLED
try {
    $env:PUBLIC_DEMO_MODE = "true"
    $env:DOCS_ENABLED = "false"
    Write-Host "Starting the website and API on http://127.0.0.1:8000"
    Write-Host "Keep this window open. In another PowerShell window, start the Cloudflare Quick Tunnel."
    Push-Location $backend
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
}
finally {
    Pop-Location
    $env:PUBLIC_DEMO_MODE = $oldDemo
    $env:DOCS_ENABLED = $oldDocs
}
