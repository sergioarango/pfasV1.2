# ESP32 Motor Control GUI - Installation Guide

This folder contains a desktop GUI and serial communication layer to control the ESP32 motor firmware using buttons.

## Files in this folder

- `esp32_control_gui.py` - Button-based desktop interface
- `esp32com.py` - Serial communication and fast command interface
- `install_windows.bat` - One-click Windows installer
- `uninstall_windows.bat` - One-click Windows uninstall helper
- `start_gui.bat` - Launch script for the GUI
- `detect_esp32_port.py` - Helper that auto-detects COM port and updates env file
- `requirements.txt` - Python dependency list

## Requirements

- Windows 10/11
- USB connection to ESP32
- Arduino Serial Monitor closed while using this app

## Quick install (recommended)

1. Open this folder: `backEnd/ESP32/Com`
2. Double-click `install_windows.bat`
3. Wait until the installer finishes
4. Use the Desktop icon `PFAS ESP32 Control`

## What the installer does

`install_windows.bat` performs these steps:

1. Checks if Python exists
2. If Python is missing, tries to install Python automatically with `winget`
3. Creates a local virtual environment in `.venv`
4. Installs required libraries from `requirements.txt`
5. Runs COM auto-detection with `detect_esp32_port.py`
6. Writes/updates `MOTOR_PORT` and `MOTOR_BAUD` in `env/.env`
7. Creates Desktop shortcut `PFAS ESP32 Control`

## Environment configuration

The app reads serial settings from:

- `env/.env`

Expected values:

```env
MOTOR_PORT=COM6
MOTOR_BAUD=115200
```

If auto-detection picks the wrong port, edit `MOTOR_PORT` manually.

## Manual installation (alternative)

Use this only if you do not want to run the batch installer.

1. Open a terminal in `backEnd/ESP32/Com`
2. Create venv:

```powershell
python -m venv .venv
```

3. Activate venv:

```powershell
.venv\Scripts\activate
```

4. Install dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

5. Run port detector:

```powershell
python detect_esp32_port.py
```

6. Start GUI:

```powershell
python esp32_control_gui.py
```

## First run test

After GUI opens:

1. Click `Connect`
2. Click `HOME_POSITION`
3. Click `Go Vial 1`
4. Check the response log for ACK/completion lines

## Troubleshooting

### Python not found

- Install Python 3.10+ manually from: https://www.python.org/downloads/
- Re-run `install_windows.bat`

### Port busy / cannot open COM port

- Close Arduino Serial Monitor
- Close any other serial tool using the same COM port
- Reconnect USB cable and retry

### Wrong COM port selected

- Open `env/.env`
- Set correct port manually, for example:

```env
MOTOR_PORT=COM6
MOTOR_BAUD=115200
```

### GUI starts but no motor movement

- Verify firmware is flashed on ESP32
- Verify motor drivers and power wiring
- Test from GUI with `HOME_POSITION` first

## Running in daily use

After initial installation, use:

- Desktop icon: `PFAS ESP32 Control`
- `start_gui.bat`

No need to reinstall unless dependencies or Python environment changed.

## Uninstall process

You can remove the local app setup without deleting project source code.

### Quick uninstall (recommended)

1. Open this folder: `backEnd/ESP32/Com`
2. Double-click `uninstall_windows.bat`
3. Wait until uninstall finishes

`uninstall_windows.bat` does:

1. Removes Desktop shortcut `PFAS ESP32 Control`
2. Removes local virtual environment `.venv`
3. Keeps your source files and `env/.env`

### What is not removed

- System Python installation
- Project source files (`esp32_control_gui.py`, `esp32com.py`, etc.)
- `env/.env` configuration file

### Full manual cleanup (optional)

If you want to completely remove all local artifacts from this module:

1. Delete folder `backEnd/ESP32/Com/.venv` if it still exists
2. Delete Desktop shortcut `PFAS ESP32 Control`
3. Optionally delete `backEnd/ESP32/Com/__pycache__`
