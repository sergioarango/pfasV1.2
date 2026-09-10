"""Detect ESP32 serial port and write MOTOR_PORT/MOTOR_BAUD to project env file."""

from __future__ import annotations

from pathlib import Path

from serial.tools import list_ports


def find_candidates():
    candidates = []
    for p in list_ports.comports():
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        if any(tag in desc for tag in ("esp32", "cp210", "ch340", "usb serial")) or "10c4" in hwid:
            candidates.append(p.device)
    return sorted(set(candidates))


def update_env(env_path: Path, port: str, baud: int = 115200) -> None:
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    has_port = False
    has_baud = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("MOTOR_PORT="):
            new_lines.append(f"MOTOR_PORT={port}")
            has_port = True
        elif stripped.startswith("MOTOR_BAUD="):
            new_lines.append(f"MOTOR_BAUD={baud}")
            has_baud = True
        else:
            new_lines.append(line)

    if not has_port:
        new_lines.append(f"MOTOR_PORT={port}")
    if not has_baud:
        new_lines.append(f"MOTOR_BAUD={baud}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(new_lines).strip() + "\n", encoding="utf-8")


def main() -> int:
    candidates = find_candidates()
    if not candidates:
        print("No ESP32-like serial device found.")
        return 1

    if len(candidates) > 1:
        print("Multiple possible ESP32 ports found:")
        for idx, port in enumerate(candidates, start=1):
            print(f"  {idx}. {port}")
        print("Using first candidate. Edit env/.env if needed.")

    selected = candidates[0]
    project_root = Path(__file__).resolve().parents[3]
    env_path = project_root / "env" / ".env"

    update_env(env_path, selected, baud=115200)
    print(f"Configured MOTOR_PORT={selected} in {env_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
