$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

python -m pip install -e ".[dev]"
$env:PYTHONPATH = "src"
python -m pytest --basetemp tests/.tmp -p no:cacheprovider
python -m PyInstaller --noconfirm --clean usb4431_monitor.spec

Write-Host "Build complete: dist\USB4431-LongDrift\USB4431-LongDrift.exe"

