from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from datetime import datetime

from .base_tab import BaseTab

class DashboardTab(BaseTab):
    TAB_ID = "dashboard"
    TAB_TITLE = "Dashboard"
    ORDER = 0

    def __init__(self, controller, log_fn):
        super().__init__(controller, log_fn)
        
        # Live Variables
        self.var_status = tk.StringVar(value="OFFLINE")
        self.var_port = tk.StringVar(value="--")
        self.var_uptime = tk.StringVar(value="--")
        self.var_last_backup = tk.StringVar(value="Never")

        # Dynamic Widgets
        self.lbl_status = None
        self.btn_start = None
        self.btn_stop = None

    def build(self, parent):
        self.frame = ttk.Frame(parent)
        
        # 3-Column Layout
        self.frame.columnconfigure(0, weight=1)
        self.frame.columnconfigure(1, weight=1)
        self.frame.columnconfigure(2, weight=1)

        # --- PANEL 1: Server Health ---
        health = ttk.LabelFrame(self.frame, text="Server Health")
        health.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        
        # Status Indicator
        self.lbl_status = ttk.Label(
            health, 
            textvariable=self.var_status, 
            font=("Segoe UI", 16, "bold"),
            foreground="#D24C3F" # Default Red
        )
        self.lbl_status.pack(pady=(15, 5))

        # Port & Uptime
        info = ttk.Frame(health)
        info.pack(fill="x", padx=10, pady=10)
        
        self._make_info_row(info, "Port:", self.var_port, 0)
        self._make_info_row(info, "Last Start:", self.var_uptime, 1)

        # --- PANEL 2: Quick Actions ---
        actions = ttk.LabelFrame(self.frame, text="Quick Actions")
        actions.grid(row=0, column=1, sticky="nsew", padx=0, pady=12)
        actions.columnconfigure(0, weight=1)

        self.btn_start = ttk.Button(actions, text="Start Server", command=self._do_start)
        self.btn_start.pack(fill="x", padx=20, pady=(20, 5))

        self.btn_stop = ttk.Button(actions, text="Stop Server", command=self._do_stop)
        self.btn_stop.pack(fill="x", padx=20, pady=5)
        
        ttk.Separator(actions, orient="horizontal").pack(fill="x", padx=10, pady=15)

        ttk.Button(actions, text="View Backups", command=self._goto_backups).pack(fill="x", padx=20, pady=5)

        # --- PANEL 3: Backup Status ---
        # (Using the AppState data we verified in Phase 2)
        backup_pnl = ttk.LabelFrame(self.frame, text="Data Safety")
        backup_pnl.grid(row=0, column=2, sticky="nsew", padx=12, pady=12)
        
        b_info = ttk.Frame(backup_pnl)
        b_info.pack(fill="x", padx=10, pady=10)
        self._make_info_row(b_info, "Last Backup:", self.var_last_backup, 0)

        # Initial Load
        self._refresh_ui_state()
        return self.frame

    def _make_info_row(self, parent, label, var, row):
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text=label, foreground="#B8AF9F").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Label(parent, textvariable=var, font=("Segoe UI", 9, "bold")).grid(row=row, column=1, sticky="e", pady=2)

    # -------------------------
    # Lifecycle / Refresh
    # -------------------------
    def refresh(self):
        """Called by UiApp main loop"""
        self._refresh_ui_state()

    def on_show(self):
        self._refresh_ui_state()

    def _refresh_ui_state(self):
        # 1. Server Run State
        is_running = self.controller.is_server_running()
        
        if is_running:
            self.var_status.set("ONLINE")
            self.lbl_status.configure(foreground="#78B26E") # Green
            self.btn_start.state(["disabled"])
            self.btn_stop.state(["!disabled"])
        else:
            self.var_status.set("OFFLINE")
            self.lbl_status.configure(foreground="#D24C3F") # Red
            self.btn_start.state(["!disabled"])
            self.btn_stop.state(["disabled"])

        # 2. Config Data
        state = self.controller.get_state()
        self.var_port.set(str(state.port))
        self.var_uptime.set(state.last_started_at or "Unknown")
        self.var_last_backup.set(state.last_backup_at or "Never")

    # -------------------------
    # Actions
    # -------------------------
    def _do_start(self):
        try:
            self.controller.start_server()
        except Exception as e:
            self.log(f"[ERROR] Start failed: {e}")

    def _do_stop(self):
        try:
            self.controller.stop_server_graceful()
        except Exception as e:
            self.log(f"[ERROR] Stop failed: {e}")

    def _goto_backups(self):
        # A simple hack to switch tabs: we ask the notebook to select the backups tab
        # This relies on the notebook structure in UiApp.
        # Ideally, UiApp would expose a 'switch_to(tab_id)' method.
        # For now, we just log it as a TODO or let the user click the tab.
        self.log("[INFO] Switch to Backups tab manually (Auto-switch not yet implemented).")