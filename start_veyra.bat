@echo off
setlocal
cd /d "%~dp0"
title Veyra ERP

REM ---- settings you can change ----
set "URL=http://127.0.0.1:8000"
set "PORT=8000"
REM 1 = enable all modules for the demo company on every launch, 0 = only when the demo data is first created
set "ENABLE_ALL=1"
REM ---------------------------------

REM Already running? Just open the browser.
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
    start "" "%URL%"
    exit /b 0
)

if exist ".venv\Scripts\python.exe" goto :have_venv
echo First run: preparing the environment, this can take a few minutes...
set "PY=py"
where py >nul 2>nul || set "PY=python"
%PY% -m venv .venv || goto :error
call ".venv\Scripts\activate.bat" || goto :error
python -m pip install -r requirements.txt || goto :error
goto :prepared

:have_venv
call ".venv\Scripts\activate.bat" || goto :error

:prepared

echo Updating the database...
python manage.py makemigrations accounts core inventory accounting sales purchasing || goto :error
python manage.py migrate || goto :error
python manage.py seed_modules || goto :error
python manage.py seed_demo --if-empty || goto :error
if "%ENABLE_ALL%"=="1" python manage.py enable_all_modules 2>nul

echo.
echo Starting Veyra ERP at %URL%
echo Demo manager login: ahmed
echo Keep this window open while you work. Close it to stop the server.
echo.
start "" /min cmd /c "timeout /t 4 /nobreak >nul & start %URL%"
python manage.py runserver 127.0.0.1:%PORT%
echo.
echo The server stopped.
pause
exit /b 0

:error
echo.
echo Something went wrong. Read the message above.
echo If Python is not installed, get it from python.org and tick Add Python to PATH.
pause
exit /b 1
