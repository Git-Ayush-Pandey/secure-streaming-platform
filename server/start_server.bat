@echo off
setlocal

title Secure Drone Stream Server Launcher

echo.
echo ==========================================
echo   Secure Drone Stream Server Launcher
echo ==========================================
echo.

cd /d "%~dp0"

REM --------------------------------------------------
REM Verify Python
REM --------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
echo [ERROR] Python is not installed.
pause
exit /b 1
)

REM --------------------------------------------------
REM First-time setup
REM --------------------------------------------------
if not exist ".venv" (

echo [INFO] First launch detected.
echo [INFO] Creating virtual environment...

python -m venv .venv

if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo [INFO] Upgrading pip...
python -m pip install --upgrade pip

echo [INFO] Installing backend dependencies...
pip install -r backend\requirements.txt

if errorlevel 1 (
    echo [ERROR] Backend dependency installation failed.
    pause
    exit /b 1
)

echo [INFO] Installing frontend dependencies...
pushd frontend
call npm install
popd

if errorlevel 1 (
    echo [ERROR] Frontend dependency installation failed.
    pause
    exit /b 1
)

)

REM --------------------------------------------------
REM Activate existing venv
REM --------------------------------------------------
call .venv\Scripts\activate.bat

REM --------------------------------------------------
REM Verify Node
REM --------------------------------------------------
node --version >nul 2>&1
if errorlevel 1 (
echo [ERROR] Node.js is not installed.
pause
exit /b 1
)

REM --------------------------------------------------
REM Start Backend
REM --------------------------------------------------
echo [INFO] Starting backend...

start "Drone Backend" cmd /k "cd /d ""%~dp0"" && call .venv\Scripts\activate.bat && python run.py --reload"

timeout /t 5 /nobreak >nul

REM --------------------------------------------------
REM Start Frontend
REM --------------------------------------------------
echo [INFO] Starting frontend...

start "Drone Frontend" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"

timeout /t 8 /nobreak >nul

REM --------------------------------------------------
REM Open Browser
REM --------------------------------------------------
start "" "http://127.0.0.1:5173"

echo.
echo ==========================================
echo Backend Started
echo Frontend Started
echo Dashboard Opened
echo ==========================================
echo.

exit /b 0