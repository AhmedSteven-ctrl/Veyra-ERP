@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"
if errorlevel 1 goto :failed
echo.
echo Done. Look for Veyra ERP on your Desktop.
pause
exit /b 0

:failed
echo.
echo Could not create the shortcut. Read the message above.
pause
exit /b 1
