@echo off
title Start Local AI Workspace

set "APP_DIR=%~dp0"
for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"

set "VENV_PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"

echo.
echo Starting Local AI Workspace...
echo App folder: %APP_DIR%
echo Project folder: %PROJECT_DIR%
echo Tip: use app\restart_local_ai_workspace.bat if an old backend may still be running.
echo.

cd /d "%PROJECT_DIR%"

if exist "%VENV_PYTHON%" (
    echo Using virtual environment Python:
    echo %VENV_PYTHON%
    echo.
    "%VENV_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8080
) else (
    echo Virtual environment not found:
    echo %VENV_PYTHON%
    echo.
    echo Trying system Python instead...
    echo.
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
)

pause
