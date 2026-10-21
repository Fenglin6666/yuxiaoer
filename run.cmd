@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    where uv >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python venv not found and uv is not installed.
        echo Install uv first: https://github.com/astral-sh/uv
        pause
        exit /b 1
    )
    echo Creating virtual environment...
    uv venv --python 3.12
    if errorlevel 1 goto :fail
    uv pip install -r requirements.txt
    if errorlevel 1 goto :fail
) else (
    ".venv\Scripts\python.exe" -c "import qrcode, msgpack, multipart" >nul 2>nul
    if errorlevel 1 (
        where uv >nul 2>nul
        if errorlevel 1 (
            echo [ERROR] Missing dependencies and uv is not installed.
            pause
            exit /b 1
        )
        echo Installing missing dependencies...
        uv pip install -r requirements.txt
        if errorlevel 1 goto :fail
    )
)

set "PYTHONPATH=%CD%\src"
if not defined YUXIAOER_CONTROL_PORT set "YUXIAOER_CONTROL_PORT=8787"

echo.
echo   YuXiaoEr - multi-account console
echo   http://127.0.0.1:%YUXIAOER_CONTROL_PORT%
echo   Local only. Press Ctrl+C to stop.
echo.

".venv\Scripts\python.exe" -m uvicorn yuxiaoer.control.main:app --host 127.0.0.1 --port %YUXIAOER_CONTROL_PORT%
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo [ERROR] Startup failed. Check the output above.
pause
exit /b 1
