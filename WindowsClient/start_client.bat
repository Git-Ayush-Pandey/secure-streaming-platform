@echo off
setlocal EnableDelayedExpansion

echo ========================================
echo Secure Web Server Backend Startup
echo ========================================
echo.

cd /d "%~dp0"

:: --------------------------------------------------
:: Verify Python
:: --------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

:: --------------------------------------------------
:: Create VENV if missing
:: --------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not found.
    echo [INFO] Creating virtual environment...
    python -m venv .venv

    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: --------------------------------------------------
:: Activate VENV
:: --------------------------------------------------
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)

:: --------------------------------------------------
:: Check if pip is healthy
:: --------------------------------------------------
python -m pip --version >nul 2>&1

if errorlevel 1 (
    echo.
    echo [WARNING] Corrupted virtual environment detected.
    echo [INFO] Recreating .venv...

    call deactivate >nul 2>&1

    rmdir /s /q .venv

    python -m venv .venv

    if errorlevel 1 (
        echo [ERROR] Failed to recreate virtual environment.
        pause
        exit /b 1
    )

    call .venv\Scripts\activate.bat

    python -m ensurepip --upgrade

    if errorlevel 1 (
        echo [ERROR] Failed to repair pip.
        pause
        exit /b 1
    )
)

:: --------------------------------------------------
:: Upgrade pip
:: --------------------------------------------------
echo.
echo [INFO] Upgrading pip...
python -m pip install --upgrade pip

if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip.
    pause
    exit /b 1
)

:: --------------------------------------------------
:: Install requirements
:: --------------------------------------------------
if exist requirements.txt (
    echo.
    echo [INFO] Installing dependencies...
    python -m pip install -r requirements.txt

    if errorlevel 1 (
        echo [ERROR] Failed to install requirements.
        pause
        exit /b 1
    )
) else (
    echo [WARNING] requirements.txt not found.
)

:: --------------------------------------------------
:: Start application
:: --------------------------------------------------
echo.
echo ========================================
echo Starting Application
echo ========================================
echo.

python main.py

echo.
echo Application exited.
pause