# run_gui.ps1 - Start the UoS Course Seat Monitor Graphical Interface
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir
Write-Host "Launching UoS Seat Monitor GUI..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe gui.py
