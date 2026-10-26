@echo off
REM Veyra ERP - first-time setup on Windows (safe to run again)
if not exist .venv\Scripts\python.exe (
    py -m venv .venv || goto :error
)
call .venv\Scripts\activate || goto :error
python -m pip install -r requirements.txt || goto :error
REM migrations files must exist (create them once, then keep them in the project)
python manage.py makemigrations accounts core inventory accounting sales purchasing || goto :error
python manage.py migrate || goto :error
python manage.py seed_modules || goto :error
python manage.py seed_demo || goto :error
echo.
echo Done. Next:
echo   python manage.py seed_owner     (creates the admin account, prints its password once)
echo   python manage.py runserver      (then open http://127.0.0.1:8000)
goto :eof

:error
echo.
echo Setup failed. Read the message above.
exit /b 1
