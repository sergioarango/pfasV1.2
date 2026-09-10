@echo off
setlocal

REM One-click uninstall for ESP32 GUI control app
cd /d "%~dp0"
set "APP_DIR=%CD%"
set "DESKTOP_LINK=%USERPROFILE%\Desktop\PFAS ESP32 Control.lnk"

echo [1/3] Closing launcher dependencies...
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat >nul 2>&1
)

echo [2/3] Removing Desktop shortcut...
if exist "%DESKTOP_LINK%" (
    del /f /q "%DESKTOP_LINK%"
    if errorlevel 1 (
        echo Could not remove Desktop shortcut automatically.
    ) else (
        echo Desktop shortcut removed.
    )
) else (
    echo Desktop shortcut was not found.
)

echo [3/3] Removing local virtual environment...
if exist ".venv" (
    rmdir /s /q ".venv"
    if errorlevel 1 (
        echo Could not remove .venv automatically.
        echo Close all terminals/apps using this folder and try again.
        pause
        exit /b 1
    ) else (
        echo .venv removed.
    )
) else (
    echo No .venv folder found.
)

echo.
echo Uninstall complete.
echo Notes:
echo - Project source files were kept.
echo - env\.env was not deleted.
echo - Python system installation was not removed.
pause
exit /b 0
