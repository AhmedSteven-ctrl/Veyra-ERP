@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Veyra ERP - Force Update & Restart

set "URL=http://127.0.0.1:8000"
set "PY=%~dp0.venv\Scripts\python.exe"

REM Check project files
if not exist "manage.py" (
    echo ERROR: manage.py not found.
    pause
    exit /b 1
)

REM Check virtual environment
if not exist "%PY%" (
    echo ERROR: Virtual environment not found.
    echo Please create .venv and install requirements first.
    pause
    exit /b 1
)

echo ==========================================
echo   Closing Old Running Server Processes...
echo ==========================================

REM Kill any running python instance on port 8000 to force fresh reload
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /R /C:":8000 .*LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo ==========================================
echo   Running Auto-Migrations & Updates...
echo ==========================================

REM Automatically detect and create migrations for any code changes
"%PY%" manage.py makemigrations --noinput

REM Apply database migrations automatically
"%PY%" manage.py migrate --noinput

REM Seed modules catalog and Odoo chart of accounts automatically
"%PY%" manage.py seed_modules --verbosity=0
"%PY%" manage.py seed_chart_of_accounts --verbosity=0

echo ==========================================
echo   Starting Fresh Veyra ERP Server...
echo ==========================================

REM Open browser when server becomes available
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "$u='%URL%'; for($i=0;$i -lt 60;$i++){ try { $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',8000); $c.Close(); Start-Process $u; exit 0 } catch { if($c){$c.Dispose()}; Start-Sleep -Milliseconds 500 } }"

REM Start Django server with new code
"%PY%" manage.py runserver 127.0.0.1:8000

endlocal