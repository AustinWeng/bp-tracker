@echo off
REM 血壓記錄系統 - Windows 一鍵打包腳本
REM 在 Windows 機器上雙擊執行此檔案,產生 dist\bp-tracker.exe (單檔可執行)

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ===============================================
echo   bp-tracker  -  Windows build
echo ===============================================
echo.

REM 1. 找 Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [X] 找不到 Python。請先安裝 Python 3.10 以上 (https://www.python.org/downloads/)
    echo     安裝時記得勾選 "Add python.exe to PATH"
    pause
    exit /b 1
)

for /f "delims=" %%v in ('python --version') do echo [OK] %%v

REM 2. 建 venv (若不存在)
if not exist ".venv\Scripts\python.exe" (
    echo [..] 建立虛擬環境 .venv ...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [X] 建立 venv 失敗
        pause
        exit /b 1
    )
)

REM 3. 安裝套件
echo [..] 安裝套件 ...
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
".venv\Scripts\pip.exe" install -q -r requirements.txt
".venv\Scripts\pip.exe" install -q waitress pyinstaller
if %errorlevel% neq 0 (
    echo [X] 套件安裝失敗
    pause
    exit /b 1
)

REM 4. 清掉舊 build
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist

REM 5. PyInstaller
echo.
echo [..] 開始打包 (可能需要 1-3 分鐘) ...
echo.
".venv\Scripts\pyinstaller.exe" bp_tracker.spec --noconfirm
if %errorlevel% neq 0 (
    echo.
    echo [X] 打包失敗
    pause
    exit /b 1
)

REM 6. 複製現有 DB / 校對 Excel 到 dist (若存在)
if exist "phase2_db\bp.db" (
    echo [..] 複製現有 bp.db 到 dist\
    copy /y "phase2_db\bp.db" "dist\bp.db" >nul
)

REM 7. 顯示結果
echo.
echo ===============================================
echo   [OK] 打包完成
echo ===============================================
echo.
echo   執行檔: dist\bp-tracker.exe
echo   資料庫: dist\bp.db          (與 exe 同目錄,可備份/搬移)
echo.
echo   使用方式:
echo     1. 把整個 dist\ 資料夾複製到目標位置
echo     2. 雙擊 bp-tracker.exe
echo     3. 瀏覽器會自動開啟 http://localhost:5050
echo.
pause
