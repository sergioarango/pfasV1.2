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
import threading
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

    def __init__(self, device_port=None, baud_rate=None, timeout_s=1.0, verbose=False):
        self.DEVICE_PORT = device_port
        self.BAUD_RATE = baud_rate
        self.TIMEOUT_S = timeout_s
        self.VERBOSE = verbose
        self.LOG = logging.getLogger(__name__)
        self._ser = None
        self._command_lock = threading.Lock()

    def _debug(self, message):
        """Print debug output only when verbose mode is enabled."""
        if self.VERBOSE:
            print(message)

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
        self._debug(f"DEBUG: opening serial port {port!r} at {baudrate}")

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

    def _drain_input(self):
        """Drain stale serial lines before sending a new command."""
        if not self._ser or not self._ser.is_open:
            return

        drained = 0
        start = time.time()
        while (time.time() - start) < 0.2:
            waiting = self._ser.in_waiting
            if waiting <= 0:
                break
            line = self._readline()
            if not line:
                continue
            drained += 1
            self.LOG.debug("RX (drain) <- %s", line)

        if drained:
            self._debug(f"DEBUG: drained {drained} stale serial line(s) before TX")

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
        with self._command_lock:
            self.connect()
            self._drain_input()

            wire = f"{command}\n".encode("utf-8")
            self._debug(f"DEBUG: sending command -> {command!r} bytes={wire!r}")
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
            is_rotator_command = (
                cmd_upper.startswith("ROTATE_CLOCK")
                or cmd_upper.startswith("ROTATE_UCLOCK")
                or cmd_upper == "STOP_ROTATOR"
            )
            is_emergency_command = cmd_upper in (
                "EMERGENCY_STOP",
                "ESTOP",
                "STOP_ALL",
                "CLEAR_EMERGENCY",
                "RESET_ESTOP",
            )
            move_complete_count = 0

            # ACK means command accepted. For multi-stage moves, wait for both MOVE_COMPLETE events.
            if is_multi_stage_vial_move:
                completion_tokens = ("DONE", "DEVICE IS NOW IN VIAL", "ERR", "ERROR")
            elif is_rotator_command:
                # Rotator commands never emit DONE/MOVE_COMPLETE; their final reply is the detailed ACK line.
                completion_tokens = ("ACK CLOCK", "ACK COUNTERCLOCK", "ACK STOP ROTATOR", "ERR", "ERROR")
            elif is_emergency_command:
                # Emergency stop/clear never emit DONE/MOVE_COMPLETE; their reply is a single ACK line.
                completion_tokens = ("ACK EMERGENCY_STOP", "ACK CLEAR_EMERGENCY", "ERR", "ERROR")
            else:
                completion_tokens = ("DONE", "MOVE_COMPLETE", "ERR", "ERROR")

            while time.time() < end_at:
                line = self._readline()
                if not line:
                    continue

                parsed = self._parse_line(line)
                responses.append(parsed)
                self._debug(f"DEBUG: received <- {parsed['raw']!r}")
                self.LOG.debug("RX <- %s", parsed["raw"])

                raw_upper = parsed["raw"].upper()
                if "MOVE_COMPLETE" in raw_upper:
                    move_complete_count += 1

                if is_multi_stage_vial_move and move_complete_count >= 2:
                    break

                if any(token in raw_upper for token in completion_tokens):
                    break

            if wait_response and not responses:
                self._debug(f"DEBUG: no response received for command {command!r} within {response_timeout_s}s")

            return responses

    @staticmethod
    def _has_error(responses):
        for item in responses:
            raw = str(item.get("raw", "")).upper()
            if "ERR" in raw or "ERROR" in raw:
                return True
        return False

    def run_sequence(self, commands, settle_delay_s=0.15):
        """Run commands in order, waiting for each routine to complete before the next."""
        all_responses = []
        for item in commands:
            if isinstance(item, tuple):
                cmd, timeout_s = item
            else:
                cmd, timeout_s = item, 120.0

            responses = self.send_command(cmd, wait_response=True, response_timeout_s=float(timeout_s))
            all_responses.append({"command": cmd, "responses": responses})
            time.sleep(settle_delay_s)

        return all_responses

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
        if not state:
            return self.stop_rotator()

        if direction_clockwise:
            return self.rotate_clock(speed_rpm)
        return self.rotate_uclock(speed_rpm)

    def set_manual_mode(self, enabled):
        raise NotImplementedError("Firmware does not implement MANUAL_MODE command.")

    def rotate_clock(self, rpm):
        rpm_value = float(rpm)
        return self.send_command(f"ROTATE_CLOCK {rpm_value}", response_timeout_s=8.0)

    def rotate_uclock(self, rpm):
        rpm_value = float(rpm)
        return self.send_command(f"ROTATE_UCLOCK {rpm_value}", response_timeout_s=8.0)

    def stop_rotator(self):
        return self.send_command("STOP_ROTATOR", response_timeout_s=8.0)

    def move_right(self, steps=1):
        return self.send_command(f"MOVE_RIGHT {steps}", response_timeout_s=20.0)

    def move_left(self, steps=1):
        return self.send_command(f"MOVE_LEFT {steps}", response_timeout_s=20.0)

    def move_up(self, steps=1):
        return self.send_command(f"MOVE_UP {steps}", response_timeout_s=20.0)

    def move_down(self, steps=1):
        return self.send_command(f"MOVE_DOWN {steps}", response_timeout_s=20.0)

    def stop_all(self):
        return self.send_command("EMERGENCY_STOP", response_timeout_s=8.0)

    def clear_emergency(self):
        return self.send_command("CLEAR_EMERGENCY", response_timeout_s=8.0)


