@echo off
setlocal EnableDelayedExpansion

title Secure Streaming Client

echo.
echo ========================================
echo Secure Streaming Client Startup
echo ========================================
echo.

cd /d "%~dp0"

REM --------------------------------------------------
REM Verify Python
REM --------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
echo [ERROR] Python is not installed or not in PATH.
pause
exit /b 1
)

REM --------------------------------------------------
REM Create VENV if missing
REM --------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
echo [INFO] Creating virtual environment...
python -m venv .venv
)

REM --------------------------------------------------
REM Repair VENV if broken
REM --------------------------------------------------
if not exist ".venv\Scripts\activate.bat" (
echo.
echo [WARNING] Broken virtual environment detected.
echo [INFO] Recreating .venv...

```
if exist ".venv" (
    rmdir /s /q ".venv"
)

python -m venv .venv

if errorlevel 1 (
    echo [ERROR] Failed to recreate virtual environment.
    pause
    exit /b 1
)
```

)

REM --------------------------------------------------
REM Activate VENV
REM --------------------------------------------------
call ".venv\Scripts\activate.bat"

if errorlevel 1 (
echo [ERROR] Failed to activate virtual environment.
pause
exit /b 1
)

REM --------------------------------------------------
REM Upgrade pip
REM --------------------------------------------------
echo.
echo [INFO] Upgrading pip...
python -m pip install --upgrade pip

REM --------------------------------------------------
REM Install dependencies
REM --------------------------------------------------
if exist "requirements.txt" (
echo.
echo [INFO] Installing dependencies...
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)

)

REM --------------------------------------------------
REM Start Client
REM --------------------------------------------------
echo.
echo ========================================
echo Starting Application
echo ========================================
echo.

python main.py

echo.
echo Application exited.
pause
