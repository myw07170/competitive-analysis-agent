# 运行一键 CLI 演示（无界面）。
# 用法：  .\scripts\run-demo.ps1 -Product "Notion" -Market us

param(
    [Parameter(Mandatory=$true)][string]$Product,
    [string]$Market = "us",
    [string]$Extras = "",
    [switch]$Json
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "backend")

if (Test-Path ".venv\Scripts\Activate.ps1") {
    & .\.venv\Scripts\Activate.ps1
} else {
    Write-Host "No virtualenv found — run start-backend.ps1 once to set it up." -ForegroundColor Yellow
    exit 1
}

$args = @("-m", "app.scripts.demo", "--product", $Product, "--market", $Market)
if ($Extras) { $args += @("--extras", $Extras) }
if ($Json)   { $args += "--json" }

python @args
