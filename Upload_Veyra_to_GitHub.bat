
@echo off
cd /d "%~dp0"
title Veyra ERP - GitHub Upload

if not exist ".git" (
    echo Git repository is not initialized.
    pause
    exit /b 1
)

echo Checking for sensitive files...
git status --short
echo.
echo Review the list above before uploading.
set /p CONFIRM=Continue with commit and push? (Y/N):
if /i not "%CONFIRM%"=="Y" exit /b 0

git add -A
git diff --cached --name-only | findstr /i /r /c:"^\.env$" /c:"\.sqlite3$" /c:"\.venv/"
if not errorlevel 1 (
    echo STOP: Sensitive files may be staged.
    echo Review .gitignore and staged files before continuing.
    pause
    exit /b 1
)

git diff --cached --quiet
if not errorlevel 1 (
    echo No changes to commit.
    pause
    exit /b 0
)

git commit -m "Update Veyra ERP"
if errorlevel 1 (
    pause
    exit /b 1
)

git push -u origin HEAD
if errorlevel 1 (
    echo Upload failed. Check GitHub login and remote settings.
    pause
    exit /b 1
)

echo Upload completed successfully.
pause
