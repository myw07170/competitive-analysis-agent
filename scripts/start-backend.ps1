# 以开发模式启动 FastAPI 后端。
# 在仓库根目录运行：  .\scripts\start-backend.ps1

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "backend")

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtualenv..." -ForegroundColor Cyan
    python -m venv .venv
}

& .\.venv\Scripts\Activate.ps1

Write-Host "Installing requirements (idempotent)..." -ForegroundColor Cyan
pip install -q -r requirements.txt

if (-not (Test-Path ".env")) {
    Write-Host "No .env file found. Copying .env.example -> .env (mock mode by default)." -ForegroundColor Yellow
    Copy-Item .env.example .env
}

Write-Host "Starting FastAPI on http://127.0.0.1:8000 ..." -ForegroundColor Green
python main.py
