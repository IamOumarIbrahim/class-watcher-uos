# run.ps1 - Start the UoS Seat Monitor
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir
Write-Host "Starting UoS Seat Monitor..." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop.`n" -ForegroundColor Gray
.\.venv\Scripts\python.exe monitor.py $args