class FastMotorInterface:
    """Fast high-level interface with smart vial routing and safe sequencing."""

    def __init__(self, device_port=None, baud_rate=None, timeout_s=1.0, verbose=False):
        self._motor = MotorsCom(
            device_port=device_port,
            baud_rate=baud_rate,
            timeout_s=timeout_s,
            verbose=verbose,
        )
        self._position = "UNKNOWN"

    def __enter__(self):
        self._motor.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._motor.disconnect()

    def connect(self):
        self._motor.connect()

    def disconnect(self):
        self._motor.disconnect()

    @property
    def position(self):
        return self._position

    def execute(self, command, timeout_s=120.0):
        responses = self._motor.send_command(command, wait_response=True, response_timeout_s=timeout_s)
        if not self._motor._has_error(responses):
            self._update_position_from_command(command)
        return responses

    def _update_position_from_command(self, command):
        cmd = command.strip().upper()
        if cmd in ("HOME", "HOME_POSITION"):
            self._position = "HOME"
            return

        if cmd.startswith("HOME_TO_VIAL"):
            self._position = cmd.replace("HOME_TO_", "")
            return

        if cmd.startswith("VIAL") and "_TO_VIAL" in cmd:
            self._position = cmd.split("_TO_")[1]
            return

        if cmd.startswith(("MOVE_", "HOME_Z", "HOME_X", "HOME_POSITION_Z", "HOME_POSITION_X")):
            self._position = "UNKNOWN"

    def home(self):
        return self.execute("HOME_POSITION", timeout_s=60.0)

    def rotate_clock(self, rpm):
        return self._motor.rotate_clock(rpm)

    def rotate_uclock(self, rpm):
        return self._motor.rotate_uclock(rpm)

    def stop_rotator(self):
        return self._motor.stop_rotator()

    def emergency_stop(self):
        return self._motor.stop_all()

    def clear_emergency(self):
        return self._motor.clear_emergency()

    def go_to_vial(self, vial_number):
        if vial_number not in (1, 2, 3, 4, 5):
            raise ValueError("vial_number must be 1..5")

        target = f"VIAL{vial_number}"
        if self._position == target:
            return []

        if self._position.startswith("VIAL"):
            command = f"{self._position}_TO_{target}"
        else:
            command = f"HOME_TO_{target}"
        return self.execute(command, timeout_s=120.0)

    def home_to_vial1(self):
        return self.go_to_vial(1)

    def home_to_vial2(self):
        return self.go_to_vial(2)

    def home_to_vial3(self):
        return self.go_to_vial(3)

    def home_to_vial4(self):
        return self.go_to_vial(4)

    def home_to_vial5(self):
        return self.go_to_vial(5)

    def quick_route(self, vial_numbers):
        results = []
        for vial in vial_numbers:
            responses = self.go_to_vial(int(vial))
            results.append({"target": f"VIAL{int(vial)}", "responses": responses})
        return results


# if __name__ == "__main__":
#     # Example of using environment variables in other code.
#     # The project .env file should contain:
#     #   MOTOR_PORT=COM6
#     #   MOTOR_BAUD=115200
#     logging.basicConfig(level=logging.INFO, format="[%(module)s] %(message)s", stream=sys.stdout)
#     with FastMotorInterface(verbose=True) as machine:
#         machine.home()
#         route = machine.quick_route([1, 2, 4, 3])
#         print("DEBUG: fast route results:")
#         for result in route:
#             print(result["target"])
#             for line in result["responses"]:
#                 print("  ", line)
        
       

    # Example usage in another Python file:
    # from backEnd.ESP32.Com.esp32com import MotorsCom
    # with MotorsCom() as motor:
    #     motor.home_position()
    #     motor.move_up(20)



