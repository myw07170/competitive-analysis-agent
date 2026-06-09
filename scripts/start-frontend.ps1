# 以开发模式启动 Vite 前端。
# 在仓库根目录运行：  .\scripts\start-frontend.ps1

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "frontend")

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing node modules (first run)..." -ForegroundColor Cyan
    if (Get-Command pnpm -ErrorAction SilentlyContinue) {
        pnpm install
    } elseif (Get-Command npm -ErrorAction SilentlyContinue) {
        npm install
    } else {
        throw "Neither pnpm nor npm found in PATH."
    }
}

Write-Host "Starting Vite on http://127.0.0.1:5173 ..." -ForegroundColor Green
if (Get-Command pnpm -ErrorAction SilentlyContinue) {
    pnpm dev
} else {
    npm run dev
}
