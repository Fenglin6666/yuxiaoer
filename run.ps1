# 鱼小二 · 一键启动（单店实例）
param(
    [string]$ShopId = "default",
    [int]$Port = 0
)
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
$env:YUXIAOER_SHOP_ID = $ShopId
if ($Port -gt 0) {
    $env:YUXIAOER_PORT = "$Port"
} elseif (-not $env:YUXIAOER_PORT) {
    $env:YUXIAOER_PORT = "8787"
}

$dataLabel = if ($ShopId -eq "default") { "data/" } else { "data/shops/$ShopId/" }
Write-Host ""
Write-Host "  鱼小二 · 托管客服" -ForegroundColor Green
Write-Host "  店铺: $ShopId" -ForegroundColor Cyan
Write-Host "  http://127.0.0.1:$env:YUXIAOER_PORT" -ForegroundColor Cyan
Write-Host "  通道: 原生闲鱼  ·  数据目录 $dataLabel" -ForegroundColor DarkGray
Write-Host ""

& ".\.venv\Scripts\python.exe" -m uvicorn yuxiaoer.main:app --host 127.0.0.1 --port $env:YUXIAOER_PORT
