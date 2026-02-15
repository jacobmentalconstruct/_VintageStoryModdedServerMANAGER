from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional, List, Any

from src.server_manager_core import (
    CONFIG_FILENAME,
    AppState,
    ConfigStore,
    PortChecker,
    BackupManager,
    ServerProcess,
    ModManager,
    NetworkClient,
)

from .state_store import StateStore
from .validators import (
    validate_paths_for_start, 
    validate_backup_settings,
    validate_world_gen_settings,
)
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
      - Mod Management & Networking

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
        self._backups = BackupManager(self._log)
        self._mods = ModManager(self._log)
        self._net = NetworkClient(self._log)

        # Behavior flags / policies (tunable)
        self.disallow_backups_while_server_running = True

    # -------------------------
    # State / Config
    # -------------------------

    def get_state(self) -> AppState:
        return self._store.get_state()

    def update_state(self, transform: Callable[[AppState], AppState]) -> None:
        self._store.update(transform)

    def load_state(self) -> None:
        try:
            loaded = self._config.load()
            # Merge loaded fields into current state defaults
            self.update_state(lambda s: replace(
                s,
                server_exe_path=loaded.server_exe_path,
                data_path=loaded.data_path,
                port=loaded.port,
                backup_root=loaded.backup_root,
                backup_interval_minutes=loaded.backup_interval_minutes,
                backup_retention_days=loaded.backup_retention_days,
                backups_enabled=loaded.backups_enabled,
                last_started_at=loaded.last_started_at,
                last_backup_at=loaded.last_backup_at,
                world_settings=loaded.world_settings,
                mod_profiles=loaded.mod_profiles,
            ))
            self._log(f"[INFO] Config loaded from {self._config_path}")
        except FileNotFoundError:
            self._log("[INFO] No config file found. Using defaults.")
        except Exception as e:
            self._log(f"[ERROR] Failed to load config: {e}")

    def save_state(self) -> None:
        try:
            current = self.get_state()
            self._config.save(current)
            self._log(f"[INFO] Config saved to {self._config_path}")
        except Exception as e:
            self._log(f"[ERROR] Failed to save config: {e}")

    # -------------------------
    # Server Lifecycle
    # -------------------------

    def start_server(self) -> None:
        state = self.get_state()
        validate_paths_for_start(state)

        if self._server.is_running():
            raise ValidationError("Server is already running.")

        # Update state timestamp
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.update_state(lambda s: replace(s, last_started_at=now_str))
        
        # We save state so 'last_started_at' persists immediately
        self.save_state()

        self._server.start(
            state.server_exe_path,
            state.data_path,
            port=state.port
        )

    def stop_server_graceful(self) -> None:
        if not self._server.is_running():
            return
        self._server.stop_graceful()

    def kill_server(self) -> None:
        if not self._server.is_running():
            return
        self._server.kill()

    def is_server_running(self) -> bool:
        return self._server.is_running()

    def poll_server_output(self, max_lines: int = 100) -> List[str]:
        return self._server.read_output_lines(max_lines)

    def send_server_command(self, cmd: str) -> None:
        if not self._server.is_running():
            raise NotRunningError("Cannot send command; server is not running.")
        self._server.write_stdin(cmd)

    # -------------------------
    # Backup Lifecycle
    # -------------------------

    def backups_start_scheduler(self) -> None:
        self._backups.start_scheduler(
            interval_minutes_fn=lambda: self.get_state().backup_interval_minutes,
            is_enabled_fn=lambda: self.get_state().backups_enabled,
            on_backup_due=self._on_scheduled_backup_due
        )

    def backups_stop_scheduler(self) -> None:
        self._backups.stop_scheduler()

    def _on_scheduled_backup_due(self) -> None:
        """Callback from background thread when timer fires."""
        state = self.get_state()
        if self.disallow_backups_while_server_running and self._server.is_running():
            self._log("[SKIP] Scheduled backup skipped because server is running.")
            return

        try:
            self.create_backup(trigger="Auto")
            
            # Auto-prune logic
            if state.backup_retention_days > 0:
                pruned = self._backups.prune_old_backups(
                    Path(state.backup_root), 
                    state.backup_retention_days
                )
                if pruned > 0:
                    self._log(f"[INFO] Pruned {pruned} old backups.")

        except Exception as e:
            self._log(f"[ERROR] Scheduled backup failed: {e}")

    def create_backup(self, trigger: str = "Manual") -> None:
        state = self.get_state()
        validate_backup_settings(state)

        # Policy check
        if self.disallow_backups_while_server_running and self._server.is_running():
            raise ValidationError("Cannot create backup while server is running.")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Execute
        zip_path = self._backups.create_backup_zip(
            data_path=Path(state.data_path),
            backup_root=Path(state.backup_root),
            prefix="VS_Backup"
        )
        
        self._log(f"[OK] {trigger} Backup created: {zip_path.name}")
        
        # Update State
        self.update_state(lambda s: replace(s, last_backup_at=timestamp))
        self.save_state()

    def list_backups(self) -> List[Any]:
        """Returns list of BackupInfo objects."""
        root = self.get_state().backup_root
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
    # Mod Orchestration
    # -------------------------

    def list_mods(self) -> List[Any]:
        """Scans the active server data path for mods."""
        state = self.get_state()
        if not state.data_path:
            return []
        return self._mods.list_available_mods(state.data_path)

    def bundle_mods_for_players(self, profile_name: str = "Standard") -> Optional[Path]:
        """Zips up the current mod folder for distribution."""
        state = self.get_state()
        if not state.data_path or not state.backup_root:
            raise ValidationError("Data Path and Backup Root must be set to bundle mods.")

        return self._mods.create_client_bundle(
            state.data_path,
            state.backup_root,
            profile_name
        )

    def fetch_online_mods(self) -> List[Any]:
        """Fetches and parses the online mod catalog."""
        raw_data = self._net.fetch_mod_db()
        if not raw_data:
            return []
        return self._mods.parse_api_response(raw_data)

    def install_mod_from_url(self, url: str, filename: str) -> None:
        """Downloads a mod directly to the /Mods folder."""
        state = self.get_state()
        if not state.data_path:
            raise ValidationError("Data Path must be set before installing mods.")
        
        # Prepare destination
        mods_dir = Path(state.data_path).expanduser().resolve() / "Mods"
        mods_dir.mkdir(parents=True, exist_ok=True)
        
        dest = mods_dir / filename
        
        # Download
        success = self._net.download_file(url, str(dest))
        if success:
            self._log(f"[OK] Installed mod: {filename}")
        else:
            raise ValidationError(f"Failed to download {filename}")

    # -------------------------
    # World Gen Orchestration
    # -------------------------

    def update_world_settings(self, new_settings: dict) -> None:
        """Updates the AppState with new world generation parameters."""
        validate_world_gen_settings(new_settings)
        self.update_state(lambda s: replace(s, world_settings=new_settings))
        self._log("[OK] World generation settings updated in state.")

    # -------------------------
    # Network helpers
    # -------------------------

    def is_port_listening_localhost(self, port: int) -> bool:
        return PortChecker.is_port_listening(port)