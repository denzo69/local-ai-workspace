@echo off
setlocal
title Restart Local AI Workspace

set "APP_DIR=%~dp0"
for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"
set "VENV_PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "VERSION_FILE=%PROJECT_DIR%\VERSION"

set "APP_VERSION=unknown"
if exist "%VERSION_FILE%" (
    set /p APP_VERSION=<"%VERSION_FILE%"
)

set "GIT_BUILD=unknown"
for /f "usebackq delims=" %%G in (`git -C "%PROJECT_DIR%" rev-parse --short HEAD 2^>nul`) do set "GIT_BUILD=%%G"

echo.
echo Restarting Local AI Workspace
echo Project: %PROJECT_DIR%
echo Version: v%APP_VERSION%
echo Build:   %GIT_BUILD%
echo.

echo Stopping existing uvicorn processes for app.main, if any...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -like '*uvicorn*' -and $_.CommandLine -like '*app.main:app*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

cd /d "%PROJECT_DIR%"

echo.
echo Starting backend...
echo Open: http://127.0.0.1:8080/ui
echo.

if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8080
) else (
    echo Virtual environment not found, trying system Python:
    echo %VENV_PYTHON%
    echo.
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
)

pause
