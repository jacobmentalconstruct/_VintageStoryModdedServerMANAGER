# src/ui_core/tabs/backup_tab.py
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from dataclasses import replace
from pathlib import Path

# Import compatibility: supports BOTH run modes:
#   - python src/app.py        (no 'src.' prefix packages)
#   - python -m src.app        ('src.' prefix packages)
try:
    from src.orchestration_core.errors import ValidationError
    from src.server_manager_core.models import AppState
except ModuleNotFoundError:  # fallback for non -m launch
    from orchestration_core.errors import ValidationError
    from server_manager_core.models import AppState

from .base_tab import BaseTab


class BackupsTab(BaseTab):
    TAB_ID = "backups"
    TAB_TITLE = "Backups"
    ORDER = 20

    def __init__(self, controller, log_fn):
        super().__init__(controller, log_fn)

        self.var_enabled = tk.BooleanVar(value=False)
        self.var_backup_root = tk.StringVar()
        self.var_interval = tk.StringVar()
        self.var_retention = tk.StringVar()

        # Snapshot browser
        self._tree = None
        self._tree_rows: dict[str, str] = {}  # iid -> zip_path

        self._btn_apply = None
        self._btn_refresh = None
        self._btn_restore = None
        self._btn_open_backup = None
        self._btn_open_data = None

        # prevent recursion when we programmatically adjust checkbox state
        self._squelch_toggle = False

    def build(self, parent):
        self.frame = ttk.Frame(parent)

        outer = ttk.Frame(self.frame)
        outer.pack(fill="both", expand=True, padx=12, pady=12)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        # -------------------------
        # Settings
        # -------------------------
        box = ttk.LabelFrame(outer, text="Backup Settings")
        box.grid(row=0, column=0, sticky="nsew")
        box.columnconfigure(1, weight=1)

        chk = ttk.Checkbutton(
            box,
            text="Enable scheduled backups",
            variable=self.var_enabled,
            command=self._on_toggle_enabled,
        )
        chk.grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 6))

        ttk.Label(box, text="Backup Folder:").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(box, textvariable=self.var_backup_root).grid(row=1, column=1, sticky="ew", padx=8, pady=6)
        ttk.Button(box, text="Browse…", command=self._browse_backup_root).grid(row=1, column=2, sticky="e", padx=8, pady=6)

        ttk.Label(box, text="Interval (minutes):").grid(row=2, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(box, textvariable=self.var_interval, width=12).grid(row=2, column=1, sticky="w", padx=8, pady=6)

        ttk.Label(box, text="Retention (days):").grid(row=3, column=0, sticky="w", padx=8, pady=(6, 8))
        ttk.Entry(box, textvariable=self.var_retention, width=12).grid(row=3, column=1, sticky="w", padx=8, pady=(6, 8))

        btn_row = ttk.Frame(box)
        btn_row.grid(row=4, column=0, columnspan=3, sticky="ew", padx=8, pady=(0, 8))
        btn_row.columnconfigure(0, weight=1)

        self._btn_apply = ttk.Button(btn_row, text="Apply to Config", command=self._apply_to_state)
        self._btn_apply.pack(side="left")

        # -------------------------
        # Snapshot Browser (Wave B2)
        # -------------------------
        vault = ttk.LabelFrame(outer, text="Snapshots")
        vault.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        vault.columnconfigure(0, weight=1)
        vault.rowconfigure(1, weight=1)

        top = ttk.Frame(vault)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 6))
        top.columnconfigure(0, weight=1)

        self._btn_refresh = ttk.Button(top, text="Refresh", command=self._refresh_snapshot_list)
        self._btn_restore = ttk.Button(top, text="Restore Selected…", command=self._restore_selected)
        self._btn_refresh.pack(side="left")
        self._btn_restore.pack(side="left", padx=(10, 0))

        columns = ("timestamp", "size", "filename")
        self._tree = ttk.Treeview(vault, columns=columns, show="headings", selectmode="browse")
        self._tree.heading("timestamp", text="Timestamp")
        self._tree.heading("size", text="Size")
        self._tree.heading("filename", text="Filename")

        self._tree.column("timestamp", width=180, anchor="w")
        self._tree.column("size", width=100, anchor="e")
        self._tree.column("filename", width=480, anchor="w")

        ysb = ttk.Scrollbar(vault, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=ysb.set)

        self._tree.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 8))
        ysb.grid(row=1, column=1, sticky="ns", padx=(0, 8), pady=(0, 8))

        # -------------------------
        # Utilities
        # -------------------------
        util = ttk.LabelFrame(outer, text="Utilities")
        util.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        util.columnconfigure(0, weight=1)

        util_row = ttk.Frame(util)
        util_row.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        util_row.columnconfigure(0, weight=1)

        self._btn_open_backup = ttk.Button(util_row, text="Open Backup Folder", command=self._open_backup_folder)
        self._btn_open_data = ttk.Button(util_row, text="Open Data Folder", command=self._open_data_folder)
        self._btn_open_backup.pack(side="left")
        self._btn_open_data.pack(side="left", padx=(10, 0))

        # Initial fill
        self._load_from_state()
        self._refresh_snapshot_list()
        return self.frame

    # -------------------------
    # Tab lifecycle
    # -------------------------

    def on_show(self) -> None:
        self._load_from_state()
        self._refresh_snapshot_list()

    def refresh(self) -> None:
        return

    # -------------------------
    # State sync
    # -------------------------

    def _load_from_state(self) -> None:
        state = self.controller.get_state()
        self._squelch_toggle = True
        try:
            self.var_enabled.set(bool(state.backups_enabled))
        finally:
            self._squelch_toggle = False

        self.var_backup_root.set(state.backup_root or "")
        self.var_interval.set(str(state.backup_interval_minutes))
        self.var_retention.set(str(state.backup_retention_days))

    def _apply_to_state(self) -> None:
        """Commit UI fields into state and validate enabling via controller."""

        def mut(s: AppState) -> AppState:
            root = self.var_backup_root.get().strip()
            try:
                interval = int(self.var_interval.get().strip())
            except Exception:
                interval = s.backup_interval_minutes
            try:
                retention = int(self.var_retention.get().strip())
            except Exception:
                retention = s.backup_retention_days

            return replace(
                s,
                backup_root=root,
                backup_interval_minutes=interval,
                backup_retention_days=retention,
            )

        new_state = self.controller.update_state(mut)

        self.var_backup_root.set(new_state.backup_root or "")
        self.var_interval.set(str(new_state.backup_interval_minutes))
        self.var_retention.set(str(new_state.backup_retention_days))

        want_enabled = bool(self.var_enabled.get())

        try:
            self.controller.set_backups_enabled(want_enabled)
            self.controller.backups_start_scheduler()
            self.log("[OK] Backup settings applied.")
        except ValidationError as e:
            self.log(f"[ERROR] Backup settings invalid: {e}")
            messagebox.showerror("Invalid backup settings", str(e))

            self._squelch_toggle = True
            try:
                self.var_enabled.set(False)
            finally:
                self._squelch_toggle = False

            try:
                self.controller.set_backups_enabled(False)
            except Exception:
                pass
        except Exception as e:
            self.log(f"[ERROR] Failed applying backup settings: {e}")
            messagebox.showerror("Apply failed", str(e))

        actual = bool(self.controller.get_state().backups_enabled)
        self._squelch_toggle = True
        try:
            self.var_enabled.set(actual)
        finally:
            self._squelch_toggle = False

        self._refresh_snapshot_list()

    # -------------------------
    # Snapshot Browser
    # -------------------------

    def _refresh_snapshot_list(self) -> None:
        if not self._tree:
            return

        # Clear
        for iid in self._tree.get_children(""):
            self._tree.delete(iid)
        self._tree_rows.clear()

        state = self.controller.get_state()
        backup_root = (state.backup_root or "").strip()
        if not backup_root:
            return

        # Controller passthrough required:
        #   list_backups() -> list[BackupInfo]
        if not hasattr(self.controller, "list_backups"):
            self.log("[ERROR] AppController missing list_backups(); cannot populate snapshot browser.")
            return

        try:
            backups = self.controller.list_backups()
        except Exception as e:
            self.log(f"[ERROR] Failed listing backups: {e}")
            return

        for i, b in enumerate(backups):
            # b may be dataclass with properties; be defensive
            ts = getattr(b, "mtime_local", "")
            size_bytes = int(getattr(b, "size_bytes", 0) or 0)
            size_kib = size_bytes / 1024.0
            filename = getattr(b, "filename", "")
            path = getattr(b, "path", "")

            iid = f"b{i}"
            self._tree.insert("", "end", iid=iid, values=(ts, f"{size_kib:,.1f} KiB", filename))
            self._tree_rows[iid] = path

    def _restore_selected(self) -> None:
        if not self._tree:
            return
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Restore", "Select a snapshot to restore.")
            return

        iid = sel[0]
        zip_path = self._tree_rows.get(iid)
        if not zip_path:
            messagebox.showerror("Restore", "Selected snapshot path not found.")
            return

        state = self.controller.get_state()
        if not state.data_path:
            messagebox.showerror("Restore", "Data path is not set. Configure it in the Server tab first.")
            return

        # If server is running, block restore (controller refuses restore while running)
        try:
            if hasattr(self.controller, "is_server_running") and self.controller.is_server_running():
                messagebox.showerror(
                    "Server Running",
                    "The server appears to be running.\n\n"
                    "Stop the server first, then run the restore.",
                )
                return
        except Exception:
            pass

        # Safety lock: typed confirmation
        confirm = tk.Toplevel(self.frame)
        confirm.title("Confirm Restore")
        confirm.geometry("520x220")
        confirm.transient(self.frame.winfo_toplevel())
        confirm.grab_set()

        ttk.Label(confirm, text="Point-in-time Restore (Safety Lock)", style="Heading.TLabel").pack(anchor="w", padx=12, pady=(12, 6))
        msg = (
            "This will rename the current save folder to a .bak_<timestamp> folder\n"
            "and then extract the selected snapshot.\n\n"
            "Type RESTORE to confirm."
        )
        ttk.Label(confirm, text=msg).pack(anchor="w", padx=12)

        var = tk.StringVar()
        entry = ttk.Entry(confirm, textvariable=var)
        entry.pack(fill="x", padx=12, pady=(10, 6))
        entry.focus_set()

        btns = ttk.Frame(confirm)
        btns.pack(fill="x", padx=12, pady=(6, 12))
        btns.columnconfigure(0, weight=1)

        def do_restore():
            if var.get().strip().upper() != "RESTORE":
                messagebox.showerror("Confirm", "Type RESTORE to proceed.")
                return

            if not hasattr(self.controller, "restore_backup"):
                messagebox.showerror("Restore", "AppController missing restore_backup(); cannot restore.")
                self.log("[ERROR] AppController missing restore_backup().")
                confirm.destroy()
                return

            try:
                self.controller.restore_backup(zip_path)
                self.log(f"[OK] Restore requested: {zip_path}")
            except Exception as e:
                self.log(f"[ERROR] Restore failed: {e}")
                messagebox.showerror("Restore failed", str(e))
            finally:
                confirm.destroy()
                self._refresh_snapshot_list()

        ttk.Button(btns, text="Cancel", command=confirm.destroy).pack(side="right")
        ttk.Button(btns, text="Restore", command=do_restore).pack(side="right", padx=(0, 10))

    # -------------------------
    # UI actions
    # -------------------------

    def _on_toggle_enabled(self) -> None:
        if self._squelch_toggle:
            return
        self._apply_to_state()

    def _browse_backup_root(self) -> None:
        initial = self.var_backup_root.get().strip()
        init_dir = initial if initial else str(Path.cwd())
        path = filedialog.askdirectory(title="Select Backup Folder", initialdir=init_dir)
        if path:
            self.var_backup_root.set(path)
            self._apply_to_state()

    def _open_backup_folder(self) -> None:
        try:
            self.controller.open_backup_folder()
        except Exception as e:
            self.log(f"[ERROR] Could not open backup folder: {e}")
            messagebox.showerror("Open failed", str(e))

    def _open_data_folder(self) -> None:
        try:
            self.controller.open_data_folder()
        except Exception as e:
            self.log(f"[ERROR] Could not open data folder: {e}")
            messagebox.showerror("Open failed", str(e))


