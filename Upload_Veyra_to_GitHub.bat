
@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Veyra ERP - Full GitHub Update

echo ==========================================
echo       Veyra ERP - Full Repository Update
echo ==========================================
echo.

if not exist ".git" (
    echo ERROR: Git repository is not initialized.
    pause
    exit /b 1
)

set "EXPECTED_URL=https://github.com/AhmedSteven-ctrl/Veyra-ERP.git"

echo Checking Git remote...

for /f "delims=" %%R in ('git remote get-url origin 2^>nul') do set "REMOTE_URL=%%R"

if not defined REMOTE_URL (
    echo ERROR: Remote origin is missing.
    pause
    exit /b 1
)

if /i not "%REMOTE_URL%"=="%EXPECTED_URL%" (
    echo ERROR: Unexpected remote URL:
    echo %REMOTE_URL%
    echo Expected:
    echo %EXPECTED_URL%
    pause
    exit /b 1
)

echo Remote URL verified.
echo.

echo WARNING:
echo This will REPLACE the GitHub main branch history.
echo Existing remote commits may become unreachable.
echo.
set /p CONFIRM=Type YES to continue:

if /i not "%CONFIRM%"=="YES" exit /b 0

echo.
echo Fetching remote repository...

git fetch origin
if errorlevel 1 (
    echo ERROR: Could not fetch remote repository.
    pause
    exit /b 1
)

echo.
echo Staging project files...

git add -A
if errorlevel 1 (
    echo ERROR: Failed to stage files.
    pause
    exit /b 1
)

echo.
echo Checking staged files...

set "STAGED_FILE=%TEMP%\veyra_staged_%RANDOM%.txt"

git diff --cached --name-only > "%STAGED_FILE%"

powershell -NoProfile -Command "$p=Get-Content -LiteralPath '%STAGED_FILE%'; $bad=$p | Where-Object { $_ -match '(^|/)\.env$' -or (($_ -match '(^|/)\.env\.') -and ($_ -notmatch '(^|/)\.env\.example$')) -or $_ -match '\.(sqlite|sqlite3|db)$' -or $_ -match '(^|/)(\.venv|venv|__pycache__)(/|$)' }; if($bad){Write-Host 'Blocked files:'; $bad; exit 1}"

if errorlevel 1 (
    echo.
    echo STOP: Sensitive or local files detected.
    del "%STAGED_FILE%" 2>nul
    git status --short
    pause
    exit /b 1
)

del "%STAGED_FILE%" 2>nul

echo.
echo Renaming local branch to main...

git branch -M main
if errorlevel 1 (
    echo ERROR: Could not rename branch.
    pause
    exit /b 1
)

echo.
echo Creating replacement commit...

git -c user.name="Veyra ERP Update" -c user.email="veyra-update@users.noreply.github.com" commit -m "Update Veyra ERP project snapshot"

if errorlevel 1 (
    echo ERROR: Commit failed.
    echo Check whether there are staged changes.
    pause
    exit /b 1
)

echo.
echo Uploading project to GitHub main...

git push --force-with-lease -u origin main

if errorlevel 1 (
    echo.
    echo ERROR: Upload failed.
    echo Check authentication, branch protection and permissions.
    pause
    exit /b 1
)

echo.
echo SUCCESS: Veyra ERP uploaded to GitHub.
echo Branch: main
echo.
pause
endlocal