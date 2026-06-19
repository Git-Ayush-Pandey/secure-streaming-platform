Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "       Starting Secure Drone Client       " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Ensure we are in the client root directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir
Set-Location ..

# Verify .venv exists
if (-not (Test-Path ".venv")) {
    Write-Host "[WARNING] Virtual environment not found. Running setup..." -ForegroundColor Yellow
    & .\scripts\create_env.ps1
}

# Activate virtual environment
Write-Host "[INFO] Activating virtual environment..." -ForegroundColor Yellow
& .venv\Scripts\Activate.ps1

# Start the client
Write-Host "[INFO] Starting client application..." -ForegroundColor Yellow
python main.py

Write-Host ""
Write-Host "[INFO] Client application terminated." -ForegroundColor Cyan
