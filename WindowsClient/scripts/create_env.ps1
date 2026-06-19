Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   Secure Drone Client Environment Setup   " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Ensure we are in the client root directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir
Set-Location ..

# Verify Python
python --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python is not installed or not in PATH."
    Exit 1
}

# Create virtual environment if missing
if (-not (Test-Path ".venv")) {
    Write-Host "[INFO] Creating virtual environment (.venv)..." -ForegroundColor Yellow
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create virtual environment."
        Exit 1
    }
}

# Activate virtual environment
Write-Host "[INFO] Activating virtual environment..." -ForegroundColor Yellow
& .venv\Scripts\Activate.ps1

# Upgrade pip
Write-Host "[INFO] Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install dependencies
Write-Host "[INFO] Installing dependencies from requirements.txt..." -ForegroundColor Yellow
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Error "Dependency installation failed."
    Exit 1
}

Write-Host ""
Write-Host "[SUCCESS] Client environment configured successfully!" -ForegroundColor Green
Write-Host "To run the client, execute: .\scripts\run_client.ps1" -ForegroundColor Green
