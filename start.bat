@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 --version >nul 2>&1
  if not errorlevel 1 (
    py -3.12 -m venv .venv
  ) else (
    py -3 -m venv .venv
  )
  if errorlevel 1 goto failed
)
if not exist ".venv\.surface-installed" (
  ".venv\Scripts\python.exe" -m pip install -e ".[windows]"
  if errorlevel 1 goto failed
  type nul > ".venv\.surface-installed"
)
".venv\Scripts\python.exe" -m interactive_surface %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo ERROR: Interactive Surface could not start. Read the messages above.
echo If Python is missing, install Python 3.12 and reopen Command Prompt.
echo Run start.bat in Command Prompt to keep the error visible.
pause
exit /b 1
