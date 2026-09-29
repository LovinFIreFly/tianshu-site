# Thin wrapper. Real logic lives in build_desktop.py
# (Windows PowerShell reads .ps1 as GBK, so non-ASCII here would break strings.)
#   Usage: powershell -ExecutionPolicy Bypass -File tools\build_desktop.ps1
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = 'utf-8'
python tools\build_desktop.py
exit $LASTEXITCODE
