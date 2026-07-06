# src/ui_core/tabs/server_tab.py
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from dataclasses import replace
from pathlib import Path
from time import perf_counter

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
        self.var_start_hint = tk.StringVar(value="")

        self.var_selected_name = tk.StringVar(value="None")
        self.var_selected_id = tk.StringVar(value="")
        self.var_selected_map = tk.StringVar(value="Unknown")
        self.var_selected_path = tk.StringVar(value="")
        self.var_selected_world = tk.StringVar(value="")
        self.var_selected_mods = tk.StringVar(value="")

        self.var_cmd = tk.StringVar()

        # Widgets we update later
        self._tree_servers = None
        self._server_rows = {}
        self._btn_start = None
        self._btn_stop = None
        self._btn_force = None
        self._btn_kill = None
        self._btn_send = None
        self._generation_locked_buttons = []
        self._last_port_check_at = 0.0
        self._last_port_listening = None
        self._port_check_interval_s = 1.5

    # -------------------------
    # Build
    # -------------------------

    def build(self, parent):
        self.frame = ttk.Frame(parent)

        outer = ttk.Frame(self.frame)
        outer.pack(fill="both", expand=True, padx=12, pady=12)
        outer.columnconfigure(0, weight=1)
        # Give the server list a guaranteed minimum height so it can't be
        # collapsed to nothing when the fixed panels below claim vertical space.
        outer.rowconfigure(0, weight=1, minsize=180)

        # --- Managed servers ---
        servers = ttk.LabelFrame(outer, text="Available Server Worlds")
        servers.grid(row=0, column=0, sticky="nsew")
        servers.columnconfigure(0, weight=1)
        servers.rowconfigure(0, weight=1)

        columns = ("name", "id", "map", "port", "path")
        self._tree_servers = ttk.Treeview(servers, columns=columns, show="headings", selectmode="browse", height=5)
        self._tree_servers.heading("name", text="Name")
        self._tree_servers.heading("id", text="ID")
        self._tree_servers.heading("map", text="Map")
        self._tree_servers.heading("port", text="Port")
        self._tree_servers.heading("path", text="Data Root")
        self._tree_servers.column("name", width=160, anchor="w")
        self._tree_servers.column("id", width=140, anchor="w")
        self._tree_servers.column("map", width=90, anchor="center")
        self._tree_servers.column("port", width=70, anchor="center")
        self._tree_servers.column("path", width=500, anchor="w")
        self._tree_servers.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        self._tree_servers.bind("<<TreeviewSelect>>", lambda _e: self._select_server_from_tree())
        self._tree_servers.bind("<Double-1>", lambda _e: self._select_server_from_tree())

        srv_scroll = ttk.Scrollbar(servers, orient="vertical", command=self._tree_servers.yview)
        self._tree_servers.configure(yscrollcommand=srv_scroll.set)
        srv_scroll.grid(row=0, column=1, sticky="ns", pady=8)

        srv_buttons = ttk.Frame(servers)
        srv_buttons.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        ttk.Button(srv_buttons, text="Refresh", command=self._refresh_server_list).pack(side="left")
        btn_select = ttk.Button(srv_buttons, text="Select", command=self._select_server_from_tree)
        btn_select.pack(side="left", padx=(8, 0))
        btn_register = ttk.Button(srv_buttons, text="Register Current Path", command=self._register_current_path)
        btn_register.pack(side="left", padx=(8, 0))
        btn_reset = ttk.Button(srv_buttons, text="Reset Map", command=self._reset_map)
        btn_reset.pack(side="right", padx=(8, 0))
        btn_delete_map = ttk.Button(srv_buttons, text="Delete Map", command=self._delete_map)
        btn_delete_map.pack(side="right", padx=(8, 0))
        btn_delete_server = ttk.Button(srv_buttons, text="Delete Server", command=self._delete_server)
        btn_delete_server.pack(side="right", padx=(8, 0))
        btn_wipe = ttk.Button(srv_buttons, text="Full Server Wipe", command=self._full_server_wipe)
        btn_wipe.pack(side="right", padx=(8, 0))
        self._generation_locked_buttons.extend([
            btn_select,
            btn_register,
            btn_reset,
            btn_delete_map,
            btn_delete_server,
            btn_wipe,
        ])

        # --- Selected server details ---
        details = ttk.LabelFrame(outer, text="Selected Server")
        details.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        details.columnconfigure(1, weight=1)
        details.columnconfigure(3, weight=1)

        ttk.Label(details, text="Name:").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 3))
        ttk.Label(details, textvariable=self.var_selected_name).grid(row=0, column=1, sticky="w", padx=8, pady=(8, 3))
        ttk.Label(details, text="ID:").grid(row=0, column=2, sticky="w", padx=8, pady=(8, 3))
        ttk.Label(details, textvariable=self.var_selected_id).grid(row=0, column=3, sticky="w", padx=8, pady=(8, 3))

        ttk.Label(details, text="Map:").grid(row=1, column=0, sticky="w", padx=8, pady=3)
        ttk.Label(details, textvariable=self.var_selected_map).grid(row=1, column=1, sticky="w", padx=8, pady=3)
        ttk.Label(details, text="World:").grid(row=1, column=2, sticky="w", padx=8, pady=3)
        ttk.Label(details, textvariable=self.var_selected_world).grid(row=1, column=3, sticky="w", padx=8, pady=3)

        ttk.Label(details, text="Mods:").grid(row=2, column=0, sticky="w", padx=8, pady=3)
        ttk.Label(details, textvariable=self.var_selected_mods).grid(row=2, column=1, columnspan=3, sticky="w", padx=8, pady=3)

        ttk.Label(details, text="Data Root:").grid(row=3, column=0, sticky="w", padx=8, pady=(3, 8))
        ttk.Label(details, textvariable=self.var_selected_path).grid(row=3, column=1, columnspan=3, sticky="ew", padx=8, pady=(3, 8))

        # --- Paths / settings ---
        paths = ttk.LabelFrame(outer, text="Server Settings")
        paths.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        paths.columnconfigure(1, weight=1)

        # Executable
        ttk.Label(paths, text="Server EXE:").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        exe_entry = ttk.Entry(paths, textvariable=self.var_exe)
        exe_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=(8, 4))
        btn_browse_exe = ttk.Button(paths, text="Browse…", command=self._browse_exe)
        btn_browse_exe.grid(row=0, column=2, sticky="e", padx=8, pady=(8, 4))

        # Data path
        ttk.Label(paths, text="Data Root:").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        data_entry = ttk.Entry(paths, textvariable=self.var_data)
        data_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        btn_browse_data = ttk.Button(paths, text="Browse…", command=self._browse_data_dir)
        btn_browse_data.grid(row=1, column=2, sticky="e", padx=8, pady=4)

        # Port
        ttk.Label(paths, text="Port:").grid(row=2, column=0, sticky="w", padx=8, pady=(4, 8))
        port_entry = ttk.Entry(paths, textvariable=self.var_port, width=12)
        port_entry.grid(row=2, column=1, sticky="w", padx=8, pady=(4, 8))
        btn_apply = ttk.Button(paths, text="Apply to Config", command=self._apply_to_state)
        btn_apply.grid(row=2, column=2, sticky="e", padx=8, pady=(4, 8))
        self._generation_locked_buttons.extend([btn_browse_exe, btn_browse_data, btn_apply])

        # --- Status + Actions ---
        status = ttk.LabelFrame(outer, text="Status & Controls")
        status.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
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

        ttk.Label(left, text="Start Readiness:").grid(row=2, column=0, sticky="nw", pady=(6, 0))
        ttk.Label(left, textvariable=self.var_start_hint, wraplength=520).grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(6, 0))

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
        cmd.grid(row=4, column=0, sticky="nsew", pady=(12, 0))
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
        self._refresh_server_list()
        self._load_from_state()

        return self.frame

    # -------------------------
    # Tab lifecycle
    # -------------------------

    def on_show(self) -> None:
        # Ensure UI reflects current state when switching to this tab
        self._refresh_server_list()
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
        self._refresh_selected_details()

    def _refresh_server_list(self) -> None:
        if not self._tree_servers:
            return

        for iid in self._tree_servers.get_children():
            self._tree_servers.delete(iid)
        self._server_rows.clear()

        state = self.controller.get_state()
        try:
            servers = self.controller.list_server_worlds()
        except Exception as e:
            self.log(f"[ERROR] Failed loading server worlds: {e}")
            return

        for info in servers:
            server_id = str(info.get("id", ""))
            if not server_id:
                continue
            iid = f"srv_{server_id}"
            self._tree_servers.insert(
                "",
                "end",
                iid=iid,
                values=(
                    info.get("name", server_id),
                    server_id,
                    info.get("map_status", "Unknown"),
                    info.get("port", state.port),
                    info.get("data_path", ""),
                ),
            )
            self._server_rows[iid] = server_id
            if server_id == state.selected_server_id:
                self._tree_servers.selection_set(iid)
                self._tree_servers.focus(iid)
                self._tree_servers.see(iid)
        self._refresh_selected_details()

    def _select_server_from_tree(self) -> None:
        self._select_server_from_tree_optional()

    def _select_server_from_tree_optional(self) -> bool:
        if not self._tree_servers:
            return False
        sel = self._tree_servers.selection()
        if not sel:
            return False

        server_id = self._server_rows.get(sel[0])
        if not server_id:
            return False

        try:
            self.controller.select_server_world(server_id)
            self._load_from_state()
            self._refresh_status()
            self._refresh_selected_details()
            return True
        except Exception as e:
            self._show_error("Select server failed", str(e))
            return False

    def _register_current_path(self) -> None:
        self._apply_to_state()
        try:
            info = self.controller.register_current_data_path_as_server()
            self._refresh_server_list()
            self._load_from_state()
            self._show_info("Server registered", f"Registered: {info.get('name')}")
        except ValidationError as e:
            self._show_error("Register server failed", str(e))
        except Exception as e:
            self._show_error("Register server failed", str(e))

    def _reset_map(self) -> None:
        if not self._require_selected_server_row():
            return
        if not self._confirm_phrase(
            "Reset Map",
            "RESET MAP",
            "This archives the selected server's Saves folder and creates an empty one. Player inventory and save-bound progress will not be preserved.",
        ):
            return

        try:
            archived = self.controller.reset_world_map_keep_players()
            self._refresh_server_list()
            self._refresh_selected_details()
        except ValidationError as e:
            self._show_error("Reset map failed", str(e))
            return
        except Exception as e:
            self._show_error("Reset map failed", str(e))
            return

        msg = (
            f"Previous map archived:\n{archived}\n\nMap status is now Reset."
            if archived
            else "No existing map was found. Empty Saves folder is ready."
        )
        self._show_info("Reset Map", msg)

    def _delete_map(self) -> None:
        if not self._require_selected_server_row():
            return
        if not self._confirm_phrase(
            "Delete Map",
            "DELETE MAP",
            "This archives the selected server's Saves folder and leaves it without an active map until generation runs again.",
        ):
            return

        try:
            archived = self.controller.delete_world_map()
            self._refresh_server_list()
            self._refresh_selected_details()
        except ValidationError as e:
            self._show_error("Delete map failed", str(e))
            return
        except Exception as e:
            self._show_error("Delete map failed", str(e))
            return

        msg = (
            f"Previous map archived:\n{archived}\n\nMap status is now Deleted."
            if archived
            else "No existing map was found."
        )
        self._show_info("Delete Map", msg)

    def _full_server_wipe(self) -> None:
        if not self._require_selected_server_row():
            return
        if not self._confirm_phrase(
            "Full Server Wipe",
            "WIPE SERVER",
            "This archives the selected server's entire data folder and recreates it empty.",
        ):
            return

        try:
            archived = self.controller.full_server_wipe()
            self._refresh_server_list()
            self._load_from_state()
            self._refresh_selected_details()
        except ValidationError as e:
            self._show_error("Full server wipe failed", str(e))
            return
        except Exception as e:
            self._show_error("Full server wipe failed", str(e))
            return

        msg = f"Previous server data archived:\n{archived}" if archived else "Server data folder was created empty."
        self._show_info("Full Server Wipe", msg)

    def _delete_server(self) -> None:
        if not self._require_selected_server_row():
            return
        if not self._confirm_phrase(
            "Delete Server",
            "DELETE SERVER",
            "This removes the selected server from the list. Local managed server folders are archived outside the live servers folder.",
        ):
            return

        try:
            archived = self.controller.delete_server_world()
            self._refresh_server_list()
            self._load_from_state()
            self._refresh_selected_details()
        except ValidationError as e:
            self._show_error("Delete server failed", str(e))
            return
        except Exception as e:
            self._show_error("Delete server failed", str(e))
            return

        msg = (
            f"Server removed from the list.\n\nArchived server data:\n{archived}"
            if archived
            else "Server removed from the list. No local managed folder was archived."
        )
        self._show_info("Delete Server", msg)

    def _require_selected_server_row(self) -> bool:
        if self._select_server_from_tree_optional():
            return True
        self._show_info("Select server", "Select a server world first.")
        return False

    def _confirm_phrase(self, title: str, phrase: str, detail: str) -> bool:
        answer = simpledialog.askstring(
            title,
            f"{detail}\n\nType {phrase} to continue:",
            parent=self.frame,
        )
        return (answer or "").strip().upper() == phrase

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
        self._refresh_status()

    def _refresh_selected_details(self) -> None:
        try:
            info = self.controller.selected_server_info()
        except Exception:
            info = None

        if not info:
            self.var_selected_name.set("None")
            self.var_selected_id.set("")
            self.var_selected_map.set("Unknown")
            self.var_selected_path.set("")
            self.var_selected_world.set("")
            self.var_selected_mods.set("")
            return

        settings = info.get("world_settings") or {}
        mods = info.get("active_mods") or []
        self.var_selected_name.set(str(info.get("name") or info.get("id") or ""))
        self.var_selected_id.set(str(info.get("id") or ""))
        self.var_selected_map.set(str(info.get("map_status") or "Unknown"))
        self.var_selected_path.set(str(info.get("data_path") or ""))
        self.var_selected_world.set(str(settings.get("WorldName") or info.get("name") or ""))
        self.var_selected_mods.set(f"{len(mods)} active" if mods else "None")

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
            readiness = self.controller.server_run_readiness()
            if not readiness.get("ready"):
                raise ValidationError("; ".join(readiness.get("reasons") or ["Server is not ready to start."]))
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
        generation = self.controller.map_generation_status()
        generating = bool(generation.get("in_progress"))
        self.var_running.set("Yes" if running else "No")
        self._refresh_selected_details()

        # Port listening check (localhost)
        now = perf_counter()
        if now - self._last_port_check_at >= self._port_check_interval_s:
            self._last_port_check_at = now
            try:
                self._last_port_listening = self.controller.is_port_listening_localhost()
            except Exception:
                self._last_port_listening = None

        if self._last_port_listening is None:
            self.var_listening.set("Unknown")
        else:
            self.var_listening.set("Yes" if self._last_port_listening else "No")

        # Button states
        for button in self._generation_locked_buttons:
            try:
                button.configure(state="disabled" if generating else "normal")
            except Exception:
                pass

        if self._btn_start and self._btn_stop and self._btn_force and self._btn_kill and self._btn_send:
            if running:
                self._btn_start.configure(state="disabled")
                self._btn_stop.configure(state="normal")
                self._btn_force.configure(state="normal")
                self._btn_kill.configure(state="normal")
                self._btn_send.configure(state="normal")
                if generating:
                    name = generation.get("server_name") or "selected server"
                    self.var_start_hint.set(f"Map generation is running for {name}.")
                else:
                    self.var_start_hint.set("Server is running.")
            else:
                readiness = self.controller.server_run_readiness()
                if readiness.get("ready"):
                    self._btn_start.configure(state="disabled" if generating else "normal")
                    server_info = readiness.get("server") or {}
                    if str(server_info.get("map_status") or "") != "Active":
                        self.var_start_hint.set("Ready to start map generation.")
                    else:
                        self.var_start_hint.set("Ready to start.")
                else:
                    self._btn_start.configure(state="disabled")
                    self.var_start_hint.set("; ".join(readiness.get("reasons") or ["Not ready."]))
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
