@echo off
setlocal
title Interactive Surface - Windows Event Preparation
echo.
echo Interactive Surface - setup for closed-lid event operation
echo This changes the current Windows AC power plan and creates a Private-only firewall rule.
echo Keep the laptop connected to AC power. Battery settings will not change.
echo.
fltmc >nul 2>&1
if errorlevel 1 (
  echo ERROR: Run this file using Right-click - Run as administrator.
  pause
  exit /b 1
)
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
if errorlevel 1 goto failed
powercfg /change standby-timeout-ac 0
if errorlevel 1 goto failed
powercfg /change hibernate-timeout-ac 0
if errorlevel 1 goto failed
powercfg /change monitor-timeout-ac 0
if errorlevel 1 goto failed
powercfg /setactive SCHEME_CURRENT
if errorlevel 1 goto failed
powershell -NoProfile -Command "if (-not (Get-NetFirewallRule -Name 'InteractiveSurface-LAN-8765' -ErrorAction SilentlyContinue)) { New-NetFirewallRule -Name 'InteractiveSurface-LAN-8765' -DisplayName 'Interactive Surface - LAN TCP 8765' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -Profile Private | Out-Null }"
if errorlevel 1 goto failed
echo.
echo DONE: AC lid action set to Do nothing, AC sleep/hibernate/monitor timeouts disabled.
echo DONE: Firewall rule allows inbound TCP 8765 only on Private network profile.
echo NEXT: Connect to trusted Wi-Fi, select Private network and Win+P - Second screen only.
echo NEXT: Start the app via start.bat; scan the terminal QR from your phone BEFORE closing the lid.
echo NOTE: Restore previous power options manually via Control Panel after the event.
echo.
pause
exit /b 0
:failed
echo.
echo ERROR: Windows configuration did not complete. Review the error above.
pause
exit /b 1
