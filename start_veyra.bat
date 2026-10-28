
@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Veyra ERP - Fast Startup

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

REM If Veyra is already running, open it
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if not errorlevel 1 (
    start "" "%URL%"
    exit /b 0
)

REM Open browser when server becomes available
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "$u='%URL%'; for($i=0;$i -lt 60;$i++){ try { $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',8000); $c.Close(); Start-Process $u; exit 0 } catch { if($c){$c.Dispose()}; Start-Sleep -Milliseconds 500 } }"

REM Start Django directly
"%PY%" manage.py runserver 127.0.0.1:8000

endlocal
