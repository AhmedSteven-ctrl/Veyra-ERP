@echo off
REM Run once: puts a "Veyra ERP" icon on your Desktop that starts the site.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\create_shortcut.ps1"
echo.
pause
