# 鱼小二 · 多店控制面
param([int]$Port = 0)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "请先运行 .\run.ps1 创建虚拟环境" -ForegroundColor Red
    exit 1
}

$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
if ($Port -gt 0) { $env:YUXIAOER_CONTROL_PORT = "$Port" }
if (-not $env:YUXIAOER_CONTROL_PORT) { $env:YUXIAOER_CONTROL_PORT = "8790" }

Write-Host ""
Write-Host "  鱼小二 · 多店控制面" -ForegroundColor Green
Write-Host "  http://127.0.0.1:$env:YUXIAOER_CONTROL_PORT" -ForegroundColor Cyan
Write-Host "  本机免登录；仅监听 127.0.0.1" -ForegroundColor DarkGray
Write-Host ""

& ".\.venv\Scripts\python.exe" -m uvicorn yuxiaoer.control.main:app --host 127.0.0.1 --port $env:YUXIAOER_CONTROL_PORT
