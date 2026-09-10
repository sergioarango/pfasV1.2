"""Serial communication interface between Raspberry Pi backend and ESP32 motor controller.

This module mirrors the backend usage style of the Potentiostat class:
- create class object in backend
- call high-level methods for each routine step
- keep command orchestration in backend, real-time motion in ESP32 firmware
"""

import json
import logging
import os
import sys
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError as exc:
    raise RuntimeError(
        "pyserial is not installed. Run: pip install pyserial"
    ) from exc


class MotorsCom:
    """High-level interface to control ESP32 motor firmware using serial commands."""

    def __init__(self, device_port=None, baud_rate=None, timeout_s=1.0):
        self.DEVICE_PORT = device_port
        self.BAUD_RATE = baud_rate
        self.TIMEOUT_S = timeout_s
        self.LOG = logging.getLogger(__name__)
        self._ser = None

    def _load_env_file(self):
        """Load environment variables from the project .env file if present."""
        env_file = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "env", ".env")
        )
        if not os.path.exists(env_file):
            return

        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)

    def _resolve_port_and_baud(self):
        """Resolve serial port and baud from args, env vars, or auto-detection."""
        self._load_env_file()

        env_port = os.getenv("MOTOR_PORT")
        env_baud = os.getenv("MOTOR_BAUD")

        port = (env_port or self.DEVICE_PORT or "").strip()
        baudrate = self.BAUD_RATE

        if env_baud:
            try:
                baudrate = int(env_baud)
            except ValueError as exc:
                raise ValueError(f"Invalid MOTOR_BAUD value: {env_baud}") from exc

        if not port:
            port = self._auto_detect_port()

        if baudrate is None:
            baudrate = 115200

        return port, int(baudrate)

    def _auto_detect_port(self):
        """Auto-detect a likely ESP32 serial port."""
        candidates = []
        for p in list_ports.comports():
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if any(tag in desc for tag in ("esp32", "cp210", "ch340", "usb serial")) or "10c4" in hwid:
                candidates.append(p.device)

        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            return candidates[0]

        raise RuntimeError(
            "No ESP32 serial port auto-detected. Set MOTOR_PORT or pass device_port explicitly."
        )

    def connect(self):
        """Open serial connection to ESP32. Safe to call multiple times."""
        if self._ser and self._ser.is_open:
            return

        port, baudrate = self._resolve_port_and_baud()
        self.LOG.info("Connecting to ESP32 on %s @ %s", port, baudrate)
        print(f"DEBUG: opening serial port {port!r} at {baudrate}")

        try:
            self._ser = serial.Serial(port=port, baudrate=baudrate, timeout=self.TIMEOUT_S)
        except serial.SerialException as exc:
            raise RuntimeError(f"Could not open serial port {port!r}. Check COM port or USB cable.") from exc

        # Give firmware time to finish reset after serial open.
        # ESP32 boards often reboot on serial open.
        time.sleep(1.5)
        self.flush_input()

    def disconnect(self):
        """Close serial connection if open."""
        if self._ser and self._ser.is_open:
            self._ser.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.disconnect()

    def flush_input(self):
        """Clear unread serial input buffer."""
        if self._ser and self._ser.is_open:
            self._ser.reset_input_buffer()

    def _readline(self):
        """Read one line from serial and decode UTF-8 safely."""
        raw = self._ser.readline()
        if not raw:
            return ""
        return raw.decode("utf-8", errors="replace").strip()

    def _parse_line(self, line):
        """Parse a firmware line as JSON if possible, otherwise return text."""
        if not line:
            return {"type": "timeout", "raw": ""}
        try:
            payload = json.loads(line)
            return {"type": "json", "data": payload, "raw": line}
        except json.JSONDecodeError:
            return {"type": "text", "data": line, "raw": line}

    def send_command(self, command, wait_response=True, response_timeout_s=8.0):
        """Send one command string to ESP32 and optionally wait for response lines.

        Command protocol expectation (line-based):
        - Raspberry sends: COMMAND\n
        - ESP32 replies: ACK/ERR/DONE/JSON status lines\n
        """
        self.connect()

        wire = f"{command}\n".encode("utf-8")
        print(f"DEBUG: sending command -> {command!r} bytes={wire!r}")
        self.LOG.debug("TX -> %s", command)
        self._ser.write(wire)
        self._ser.flush()

        if not wait_response:
            return []

        end_at = time.time() + response_timeout_s
        responses = []

        cmd_upper = command.strip().upper()
        is_multi_stage_vial_move = cmd_upper.startswith("HOME_TO_VIAL") or (
            cmd_upper.startswith("VIAL") and "_TO_VIAL" in cmd_upper
        )
        move_complete_count = 0

        # ACK means command accepted. For multi-stage moves, wait for both MOVE_COMPLETE events.
        if is_multi_stage_vial_move:
            completion_tokens = ("DONE", "DEVICE IS NOW IN VIAL", "ERR", "ERROR")
        else:
            completion_tokens = ("DONE", "MOVE_COMPLETE", "ERR", "ERROR")

        while time.time() < end_at:
            line = self._readline()
            if not line:
                continue

            parsed = self._parse_line(line)
            responses.append(parsed)
            print(f"DEBUG: received <- {parsed['raw']!r}")
            self.LOG.debug("RX <- %s", parsed["raw"])

            raw_upper = parsed["raw"].upper()
            if "MOVE_COMPLETE" in raw_upper:
                move_complete_count += 1

            if is_multi_stage_vial_move and move_complete_count >= 2:
                break

            if any(token in raw_upper for token in completion_tokens):
                break

        if wait_response and not responses:
            print(f"DEBUG: no response received for command {command!r} within {response_timeout_s}s")

        return responses

    def get_status(self):
        raise NotImplementedError("Firmware does not implement STATUS command.")

    # High-level commands aligned with your routine descriptions.
    def home_position(self):
        return self.send_command("HOME_POSITION", response_timeout_s=60.0)

    #Zplatform home position
    def zplatform_home(self):
        return self.send_command("HOME_Z", response_timeout_s=45.0)

    #home to... movement commands
    def home_to_vial1(self):
        return self.send_command("HOME_TO_VIAL1", response_timeout_s=120.0)

    def home_to_vial2(self):
        return self.send_command("HOME_TO_VIAL2", response_timeout_s=120.0)

    def home_to_vial3(self):
        return self.send_command("HOME_TO_VIAL3", response_timeout_s=120.0)

    def home_to_vial4(self):
        return self.send_command("HOME_TO_VIAL4", response_timeout_s=120.0)

    def home_to_vial5(self):
        return self.send_command("HOME_TO_VIAL5", response_timeout_s=120.0)

    #vial1 to... movement commands
    def vial1_to_home(self):
        return self.home_position()

    def vial1_to_vial2(self):
        return self.send_command("VIAL1_TO_VIAL2", response_timeout_s=120.0)

    def vial1_to_vial3(self):
        return self.send_command("VIAL1_TO_VIAL3", response_timeout_s=120.0)

    def vial1_to_vial4(self):
        return self.send_command("VIAL1_TO_VIAL4", response_timeout_s=120.0)

    def vial1_to_vial5(self):
        return self.send_command("VIAL1_TO_VIAL5", response_timeout_s=120.0)

    #vial2 to... movement commands
    def vial2_to_home(self):
        return self.home_position()

    def vial2_to_vial1(self):
        return self.send_command("VIAL2_TO_VIAL1", response_timeout_s=120.0)

    def vial2_to_vial3(self):
        return self.send_command("VIAL2_TO_VIAL3", response_timeout_s=120.0)

    def vial2_to_vial4(self):
        return self.send_command("VIAL2_TO_VIAL4", response_timeout_s=120.0)

    def vial2_to_vial5(self):
        return self.send_command("VIAL2_TO_VIAL5", response_timeout_s=120.0)

    #vial3 to... movement commands
    def vial3_to_home(self):
        return self.home_position()

    def vial3_to_vial1(self):
        return self.send_command("VIAL3_TO_VIAL1", response_timeout_s=120.0)

    def vial3_to_vial2(self):
        return self.send_command("VIAL3_TO_VIAL2", response_timeout_s=120.0)

    def vial3_to_vial4(self):
        return self.send_command("VIAL3_TO_VIAL4", response_timeout_s=120.0)

    def vial3_to_vial5(self):
        return self.send_command("VIAL3_TO_VIAL5", response_timeout_s=120.0)

    #vial4 to... movement commands
    def vial4_to_home(self):
        return self.home_position()

    def vial4_to_vial1(self):
        return self.send_command("VIAL4_TO_VIAL1", response_timeout_s=120.0)

    def vial4_to_vial2(self):
        return self.send_command("VIAL4_TO_VIAL2", response_timeout_s=120.0)

    def vial4_to_vial3(self):
        return self.send_command("VIAL4_TO_VIAL3", response_timeout_s=120.0)

    def vial4_to_vial5(self):
        return self.send_command("VIAL4_TO_VIAL5", response_timeout_s=120.0)

    #vial5 to... movement commands
    def vial5_to_home(self):
        return self.home_position()

    def vial5_to_vial1(self):
        return self.send_command("VIAL5_TO_VIAL1", response_timeout_s=120.0)

    def vial5_to_vial2(self):
        return self.send_command("VIAL5_TO_VIAL2", response_timeout_s=120.0)

    def vial5_to_vial3(self):
        return self.send_command("VIAL5_TO_VIAL3", response_timeout_s=120.0)

    def vial5_to_vial4(self):
        return self.send_command("VIAL5_TO_VIAL4", response_timeout_s=120.0)

    def set_mixing(self, state, speed_rpm=1000, direction_clockwise=True):
        raise NotImplementedError("Firmware does not implement MIXING command.")

    def set_manual_mode(self, enabled):
        raise NotImplementedError("Firmware does not implement MANUAL_MODE command.")

    def move_right(self, steps=1):
        return self.send_command(f"MOVE_RIGHT {steps}", response_timeout_s=20.0)

    def move_left(self, steps=1):
        return self.send_command(f"MOVE_LEFT {steps}", response_timeout_s=20.0)

    def move_up(self, steps=1):
        return self.send_command(f"MOVE_UP {steps}", response_timeout_s=20.0)

    def move_down(self, steps=1):
        return self.send_command(f"MOVE_DOWN {steps}", response_timeout_s=20.0)

    def stop_all(self):
        raise NotImplementedError("Firmware does not implement STOP_ALL command.")


if __name__ == "__main__":
    # Example of using environment variables in other code.
    # The project .env file should contain:
    #   MOTOR_PORT=COM6
    #   MOTOR_BAUD=115200
    logging.basicConfig(level=logging.INFO, format="[%(module)s] %(message)s", stream=sys.stdout)
    with MotorsCom() as motor:
        motor.home_to_vial1()
        
       

    # Example usage in another Python file:
    # from backEnd.ESP32.Com.esp32com import MotorsCom
    # with MotorsCom() as motor:
    #     motor.home_position()
    #     motor.move_up(20)



