@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 exit /b 1
  .venv\Scripts\python.exe -m pip install -e ".[windows]"
  if errorlevel 1 exit /b 1
)
.venv\Scripts\python.exe -m interactive_surface %*
