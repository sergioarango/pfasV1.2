# ESP32 Stepper Controller

This folder contains the controller firmware for the ESP32-based vial positioning system. The code listens on the serial port and accepts commands to move the X and Z stepper motors, home the axes, and move between vial positions.

## Serial setup

- Baud rate: 115200
- Line ending: newline (`\n`)
- The controller reads commands using `Serial.readStringUntil('\n')`, so every command must end with a newline character.
- Commands are case-insensitive because the firmware converts the input to uppercase before parsing.

Example:

```python
import serial

ser = serial.Serial('COM3', 115200, timeout=1)
ser.write(b'MOVE_UP 200\n')
print(ser.readline().decode().strip())
```

On Windows, the port is usually something like `COM3`, `COM4`, etc. On Linux/macOS, it may be `/dev/ttyUSB0` or `/dev/ttyACM0`.

---

## General command format

### Manual movement

```text
MOVE_UP <steps>
MOVE_DOWN <steps>
MOVE_RIGHT <steps>
MOVE_LEFT <steps>
```

- `<steps>` must be a positive integer.
- The firmware validates it and replies with `ERR INVALID_STEP_COUNT` if the value is invalid or zero/negative.
- `MOVE_UP` and `MOVE_DOWN` control the Z-axis motor.
- `MOVE_RIGHT` and `MOVE_LEFT` control the X-axis motor.

Examples:

```text
MOVE_UP 20
MOVE_DOWN 100
MOVE_RIGHT 150
MOVE_LEFT 80
```

What the controller does:

- sets the motor direction
- enables the motor
- moves the stepper by the requested number of steps
- waits until the movement is complete
- disables the motor again
- prints `MOVE_COMPLETE`

---

## Homing commands

### Full home

```text
HOME_POSITION
HOME
```

This homes both axes:

1. homes Z first
2. homes X second
3. sets the current position to home
4. prints `DONE`

### Single-axis home

```text
HOME_POSITION_Z
HOME_Z

HOME_POSITION_X
HOME_X
```

- `HOME_Z` homes only the Z motor.
- `HOME_X` homes only the X motor.
- These commands print `ACK` first, then `DONE` after the homing operation.

Notes:

- Home is detected using the end-stop sensor.
- If the controller cannot find the sensor, it prints `ERR HOME NOT FOUND`.

---

## Go to vial commands

The system can move to 5 vial positions and track the current location in the variable `currentLocation`.

### Home to a specific vial

```text
HOME_TO_VIAL1
HOME_TO_VIAL2
HOME_TO_VIAL3
HOME_TO_VIAL4
HOME_TO_VIAL5
```

These commands:

- home the platform if needed
- move to the selected vial position
- update the current location to `VIAL1` ... `VIAL5`

Example:

```text
HOME_TO_VIAL3
```

This sends the device to vial 3.

---

## Move between vial positions

The firmware includes direct movement commands between all vial pairs.

### From vial 1

```text
VIAL1_TO_VIAL2
VIAL1_TO_VIAL3
VIAL1_TO_VIAL4
VIAL1_TO_VIAL5
```

### From vial 2

```text
VIAL2_TO_VIAL1
VIAL2_TO_VIAL3
VIAL2_TO_VIAL4
VIAL2_TO_VIAL5
```

### From vial 3

```text
VIAL3_TO_VIAL1
VIAL3_TO_VIAL2
VIAL3_TO_VIAL4
VIAL3_TO_VIAL5
```

### From vial 4

```text
VIAL4_TO_VIAL1
VIAL4_TO_VIAL2
VIAL4_TO_VIAL3
VIAL4_TO_VIAL5
```

### From vial 5

```text
VIAL5_TO_VIAL1
VIAL5_TO_VIAL2
VIAL5_TO_VIAL3
VIAL5_TO_VIAL4
```

These commands are designed to move between positions smartly by returning to home and then moving the X axis by a calculated distance before raising the Z axis again.

---

## Response messages from the controller

The firmware prints messages over Serial. You can read them with Python to know the action status.

Common responses:

- `ACK` - command received
- `MOVE_COMPLETE` - stepper motion finished
- `DONE` - homing or task finished
- `ERR INVALID_STEP_COUNT` - bad step value
- `ERR INVALID_VIAL_NUMBER` - vial number is not 1..5
- `ERR HOME NOT FOUND` - end-stop was not detected during homing
- `Motor already at home position`
- `Already at VIAL1, no movement` (or similar for other vial commands)

The controller also reports end-stop activity:

```text
Z endstop: ACTIVE
Z endstop: DEACTIVATED
X endstop: ACTIVE
X endstop: DEACTIVATED
```

---

## Example Python script

```python
import serial
import time

ser = serial.Serial('COM3', 115200, timeout=1)

def send_command(command: str):
    ser.write((command + "\n").encode())
    time.sleep(0.1)
    while ser.in_waiting:
        print(ser.readline().decode(errors='ignore').strip())

send_command('HOME_POSITION')
send_command('HOME_TO_VIAL1')
send_command('MOVE_RIGHT 100')
send_command('MOVE_UP 50')
```

This sends commands one by one and prints each response returned by the ESP32.

---

## Recommended usage pattern

For Python control, use this flow:

1. Open the serial connection
2. Send a command with a trailing newline
3. Wait briefly for the reply
4. Read all lines available from the serial buffer
5. Use the returned messages to confirm movement or errors

Example safe workflow:

```python
import serial
import time

ser = serial.Serial('COM3', 115200, timeout=1)

commands = [
    'HOME_POSITION',
    'HOME_TO_VIAL3',
    'VIAL3_TO_VIAL5',
    'MOVE_UP 50'
]

for cmd in commands:
    ser.write((cmd + '\n').encode())
    time.sleep(0.2)
    while ser.in_waiting:
        print(ser.readline().decode(errors='ignore').strip())
```

---

## Quick summary

The controller expects short text commands over Serial, not binary data. Most commands follow this style:

- `MOVE_* <steps>` for manual motion
- `HOME_*` for homing
- `HOME_TO_VIALn` to move to a vial
- `VIALa_TO_VIALb` to move between any two vial positions

The important rule for Python is:

```python
ser.write((command + "\n").encode())
```

Because the firmware reads until the newline character.
