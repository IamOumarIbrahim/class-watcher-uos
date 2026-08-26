# install.ps1 - Set up the UoS Seat Monitor on Windows
# Run from the uos-seat-monitor directory.

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "=== UoS Seat Monitor - Installation ===" -ForegroundColor Cyan

# Create virtual environment with Python 3.11+
Write-Host "`nCreating virtual environment..." -ForegroundColor Yellow
py -3.11 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Failed to create venv. Is Python 3.11 installed? Run: py -3.11 --version" }

Write-Host "Installing dependencies..." -ForegroundColor Yellow
.\.venv\Scripts\python.exe -m pip install --upgrade pip -q
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed." }

# Copy .env.example -> .env if not present.
if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Host "`n.env created from template. Edit it now:" -ForegroundColor Green
    Write-Host "  Set NTFY_TOPIC to your private ntfy topic name." -ForegroundColor White
    notepad .env
} else {
    Write-Host "`n.env already exists - skipping copy." -ForegroundColor Gray
}

Write-Host "`n=== Installation complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Quick start:" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\python.exe monitor.py --test-notification"
Write-Host "  .\.venv\Scripts\python.exe monitor.py --once"
Write-Host "  .\.venv\Scripts\python.exe monitor.py"
Write-Host ""
Write-Host "To stop monitoring a CRN after you register it:" -ForegroundColor Cyan
Write-Host "  Add the CRN to 'registered_crns' in config.json and remove it from 'required'."
