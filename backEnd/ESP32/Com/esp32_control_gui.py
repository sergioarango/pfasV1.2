"""Tkinter control panel for ESP32 motor firmware.

Button-based interface to run homing, vial routines, and manual moves.
Uses FastMotorInterface from esp32com.py and keeps a persistent serial connection.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from esp32com import FastMotorInterface


class MotorControlApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PFAS ESP32 Motor Control")
        self.root.geometry("1180x700")

        self.machine = FastMotorInterface(verbose=False)
        self.connected = False

        self.task_queue: queue.Queue[tuple[str, Callable[[], object]]] = queue.Queue()
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

        self.status_var = tk.StringVar(value="Disconnected")
        self.position_var = tk.StringVar(value="UNKNOWN")
        self.step_var = tk.StringVar(value="20")
        self.rpm_var = tk.StringVar(value="600")
        self.rotator_dir_var = tk.StringVar(value="CLOCK")
        self.route_var = tk.StringVar(value="1,2,4,3")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(main)
        header.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(header, text="Connection:", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        ttk.Label(header, textvariable=self.status_var, foreground="#0B5ED7").pack(side=tk.LEFT, padx=(6, 18))
        ttk.Label(header, text="Position:", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        ttk.Label(header, textvariable=self.position_var, foreground="#198754").pack(side=tk.LEFT, padx=(6, 0))

        actions = ttk.Frame(main)
        actions.pack(fill=tk.BOTH, expand=False)

        conn_card = ttk.LabelFrame(actions, text="Connection")
        conn_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        ttk.Button(conn_card, text="Connect", command=self.connect).pack(fill=tk.X, padx=8, pady=(8, 4))
        ttk.Button(conn_card, text="Disconnect", command=self.disconnect).pack(fill=tk.X, padx=8, pady=(0, 8))

        home_card = ttk.LabelFrame(actions, text="Home / Vials")
        home_card.grid(row=0, column=1, sticky="nsew", padx=(0, 8), pady=(0, 8))
        ttk.Button(home_card, text="HOME_POSITION", command=lambda: self.enqueue("Home", self.machine.home)).pack(fill=tk.X, padx=8, pady=(8, 6))

        vial_grid = ttk.Frame(home_card)
        vial_grid.pack(fill=tk.BOTH, padx=8, pady=(0, 8))
        for idx in range(1, 6):
            ttk.Button(
                vial_grid,
                text=f"Go Vial {idx}",
                command=lambda v=idx: self.enqueue(f"Go to vial {v}", lambda: self.machine.go_to_vial(v)),
            ).grid(row=(idx - 1) // 3, column=(idx - 1) % 3, padx=4, pady=4, sticky="ew")
        for col in range(3):
            vial_grid.columnconfigure(col, weight=1)

        manual_card = ttk.LabelFrame(actions, text="Manual Move")
        manual_card.grid(row=0, column=2, sticky="nsew", pady=(0, 8))

        step_row = ttk.Frame(manual_card)
        step_row.pack(fill=tk.X, padx=8, pady=(8, 6))
        ttk.Label(step_row, text="Steps:").pack(side=tk.LEFT)
        ttk.Entry(step_row, textvariable=self.step_var, width=10).pack(side=tk.LEFT, padx=(6, 0))

        manual_grid = ttk.Frame(manual_card)
        manual_grid.pack(fill=tk.BOTH, padx=8, pady=(0, 8))
        ttk.Button(manual_grid, text="Up", command=lambda: self._move("up")).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(manual_grid, text="Left", command=lambda: self._move("left")).grid(row=1, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(manual_grid, text="Right", command=lambda: self._move("right")).grid(row=1, column=2, padx=4, pady=4, sticky="ew")
        ttk.Button(manual_grid, text="Down", command=lambda: self._move("down")).grid(row=2, column=1, padx=4, pady=4, sticky="ew")
        for row in range(3):
            manual_grid.rowconfigure(row, weight=1)
        for col in range(3):
            manual_grid.columnconfigure(col, weight=1)

        rotator_card = ttk.LabelFrame(actions, text="Rotator / Safety")
        rotator_card.grid(row=0, column=3, sticky="nsew", padx=(8, 0), pady=(0, 8))

        rpm_row = ttk.Frame(rotator_card)
        rpm_row.pack(fill=tk.X, padx=8, pady=(8, 4))
        ttk.Label(rpm_row, text="RPM (500-800):").pack(side=tk.LEFT)
        ttk.Entry(rpm_row, textvariable=self.rpm_var, width=10).pack(side=tk.LEFT, padx=(8, 0))

        dir_row = ttk.Frame(rotator_card)
        dir_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(dir_row, text="Direction:").pack(side=tk.LEFT)
        ttk.Combobox(
            dir_row,
            textvariable=self.rotator_dir_var,
            values=("CLOCK", "UCLOCK"),
            width=10,
            state="readonly",
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(rotator_card, text="Start Rotator", command=self._start_rotator).pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Button(rotator_card, text="Stop Rotator", command=self._stop_rotator).pack(fill=tk.X, padx=8, pady=(0, 12))
        tk.Button(
            rotator_card,
            text="EMERGENCY STOP",
            command=self._emergency_stop,
            bg="#C62828",
            fg="white",
            activebackground="#B71C1C",
            activeforeground="white",
            relief=tk.RAISED,
            bd=2,
        ).pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Button(rotator_card, text="Clear Emergency", command=self._clear_emergency).pack(fill=tk.X, padx=8, pady=(0, 8))

        route_card = ttk.LabelFrame(main, text="Fast Route")
        route_card.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(route_card, text="Vials (comma-separated):").pack(side=tk.LEFT, padx=(8, 6), pady=8)
        ttk.Entry(route_card, textvariable=self.route_var, width=28).pack(side=tk.LEFT, pady=8)
        ttk.Button(route_card, text="Run Route", command=self._run_route).pack(side=tk.LEFT, padx=8, pady=8)

        log_card = ttk.LabelFrame(main, text="Response Log")
        log_card.pack(fill=tk.BOTH, expand=True)
        self.log = ScrolledText(log_card, height=18, wrap=tk.WORD, font=("Consolas", 10))
        self.log.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        for col in range(4):
            actions.columnconfigure(col, weight=1)

    def _append_log(self, text: str):
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)

    def connect(self):
        self.enqueue("Connect", self._connect_task)

    def _connect_task(self):
        self.machine.connect()
        self.connected = True
        self.status_var.set("Connected")
        self.position_var.set(self.machine.position)

    def disconnect(self):
        self.enqueue("Disconnect", self._disconnect_task)

    def _disconnect_task(self):
        self.machine.disconnect()
        self.connected = False
        self.status_var.set("Disconnected")

    def _move(self, direction: str):
        try:
            steps = int(self.step_var.get().strip())
            if steps <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Steps", "Steps must be a positive integer.")
            return

        def task():
            if direction == "up":
                return self.machine._motor.move_up(steps)
            if direction == "down":
                return self.machine._motor.move_down(steps)
            if direction == "left":
                return self.machine._motor.move_left(steps)
            return self.machine._motor.move_right(steps)

        self.enqueue(f"Move {direction.upper()} {steps}", task)

    def _run_route(self):
        raw = self.route_var.get().strip()
        if not raw:
            messagebox.showerror("Invalid Route", "Enter at least one vial number.")
            return

        try:
            vial_list = [int(part.strip()) for part in raw.split(",") if part.strip()]
        except ValueError:
            messagebox.showerror("Invalid Route", "Use comma-separated numbers, for example: 1,2,4,3")
            return

        for vial in vial_list:
            if vial not in (1, 2, 3, 4, 5):
                messagebox.showerror("Invalid Route", "Vial numbers must be between 1 and 5.")
                return

        def task():
            return self.machine.quick_route(vial_list)

        self.enqueue(f"Route {vial_list}", task)

    def _start_rotator(self):
        try:
            rpm = float(self.rpm_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid RPM", "RPM must be a number between 500 and 800.")
            return

        if rpm < 500 or rpm > 800:
            messagebox.showerror("Invalid RPM", "RPM must be between 500 and 800.")
            return

        direction = self.rotator_dir_var.get().strip().upper()

        def task():
            if direction == "UCLOCK":
                return self.machine.rotate_uclock(rpm)
            return self.machine.rotate_clock(rpm)

        self.enqueue(f"Rotator {direction} {rpm}", task)

    def _stop_rotator(self):
        self.enqueue("Stop Rotator", self.machine.stop_rotator)

    def _emergency_stop(self):
        self.enqueue("EMERGENCY_STOP", self.machine.emergency_stop)

    def _clear_emergency(self):
        self.enqueue("CLEAR_EMERGENCY", self.machine.clear_emergency)

    def enqueue(self, label: str, func):
        self.task_queue.put((label, func))

    def _worker_loop(self):
        while True:
            label, func = self.task_queue.get()
            self.root.after(0, self._append_log, f"[TX] {label}")
            try:
                result = func()
                self.root.after(0, self._handle_result, label, result)
            except Exception as exc:
                self.root.after(0, self._append_log, f"[ERR] {label}: {exc}")
            finally:
                self.task_queue.task_done()

    def _handle_result(self, label: str, result):
        if isinstance(result, list):
            if result and isinstance(result[0], dict) and "target" in result[0]:
                for item in result:
                    self._append_log(f"[DONE] {label} -> {item['target']}")
                    for line in item["responses"]:
                        self._append_log(f"  [RX] {line.get('raw', '')}")
            else:
                self._append_log(f"[DONE] {label}")
                for line in result:
                    if isinstance(line, dict):
                        self._append_log(f"  [RX] {line.get('raw', '')}")
                    else:
                        self._append_log(f"  [RX] {line}")
        else:
            self._append_log(f"[DONE] {label}: {result}")

        self.position_var.set(self.machine.position)

    def _on_close(self):
        try:
            self.machine.disconnect()
        finally:
            self.root.destroy()


def main():
    root = tk.Tk()
    app = MotorControlApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
