@echo off
setlocal EnableDelayedExpansion

title Secure Screen Streaming Server

echo.
echo ==========================================
echo      Secure Screen Streaming Server
echo ==========================================
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
REM Verify Node.js
REM --------------------------------------------------
node --version >nul 2>&1
if errorlevel 1 (
echo [ERROR] Node.js is not installed or not in PATH.
pause
exit /b 1
)

REM --------------------------------------------------
REM Create VENV if missing
REM --------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
echo [INFO] Creating virtual environment...
python -m venv .venv

```
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)
```

)

REM --------------------------------------------------
REM Activate VENV
REM --------------------------------------------------
call ".venv\Scripts\activate.bat"

echo.
echo [INFO] Upgrading pip...
python -m pip install --upgrade pip

echo.
echo [INFO] Installing backend dependencies...
python -m pip install -r backend\requirements.txt

REM --------------------------------------------------
REM Install frontend dependencies
REM --------------------------------------------------
if exist "frontend\package.json" (
pushd frontend
call npm install
popd
)

REM --------------------------------------------------
REM Start Backend Terminal
REM --------------------------------------------------
echo.
echo [INFO] Starting backend...

start "Backend" cmd /k "cd /d %~dp0 && call .venv\Scripts\activate.bat && python run.py"

timeout /t 5 /nobreak >nul

REM --------------------------------------------------
REM Start Frontend Terminal
REM --------------------------------------------------
echo.
echo [INFO] Starting frontend...

start "Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 8 /nobreak >nul

REM --------------------------------------------------
REM Open Dashboard
REM --------------------------------------------------
start "" http://127.0.0.1:5173

echo.
echo ==========================================
echo Backend Started
echo Frontend Started
echo Dashboard Opened
echo ==========================================
echo.

exit /b 0
