@echo off
REM Veyra ERP launcher: double-click to start the server and open the site.
REM It prepares everything that is needed (safe to run any number of times).
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Veyra ERP
set "URL=http://127.0.0.1:8000"

REM 0) Already running? Just open the browser.
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if not errorlevel 1 (
    echo Veyra is already running. Opening the browser...
    start "" "%URL%"
    exit /b 0
)

REM 1) Python + virtual environment
set "PY=py"
where py >nul 2>&1 || set "PY=python"
if not exist ".venv\Scripts\python.exe" (
    echo Creating the virtual environment...
    %PY% -m venv .venv || goto :error
)
call ".venv\Scripts\activate.bat" || goto :error

REM 2) Libraries (only when requirements.txt changed since the last install)
fc /b requirements.txt ".venv\requirements.stamp" >nul 2>&1
if errorlevel 1 (
    echo Installing the libraries...
    python -m pip install -r requirements.txt || goto :error
    copy /y requirements.txt ".venv\requirements.stamp" >nul
)

REM 3) Database: migrations every time, demo data only on the very first run
set "FIRST_RUN=0"
if not exist "db.sqlite3" set "FIRST_RUN=1"
python manage.py makemigrations accounts core inventory accounting sales purchasing || goto :error
python manage.py migrate || goto :error
python manage.py seed_modules || goto :error
if "%FIRST_RUN%"=="1" (
    echo First run: loading the demo company...
    python manage.py seed_demo || goto :error
    python manage.py enable_all_modules || goto :error
)

REM 4) Open the browser as soon as the server answers, then run the server in this window
start "" /b powershell -NoProfile -Command "for($i=0;$i -lt 60;$i++){ try{ $c=New-Object Net.Sockets.TcpClient('127.0.0.1',8000); $c.Close(); break }catch{ Start-Sleep -Milliseconds 500 } }; Start-Process '%URL%'"
echo.
echo ================================================
echo   Veyra ERP is running at %URL%
echo   Close this window (or press Ctrl+C) to stop.
echo ================================================
echo.
python manage.py runserver 127.0.0.1:8000
echo.
echo The server has stopped.
pause
exit /b 0

:error
echo.
echo Something went wrong. Read the message above.
pause
exit /b 1
