# Build script for Windows using PyInstaller
# Usage: Open PowerShell, activate your venv, then run:
#   .\build_exe.ps1

pyinstaller --onefile --windowed --name StardanceDashboard app_gui.py
