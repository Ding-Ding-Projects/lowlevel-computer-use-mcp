@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-installer-root.ps1" %*
exit /b %errorlevel%
