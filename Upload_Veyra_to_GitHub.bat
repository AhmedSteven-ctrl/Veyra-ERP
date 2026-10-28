```bat
@echo off
setlocal
cd /d "%~dp0"
title Veyra ERP - Replace GitHub Repository

echo ==========================================
echo       Veyra ERP - Full Repository Update
echo ==========================================
echo.

if not exist ".git" (
    echo ERROR: Git repository is not initialized.
    pause
    exit /b 1
)

echo WARNING:
echo This will REPLACE the current GitHub branch
echo history with the new local project snapshot.
echo.
set /p CONFIRM=Are you sure? Type YES to continue:
if /i not "%CONFIRM%"=="YES" exit /b 0

echo.
echo Checking sensitive files...

git add -A
if errorlevel 1 (
    echo ERROR: Failed to stage files.
    pause
    exit /b 1
)

git diff --cached --name-only | findstr /i /r /c:"^\.env$" /c:"\.env\." /c:"\.sqlite3$" /c:"\.db$" /c:"\.venv/" /c:"venv/" /c:"__pycache__/"
if not errorlevel 1 (
    echo.
    echo STOP: Sensitive or local files may be staged.
    echo Review staged files and .gitignore before continuing.
    git status --short
    pause
    exit /b 1
)

echo.
echo Creating replacement commit...

git -c user.name="Veyra ERP Update" -c user.email="veyra-update@users.noreply.github.com" commit --allow-empty -m "Replace repository with latest Veyra ERP version"
if errorlevel 1 (
    echo ERROR: Commit failed.
    pause
    exit /b 1
)

echo.
echo Replacing GitHub branch...

git push --force -u origin HEAD
if errorlevel 1 (
    echo.
    echo ERROR: Upload failed.
    echo Check GitHub authentication, branch protection,
    echo remote settings, and repository permissions.
    pause
    exit /b 1
)

echo.
echo SUCCESS: GitHub branch has been replaced.
echo The latest local project snapshot is now uploaded.
pause
endlocal
```