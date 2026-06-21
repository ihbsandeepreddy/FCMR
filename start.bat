@echo off
echo Starting SanGir Automations...

:: Create venv if it doesn't exist
if not exist ".venv" (
    echo Setting up virtual environment for first time...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -e ".[dev]"
) else (
    call .venv\Scripts\activate.bat
)

:: Pull latest code
echo Pulling latest changes from GitHub...
git pull origin main

:: Start the app
echo.
echo ============================================
echo   App running at http://localhost:8000
echo   Press Ctrl+C to stop
echo ============================================
echo.
uvicorn app.main:app --port 8000

pause
