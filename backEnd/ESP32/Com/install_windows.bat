@echo off
setlocal

REM One-click installer for ESP32 GUI control app
cd /d "%~dp0"
set "APP_DIR=%CD%"

echo [1/6] Checking Python installation...
where py >nul 2>&1
if errorlevel 1 (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python was not found.
        echo Attempting to install Python with winget...
        where winget >nul 2>&1
        if errorlevel 1 (
            echo winget is not available.
            echo Please install Python 3.10+ manually from https://www.python.org/downloads/
            pause
            exit /b 1
        )

        winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
        if errorlevel 1 (
            echo Automatic Python install failed.
            echo Please install Python 3.10+ manually and run this installer again.
            pause
            exit /b 1
        )

        echo Python installed. Re-checking availability...
        where py >nul 2>&1
        if errorlevel 1 (
            where python >nul 2>&1
            if errorlevel 1 (
                echo Python still not found in PATH.
                echo Restart terminal and run install_windows.bat again.
                pause
                exit /b 1
            ) else (
                set "PY_CMD=python"
            )
        ) else (
            set "PY_CMD=py -3"
        )
    ) else (
        set "PY_CMD=python"
    )
) else (
    set "PY_CMD=py -3"
)

echo [2/6] Creating virtual environment...
if not exist ".venv\Scripts\python.exe" (
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo [3/6] Installing dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed.
    pause
    exit /b 1
)

echo [4/6] Detecting ESP32 COM port and updating env file...
python detect_esp32_port.py
if errorlevel 1 (
    echo Port auto-detection was not completed.
    echo You can still run the app and set MOTOR_PORT manually in env\.env.
)

echo [5/6] Creating Desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$desktop = [Environment]::GetFolderPath('Desktop'); $shortcutPath = Join-Path $desktop 'PFAS ESP32 Control.lnk'; $shell = New-Object -ComObject WScript.Shell; $shortcut = $shell.CreateShortcut($shortcutPath); $shortcut.TargetPath = Join-Path $env:APP_DIR 'start_gui.bat'; $shortcut.WorkingDirectory = $env:APP_DIR; $shortcut.IconLocation = \"$env:SystemRoot\\System32\\SHELL32.dll,41\"; $shortcut.Save()"
if errorlevel 1 (
    echo Desktop shortcut could not be created automatically.
    echo You can still launch the app using start_gui.bat.
) else (
    echo Desktop shortcut created: PFAS ESP32 Control
)

echo [6/6] Installation complete.
echo.
echo To start the GUI, use the Desktop icon: PFAS ESP32 Control
echo Or run: start_gui.bat
pause
exit /b 0
