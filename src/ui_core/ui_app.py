# src/ui_core/ui_app.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
import os
from pathlib import Path
import sys
from time import perf_counter
from typing import Callable, Dict, List, Optional

from src.orchestration_core import AppController
from src.orchestration_core.errors import ValidationError, NotRunningError

from .theme import Theme
from .log_sink import LogSink
from .widgets.log_view import LogView
from .tabs.base_tab import BaseTab
# REMOVED: from .tabs.placeholder_tab import PlaceholderTab 
from .tabs.registry import get_tab_classes


class UiApp:
    """
    Tkinter UI Orchestrator:
      - owns the root window + main layout
      - owns the Notebook (tabs) and their lifecycle
      - owns the LogView + drains threaded log sink
      - pumps server output + logs + visible-tab refresh on a timer
      - manages clean shutdown

    Design rules:
      - Tabs call AppController for actions and state
      - Tabs write logs via log_fn (thread-safe)
      - UiApp is the only place that owns the tick loop
    """

    def __init__(self, app_dir: Path):
        self.app_dir = Path(app_dir).expanduser().resolve()

        self._enable_native_window_scaling()

        # Root
        self.root = tk.Tk()
        self.root.title("Server Manager")
        self.root.geometry("760x1140")  # portrait, 4:6 (2:3) aspect ratio
        self.root.minsize(600, 900)

        # Logging (thread-safe)
        self._log_sink = LogSink()
        self.log_fn: Callable[[str], None] = self._log_sink.write

        # Controller (UI-agnostic orchestration)
        self.controller = AppController(self.app_dir, self.log_fn)

        # Theme
        Theme(self.root).apply()

        # Layout widgets
        self.main: Optional[ttk.Frame] = None
        self.notebook: Optional[ttk.Notebook] = None
        self.log_view: Optional[LogView] = None
        self._generation_notice_window: Optional[tk.Toplevel] = None

        # Tabs tracking
        self._tabs: List[BaseTab] = []
        self._tab_by_frame: Dict[str, BaseTab] = {}

        # Tick loop config
        self._tick_ms = 200
        self._server_poll_interval_s = 0.5
        self._log_drain_interval_s = 0.5
        self._tab_refresh_interval_s = 1.0
        self._last_server_poll_at = 0.0
        self._last_log_drain_at = 0.0
        self._last_tab_refresh_at = 0.0
        self._disable_ui_pump = os.environ.get("VS_MANAGER_DISABLE_UI_PUMP") == "1"
        self._disable_window_settle_throttle = (
            os.environ.get("VS_MANAGER_DISABLE_WINDOW_SETTLE_THROTTLE") == "1"
        )
        self._window_settle_until = 0.0
        self._window_settle_pause_s = 0.15
        self._window_settle_tick_ms = 80
        self._is_closing = False

        # Build UI
        self._build_layout()
        self._build_tabs()

        # Load config at startup
        try:
            self.controller.load_state()
        except Exception as e:
            self.log_fn(f"[ERROR] Failed to load config: {e}")

        # Ensure background services are started (idempotent)
        try:
            self.controller.backups_start_scheduler()
        except Exception as e:
            self.log_fn(f"[ERROR] Failed to start backup scheduler: {e}")

        # Event handlers
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        if self._disable_window_settle_throttle:
            self.log_fn("[DIAG] Window settle throttle disabled by VS_MANAGER_DISABLE_WINDOW_SETTLE_THROTTLE=1.")
        else:
            self.root.bind("<Configure>", self._on_root_configure, add="+")

        # Start pump loop
        if self._disable_ui_pump:
            self.log_fn("[DIAG] UI pump disabled by VS_MANAGER_DISABLE_UI_PUMP=1.")
        else:
            self._schedule_tick()

    # -------------------------
    # Layout + tabs
    # -------------------------

    def _enable_native_window_scaling(self) -> None:
        if sys.platform != "win32":
            return

        try:
            import ctypes

            try:
                # Per-monitor v2 awareness gives Windows the cleanest native drag
                # behavior on mixed-DPI displays. Must run before Tk creates HWNDs.
                ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
                return
            except Exception:
                pass

            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
                return
            except Exception:
                pass

            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        except Exception:
            return

    def _build_layout(self) -> None:
        self.main = ttk.Frame(self.root)
        self.main.pack(fill="both", expand=True)

        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(0, weight=3)
        self.main.rowconfigure(1, weight=1)

        self.notebook = ttk.Notebook(self.main)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        self.log_view = LogView(self.main, max_lines=2500)
        self.log_view.grid(row=1, column=0, sticky="nsew")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _build_tabs(self) -> None:
        assert self.notebook is not None

        # UPDATED: We now rely purely on the registry. 
        # The registry includes DashboardTab (order 0), so it comes first automatically.
        tab_classes: List[type[BaseTab]] = get_tab_classes()

        for tab_cls in tab_classes:
            tab = tab_cls(self.controller, self.log_fn)
            frame = tab.build(self.notebook)
            self.notebook.add(frame, text=getattr(tab, "TAB_TITLE", "Tab"))
            self._tabs.append(tab)

            # map notebook tab id -> tab instance
            self._tab_by_frame[str(frame)] = tab

        # Trigger on_show for initial tab
        self._fire_current_tab_on_show()

    # -------------------------
    # Events
    # -------------------------

    def _on_tab_changed(self, _event=None) -> None:
        self._fire_current_tab_on_show()

    def _on_root_configure(self, event) -> None:
        if event.widget is not self.root:
            return
        self._window_settle_until = perf_counter() + self._window_settle_pause_s

    def _fire_current_tab_on_show(self) -> None:
        try:
            assert self.notebook is not None
            current = self.notebook.select()
            tab = self._tab_by_frame.get(current)
            if tab:
                tab.on_show()
        except Exception:
            # never let UI fail because a tab hook errored
            pass

    # -------------------------
    # Tick loop (pump)
    # -------------------------

    def _schedule_tick(self) -> None:
        # Avoid scheduling after shutdown begins
        if self._is_closing:
            return
        self.root.after(self._tick_ms, self._tick)

    def _tick(self) -> None:
        if self._is_closing:
            return

        now = perf_counter()

        if now < self._window_settle_until:
            self.root.after(self._window_settle_tick_ms, self._tick)
            return

        # (1) Drain server output -> log sink
        if now - self._last_server_poll_at >= self._server_poll_interval_s:
            self._last_server_poll_at = now
            try:
                out_lines = self.controller.poll_server_output(max_lines=100)
                if out_lines:
                    for line in out_lines:
                        self.log_fn(line)
            except Exception as e:
                self.log_fn(f"[ERROR] poll_server_output failed: {e}")

        # (2) Drain buffered logs -> LogView
        if now - self._last_log_drain_at >= self._log_drain_interval_s:
            self._last_log_drain_at = now
            try:
                lines = self._log_sink.drain(max_lines=150)
                if lines:
                    assert self.log_view is not None
                    self.log_view.append_lines(lines)
            except Exception:
                # log view failures should not crash app
                pass

        # (3) Refresh visible tab
        if now - self._last_tab_refresh_at >= self._tab_refresh_interval_s:
            self._last_tab_refresh_at = now
            try:
                assert self.notebook is not None
                current = self.notebook.select()
                tab = self._tab_by_frame.get(current)
                if tab:
                    tab.refresh()
            except Exception:
                pass

        try:
            notice = self.controller.consume_map_generation_notice()
            if notice:
                self._show_generation_notice(notice)
        except Exception as e:
            self.log_fn(f"[ERROR] Failed showing map generation notice: {e}")

        self._schedule_tick()

    def _show_generation_notice(self, notice: dict) -> None:
        if self._generation_notice_window and self._generation_notice_window.winfo_exists():
            return

        auto_close = bool(self.controller.get_state().generation_alert_auto_close)
        title = "Map Generation Complete" if notice.get("status") == "completed" else "Map Generation Stopped"

        win = tk.Toplevel(self.root)
        self._generation_notice_window = win
        win.title(title)
        win.transient(self.root)
        win.resizable(False, False)

        body = ttk.Frame(win, padding=16)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text=title, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(body, text=str(notice.get("message") or ""), wraplength=460).pack(anchor="w", pady=(8, 4))

        detail = []
        if notice.get("started_at"):
            detail.append(f"Started: {notice['started_at']}")
        if notice.get("finished_at"):
            detail.append(f"Finished: {notice['finished_at']}")
        if detail:
            ttk.Label(body, text="\n".join(detail), foreground="#B8AF9F").pack(anchor="w", pady=(0, 10))

        var_auto_close = tk.BooleanVar(value=auto_close)
        ttk.Checkbutton(
            body,
            text="Auto-close next time after 10 seconds",
            variable=var_auto_close,
        ).pack(anchor="w", pady=(4, 12))

        def close_notice() -> None:
            if self._generation_notice_window is None:
                return
            try:
                self.controller.set_generation_alert_auto_close(var_auto_close.get())
            except Exception as e:
                self.log_fn(f"[WARN] Could not save generation alert preference: {e}")
            try:
                win.grab_release()
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass
            self._generation_notice_window = None

        ttk.Button(body, text="OK", command=close_notice).pack(anchor="e")
        win.protocol("WM_DELETE_WINDOW", close_notice)

        win.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - win.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - win.winfo_height()) // 2)
        win.geometry(f"+{x}+{y}")
        win.grab_set()
        win.focus_set()

        if auto_close:
            win.after(10000, close_notice)

    # -------------------------
    # Close behavior
    # -------------------------

    def _on_close(self) -> None:
        if self._is_closing:
            return
        self._is_closing = True

        # Optional: warn if server still running
        try:
            if self.controller.is_server_running():
                choice = messagebox.askyesnocancel(
                    "Server is running",
                    "The server appears to still be running.\n\n"
                    "Yes = Stop gracefully and exit\n"
                    "No = Exit without stopping\n"
                    "Cancel = Keep app open"
                )
                if choice is None:
                    self._is_closing = False
                    self._schedule_tick()
                    return
                if choice is True:
                    try:
                        self.controller.stop_server_graceful()
                    except Exception as e:
                        # If stop fails, ask if they still want to close
                        still_close = messagebox.askyesno(
                            "Stop failed",
                            f"Graceful stop failed:\n{e}\n\nExit anyway?"
                        )
                        if not still_close:
                            self._is_closing = False
                            self._schedule_tick()
                            return
        except Exception:
            # If any unexpected UI error occurs, continue shutdown.
            pass

        # Save state (best-effort)
        try:
            self.controller.save_state()
        except Exception:
            pass

        # Stop scheduler (best-effort)
        try:
            self.controller.backups_stop_scheduler()
        except Exception:
            pass

        # Finally close window
        try:
            self.root.destroy()
        except Exception:
            pass

    # -------------------------
    # Public
    # -------------------------

    def run(self) -> None:
        self.root.mainloop()
