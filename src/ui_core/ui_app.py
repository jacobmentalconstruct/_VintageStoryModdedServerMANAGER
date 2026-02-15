# src/ui_core/ui_app.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
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

        # Root
        self.root = tk.Tk()
        self.root.title("Server Manager")
        self.root.geometry("1100x700")

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

        # Tabs tracking
        self._tabs: List[BaseTab] = []
        self._tab_by_frame: Dict[str, BaseTab] = {}

        # Tick loop config
        self._tick_ms = 150
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

        # Start pump loop
        self._schedule_tick()

    # -------------------------
    # Layout + tabs
    # -------------------------

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

        # (1) Drain server output -> log sink
        try:
            out_lines = self.controller.poll_server_output(max_lines=200)
            if out_lines:
                for line in out_lines:
                    self.log_fn(line)
        except Exception as e:
            self.log_fn(f"[ERROR] poll_server_output failed: {e}")

        # (2) Drain buffered logs -> LogView
        try:
            lines = self._log_sink.drain(max_lines=500)
            if lines:
                assert self.log_view is not None
                self.log_view.append_lines(lines)
        except Exception:
            # log view failures should not crash app
            pass

        # (3) Refresh visible tab
        try:
            assert self.notebook is not None
            current = self.notebook.select()
            tab = self._tab_by_frame.get(current)
            if tab:
                tab.refresh()
        except Exception:
            pass

        self._schedule_tick()

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