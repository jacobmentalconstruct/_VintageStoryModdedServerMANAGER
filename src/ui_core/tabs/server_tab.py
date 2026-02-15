# src/ui_core/tabs/server_tab.py
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from dataclasses import replace
from pathlib import Path

from src.orchestration_core.errors import ValidationError, NotRunningError
from src.server_manager_core.models import AppState
from .base_tab import BaseTab


class ServerTab(BaseTab):
    TAB_ID = "server"
    TAB_TITLE = "Server"
    ORDER = 10

    def __init__(self, controller, log_fn):
        super().__init__(controller, log_fn)

        # Tk variables (initialized in build())
        self.var_exe = tk.StringVar()
        self.var_data = tk.StringVar()
        self.var_port = tk.StringVar()

        self.var_running = tk.StringVar(value="Unknown")
        self.var_listening = tk.StringVar(value="Unknown")

        self.var_cmd = tk.StringVar()

        # Widgets we update later
        self._btn_start = None
        self._btn_stop = None
        self._btn_force = None
        self._btn_kill = None
        self._btn_send = None

    # -------------------------
    # Build
    # -------------------------

    def build(self, parent):
        self.frame = ttk.Frame(parent)

        outer = ttk.Frame(self.frame)
        outer.pack(fill="both", expand=True, padx=12, pady=12)
        outer.columnconfigure(0, weight=1)

        # --- Paths / settings ---
        paths = ttk.LabelFrame(outer, text="Server Settings")
        paths.grid(row=0, column=0, sticky="nsew")
        paths.columnconfigure(1, weight=1)

        # Executable
        ttk.Label(paths, text="Server EXE:").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        exe_entry = ttk.Entry(paths, textvariable=self.var_exe)
        exe_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=(8, 4))
        ttk.Button(paths, text="Browse…", command=self._browse_exe).grid(row=0, column=2, sticky="e", padx=8, pady=(8, 4))

        # Data path
        ttk.Label(paths, text="Data Path:").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        data_entry = ttk.Entry(paths, textvariable=self.var_data)
        data_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(paths, text="Browse…", command=self._browse_data_dir).grid(row=1, column=2, sticky="e", padx=8, pady=4)

        # Port
        ttk.Label(paths, text="Port:").grid(row=2, column=0, sticky="w", padx=8, pady=(4, 8))
        port_entry = ttk.Entry(paths, textvariable=self.var_port, width=12)
        port_entry.grid(row=2, column=1, sticky="w", padx=8, pady=(4, 8))
        ttk.Button(paths, text="Apply to Config", command=self._apply_to_state).grid(row=2, column=2, sticky="e", padx=8, pady=(4, 8))

        # --- Status + Actions ---
        status = ttk.LabelFrame(outer, text="Status & Controls")
        status.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        status.columnconfigure(0, weight=1)
        status.columnconfigure(1, weight=1)

        # Status display
        left = ttk.Frame(status)
        left.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        left.columnconfigure(1, weight=1)

        ttk.Label(left, text="Server Running:").grid(row=0, column=0, sticky="w")
        ttk.Label(left, textvariable=self.var_running).grid(row=0, column=1, sticky="w", padx=(8, 0))

        ttk.Label(left, text="Port Listening (localhost):").grid(row=1, column=0, sticky="w")
        ttk.Label(left, textvariable=self.var_listening).grid(row=1, column=1, sticky="w", padx=(8, 0))

        # Buttons
        right = ttk.Frame(status)
        right.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)

        self._btn_start = ttk.Button(right, text="Start Server", command=self._start_server)
        self._btn_stop = ttk.Button(right, text="Stop (Graceful)", command=self._stop_graceful)
        self._btn_force = ttk.Button(right, text="Stop (Force)", command=self._stop_force)
        self._btn_kill = ttk.Button(right, text="Kill", command=self._kill)

        self._btn_start.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self._btn_stop.grid(row=1, column=0, sticky="ew", pady=6)
        self._btn_force.grid(row=2, column=0, sticky="ew", pady=6)
        self._btn_kill.grid(row=3, column=0, sticky="ew", pady=(6, 0))

        for i in range(4):
            right.rowconfigure(i, weight=0)
        right.columnconfigure(0, weight=1)

        # --- Command line ---
        cmd = ttk.LabelFrame(outer, text="Console Command")
        cmd.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        cmd.columnconfigure(0, weight=1)

        cmd_row = ttk.Frame(cmd)
        cmd_row.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        cmd_row.columnconfigure(0, weight=1)

        cmd_entry = ttk.Entry(cmd_row, textvariable=self.var_cmd)
        cmd_entry.grid(row=0, column=0, sticky="ew")
        self._btn_send = ttk.Button(cmd_row, text="Send", command=self._send_command)
        self._btn_send.grid(row=0, column=1, padx=(8, 0))

        # Bind Enter to send
        cmd_entry.bind("<Return>", lambda _e: self._send_command())

        # Initial fill from state
        self._load_from_state()

        return self.frame

    # -------------------------
    # Tab lifecycle
    # -------------------------

    def on_show(self) -> None:
        # Ensure UI reflects current state when switching to this tab
        self._load_from_state()
        self._refresh_status()

    def refresh(self) -> None:
        # Called by UiApp tick for visible tab
        self._refresh_status()

    # -------------------------
    # State sync
    # -------------------------

    def _load_from_state(self) -> None:
        state = self.controller.get_state()
        self.var_exe.set(state.server_exe_path or "")
        self.var_data.set(state.data_path or "")
        self.var_port.set(str(state.port))

    def _apply_to_state(self) -> None:
        """
        Commit current UI fields into state (does not automatically save to disk).
        """
        def mut(s: AppState) -> AppState:
            exe = self.var_exe.get().strip()
            data = self.var_data.get().strip()
            port_txt = self.var_port.get().strip()

            # Keep port conservative: if invalid, keep old value but warn.
            try:
                port_val = int(port_txt)
            except Exception:
                port_val = s.port

            return replace(
                s,
                server_exe_path=exe,
                data_path=data,
                port=port_val,
            )

        new_state = self.controller.update_state(mut)
        self.log("[OK] Applied UI fields to state.")
        # Helpful: if port parse failed, correct the entry to current stored value
        self.var_port.set(str(new_state.port))

    # -------------------------
    # Browse helpers
    # -------------------------

    def _browse_exe(self) -> None:
        initial = self.var_exe.get().strip()
        init_dir = str(Path(initial).parent) if initial else str(Path.cwd())
        path = filedialog.askopenfilename(
            title="Select Vintage Story Server Executable",
            initialdir=init_dir,
            filetypes=[("Executable", "*.exe"), ("All Files", "*.*")]
        )
        if path:
            self.var_exe.set(path)
            self._apply_to_state()

    def _browse_data_dir(self) -> None:
        initial = self.var_data.get().strip()
        init_dir = initial if initial else str(Path.cwd())
        path = filedialog.askdirectory(
            title="Select Vintage Story Data Folder",
            initialdir=init_dir,
        )
        if path:
            self.var_data.set(path)
            self._apply_to_state()

    # -------------------------
    # Actions
    # -------------------------

    def _start_server(self) -> None:
        try:
            self._apply_to_state()
            self.controller.start_server()
            self.log("[OK] Start requested.")
        except ValidationError as e:
            self._show_error("Cannot start server", str(e))
        except Exception as e:
            self._show_error("Start failed", str(e))
        finally:
            self._refresh_status()

    def _stop_graceful(self) -> None:
        try:
            self.controller.stop_server_graceful()
            self.log("[OK] Graceful stop requested.")
        except NotRunningError as e:
            self._show_info("Server not running", str(e))
        except Exception as e:
            self._show_error("Stop failed", str(e))
        finally:
            self._refresh_status()

    def _stop_force(self) -> None:
        try:
            self.controller.stop_server_force()
            self.log("[WARN] Force stop requested.")
        except NotRunningError as e:
            self._show_info("Server not running", str(e))
        except Exception as e:
            self._show_error("Force stop failed", str(e))
        finally:
            self._refresh_status()

    def _kill(self) -> None:
        if not messagebox.askyesno("Kill Server", "Kill the server process immediately?"):
            return
        try:
            self.controller.kill_server()
            self.log("[WARN] Kill requested.")
        except NotRunningError as e:
            self._show_info("Server not running", str(e))
        except Exception as e:
            self._show_error("Kill failed", str(e))
        finally:
            self._refresh_status()

    def _send_command(self) -> None:
        cmd = self.var_cmd.get().strip()
        if not cmd:
            return
        try:
            self.controller.send_server_command(cmd)
            self.log(f"[CMD] {cmd}")
            self.var_cmd.set("")
        except NotRunningError as e:
            self._show_info("Server not running", str(e))
        except Exception as e:
            self._show_error("Send command failed", str(e))

    # -------------------------
    # Status
    # -------------------------

    def _refresh_status(self) -> None:
        running = self.controller.is_server_running()
        self.var_running.set("Yes" if running else "No")

        # Port listening check (localhost)
        try:
            listening = self.controller.is_port_listening_localhost()
            self.var_listening.set("Yes" if listening else "No")
        except Exception:
            self.var_listening.set("Unknown")

        # Button states
        if self._btn_start and self._btn_stop and self._btn_force and self._btn_kill and self._btn_send:
            if running:
                self._btn_start.configure(state="disabled")
                self._btn_stop.configure(state="normal")
                self._btn_force.configure(state="normal")
                self._btn_kill.configure(state="normal")
                self._btn_send.configure(state="normal")
            else:
                self._btn_start.configure(state="normal")
                self._btn_stop.configure(state="disabled")
                self._btn_force.configure(state="disabled")
                self._btn_kill.configure(state="disabled")
                self._btn_send.configure(state="disabled")

    # -------------------------
    # UI messaging
    # -------------------------

    def _show_error(self, title: str, msg: str) -> None:
        self.log(f"[ERROR] {title}: {msg}")
        messagebox.showerror(title, msg)

    def _show_info(self, title: str, msg: str) -> None:
        self.log(f"[INFO] {title}: {msg}")
        messagebox.showinfo(title, msg)

