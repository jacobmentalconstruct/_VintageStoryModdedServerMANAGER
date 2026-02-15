from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional, List

from src.server_manager_core import (
    CONFIG_FILENAME,
    AppState,
    ConfigStore,
    PortChecker,
    BackupManager,
    ServerProcess,
)

from .state_store import StateStore
from .validators import validate_paths_for_start, validate_backup_settings
from .errors import ValidationError, NotRunningError


class AppController:
    """
    UI-agnostic orchestration layer.

    Owns:
      - Live state store
      - Config persistence
      - Server process lifecycle
      - Backup scheduler lifecycle
      - Port check helpers

    UI should:
      - call controller methods
      - render state from controller.get_state()
      - append logs via log_fn passed into controller
    """

    def __init__(
        self,
        app_dir: Path,
        log_fn: Callable[[str], None],
        *,
        config_filename: str = CONFIG_FILENAME,
    ):
        self._log = log_fn
        self._app_dir = Path(app_dir).expanduser().resolve()
        self._config_path = self._app_dir / config_filename

        self._store = StateStore(AppState())
        self._config = ConfigStore(self._config_path)

        self._server = ServerProcess(self._log)
        try:
            import importlib
            mod = importlib.import_module(ServerProcess.__module__)
            mod_file = getattr(mod, "__file__", "<no __file__>")
            self._log(f"[DEBUG] ServerProcess imported from: {ServerProcess.__module__} :: {mod_file}")
        except Exception as e:
            self._log(f"[DEBUG] ServerProcess import path check failed: {e}")

        self._backups = BackupManager(self._log)

        # Behavior flags / policies (tunable)
        self.disallow_backups_while_server_running = True

    # -------------------------
    # State + persistence
    # -------------------------

    def load_state(self) -> AppState:
        state = self._config.load()
        self._store.set(state)
        self._log(f"[OK] Loaded config: {self._config_path}")
        return self.get_state()

    def save_state(self) -> None:
        state = self._store.get()
        self._config.save(state)
        self._log(f"[OK] Saved config: {self._config_path}")

    def get_state(self) -> AppState:
        return self._store.get()

    def set_state(self, new_state: AppState) -> None:
        self._store.set(new_state)

    def update_state(self, fn: Callable[[AppState], AppState]) -> AppState:
        return self._store.update(fn)

    # -------------------------
    # Server lifecycle
    # -------------------------

    def is_server_running(self) -> bool:
        return self._server.is_running()

    def start_server(self) -> None:
        state = self.get_state()
        validate_paths_for_start(state)

        self._server.start(state.server_exe_path, state.data_path)

        # stamp
        self.update_state(lambda s: replace(
            s,
            last_started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

    def stop_server_graceful(self) -> None:
        if not self._server.is_running():
            raise NotRunningError("Server is not running.")
        self._server.stop_graceful()

    def stop_server_force(self) -> None:
        if not self._server.is_running():
            raise NotRunningError("Server is not running.")
        self._server.stop_force()

    def kill_server(self) -> None:
        if not self._server.is_running():
            raise NotRunningError("Server is not running.")
        self._server.kill()

    def send_server_command(self, cmd: str) -> None:
        if not self._server.is_running():
            raise NotRunningError("Server is not running.")
        self._server.send_command(cmd)

    def poll_server_exit(self) -> Optional[int]:
        """A2: Check if the server has exited; returns exit code if stopped, else None."""
        return self._server.poll_exit()

    def poll_server_output(self, max_lines: int = 200) -> List[str]:
        """
        Drain buffered output lines from the server process.
        UI orchestrator typically calls this in a Tk `after()` loop and writes lines to its log view.

        A2: also polls for exit so an exit warning line is emitted into the output queue.
        """
        self._server.poll_exit()
        return self._server.poll_output(max_lines=max_lines)

    # -------------------------
    # Backups
    # -------------------------

    def backups_start_scheduler(self) -> None:
        """
        Starts the backup scheduler thread if it isn't running.
        The scheduler reads state via get_state_fn each cycle.
        """
        # validate if enabled (we don't want the scheduler to spam errors)
        state = self.get_state()
        if state.backups_enabled:
            validate_backup_settings(state)

        self._backups.start_scheduler(
            get_state_fn=self.get_state,
            set_state_fn=self.set_state,
            can_backup_fn=self._can_backup_now,
        )
        self._log("[OK] Backup scheduler started.")

    def backups_stop_scheduler(self) -> None:
        self._backups.stop_scheduler()
        self._log("[OK] Backup scheduler stop requested.")

    def set_backups_enabled(self, enabled: bool) -> None:
        def _mut(s: AppState) -> AppState:
            return replace(s, backups_enabled=bool(enabled))
        state = self.update_state(_mut)
        if enabled:
            validate_backup_settings(state)
        self._log(f"[OK] Backups enabled = {enabled}")

    def open_backup_folder(self) -> None:
        self._backups.open_backup_folder(self.get_state())

    def open_data_folder(self) -> None:
        self._backups.open_data_folder(self.get_state())

    def _can_backup_now(self) -> bool:
        if self.disallow_backups_while_server_running and self._server.is_running():
            return False
        return True

    # -------------------------
    # Wave B: Vault helpers
    # -------------------------

    def list_backups(self):
        """Wave B: List snapshot zips in backup_root (newest-first)."""
        state = self.get_state()
        root = (state.backup_root or "").strip()
        if not root:
            return []
        return self._backups.list_backups(Path(root))

    def restore_backup(self, zip_path: str) -> None:
        """
        Wave B: Point-in-time restore.

        Policy:
          - Requires data_path
          - Restores into <data_path>/Saves
          - If the server is running, refuse (UI should stop server first)
        """
        state = self.get_state()
        if not state.data_path:
            raise ValidationError("Data path is not set. Configure it in the Server tab first.")

        if self._server.is_running():
            raise ValidationError("Refusing restore while server is running. Stop the server first.")

        data_root = Path(state.data_path).expanduser().resolve()
        saves_dir = data_root / "Saves"

        zp = Path(zip_path).expanduser().resolve()
        self._log(f"[INFO] Restore requested: {zp}")
        self._log(f"[INFO] Restore target: {saves_dir}")

        renamed = self._backups.restore_backup_zip(zp, saves_dir, safety_rename=True)
        if str(renamed):
            self._log(f"[WARN] Previous Saves folder archived as: {renamed}")

        self._log("[OK] Restore completed.")

    # -------------------------
    # Network helpers
    # -------------------------

    def is_port_listening_localhost(self, port: Optional[int] = None) -> bool:
        state = self.get_state()
        p = int(port) if port is not None else int(state.port)
        return PortChecker.is_tcp_listening("127.0.0.1", p)








