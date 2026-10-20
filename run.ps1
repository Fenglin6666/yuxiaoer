# 鱼小二 · 多账号控制台（唯一入口）
param([int]$Port = 0)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "创建虚拟环境..." -ForegroundColor Cyan
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "未找到 uv，请先安装 uv 或手动 python -m venv .venv" -ForegroundColor Red
        exit 1
    }
    uv venv --python 3.12
    uv pip install -r requirements.txt
} else {
    & ".\.venv\Scripts\python.exe" -c "import qrcode, msgpack, multipart" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "补齐新增依赖..." -ForegroundColor Cyan
        uv pip install -r requirements.txt
    }
}

$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
if ($Port -gt 0) {
    $env:YUXIAOER_CONTROL_PORT = "$Port"
} elseif (-not $env:YUXIAOER_CONTROL_PORT) {
    $env:YUXIAOER_CONTROL_PORT = "8787"
}

Write-Host ""
Write-Host "  鱼小二 · 多账号控制台" -ForegroundColor Green
Write-Host "  http://127.0.0.1:$env:YUXIAOER_CONTROL_PORT" -ForegroundColor Cyan
Write-Host "  本机直接使用；在这里添加并扫码登录多个真实闲鱼账号" -ForegroundColor DarkGray
Write-Host ""

& ".\.venv\Scripts\python.exe" -m uvicorn yuxiaoer.control.main:app --host 127.0.0.1 --port $env:YUXIAOER_CONTROL_PORT
