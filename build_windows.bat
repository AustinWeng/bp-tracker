@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ===============================================
echo   bp-tracker  -  Windows build
echo ===============================================
echo.

REM 1. Find Python
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo         Install Python 3.10+ from https://www.python.org/downloads/
    echo         IMPORTANT: check "Add python.exe to PATH" during install.
    pause
    exit /b 1
)

for /f "delims=" %%v in ('python --version') do echo [OK] %%v

REM 2. Create venv if missing
if not exist ".venv\Scripts\python.exe" (
    echo [..] Creating virtual environment .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv
        pause
        exit /b 1
    )
)

REM 3. Install packages
echo [..] Installing packages ...
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
if errorlevel 1 goto pip_fail
".venv\Scripts\pip.exe" install -q -r requirements.txt
if errorlevel 1 goto pip_fail
".venv\Scripts\pip.exe" install -q waitress pyinstaller pystray pillow
if errorlevel 1 goto pip_fail
goto pip_ok

:pip_fail
echo [ERROR] Package install failed
pause
exit /b 1

:pip_ok

REM 4. Clean old build
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist

REM 5. Run PyInstaller
echo.
echo [..] Building executable (1-3 minutes) ...
echo.
".venv\Scripts\pyinstaller.exe" bp_tracker.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller failed
    pause
    exit /b 1
)

REM 6. Copy existing DB to dist (if present)
if exist "phase2_db\bp.db" (
    echo [..] Copying existing bp.db to dist\
    copy /y "phase2_db\bp.db" "dist\bp.db" >nul
)

REM 7. Done
echo.
echo ===============================================
echo   [OK] Build complete
echo ===============================================
echo.
echo   Executable: dist\bp-tracker.exe
echo   Database:   dist\bp.db   (next to exe, copy/backup as you wish)
echo.
echo   Usage:
echo     1. Copy the entire dist\ folder to wherever you want
echo     2. Double-click bp-tracker.exe
echo     3. Browser opens at http://localhost:5050
echo.
pause
