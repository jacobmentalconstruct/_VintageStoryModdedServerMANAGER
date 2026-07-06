from __future__ import annotations

import shutil
import json
import os
import re
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
from src.server_manager_core.constants import SERVER_CONFIG_FILENAME

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
        self._pending_generation_notice: Optional[dict] = None

        # Behavior flags / policies (tunable)
        self.disallow_backups_while_server_running = True

    # -------------------------
    # State / Config
    # -------------------------

    def get_state(self) -> AppState:
        return self._store.get_state()

    def update_state(self, transform: Callable[[AppState], AppState]) -> AppState:
        # BUG FIX: Return the result of the store update to the UI
        return self._store.update(transform)

    def load_state(self) -> None:
        try:
            loaded = self._config.load()
            mod_repository_path = self._migrate_mod_repository_path(loaded.mod_repository_path)
            server_exe_path = loaded.server_exe_path or self._default_server_exe_path()
            # Merge loaded fields into current state defaults
            self.update_state(lambda s: replace(
                s,
                server_exe_path=server_exe_path,
                data_path=loaded.data_path,
                port=loaded.port,
                backup_root=loaded.backup_root,
                backup_interval_minutes=loaded.backup_interval_minutes,
                backup_retention_days=loaded.backup_retention_days,
                backups_enabled=loaded.backups_enabled,
                last_started_at=loaded.last_started_at,
                last_backup_at=loaded.last_backup_at,
                world_settings=loaded.world_settings,
                world_profiles=loaded.world_profiles,
                mod_profiles=loaded.mod_profiles,
                mod_repository_path=mod_repository_path,
                active_mods=loaded.active_mods,
                servers=loaded.servers,
                selected_server_id=loaded.selected_server_id,
                map_generation_in_progress=False,
                map_generation_server_id="",
                map_generation_started_at="",
                generation_alert_auto_close=loaded.generation_alert_auto_close,
            ))
            self.discover_server_worlds()
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
        self._sync_selected_server_state()
        self._require_no_map_generation("start another server")
        state = self.get_state()
        validate_paths_for_start(state)
        self._repair_server_config_for_start(Path(state.data_path).expanduser().resolve())

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
        self._mark_map_generation_started_if_needed()

    def stop_server_graceful(self) -> None:
        if not self._server.is_running():
            return
        self._server.stop_graceful()
        self._finalize_generation_if_process_stopped()

    def kill_server(self) -> None:
        if not self._server.is_running():
            return
        self._server.kill()
        self._finalize_generation_if_process_stopped()

    def stop_server_force(self) -> None:
        self.kill_server()

    def is_server_running(self) -> bool:
        return self._server.is_running()

    def poll_server_output(self, max_lines: int = 100) -> List[str]:
        lines = self._server.read_output_lines(max_lines)
        for line in lines:
            self._observe_map_generation_output(line)
        self._finalize_generation_if_ready_without_marker()
        self._finalize_generation_if_process_stopped()
        return lines

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
        self._require_no_map_generation("create a backup")
        state = self.get_state()
        validate_backup_settings(state)
        data_root = self._require_existing_data_path()

        # Policy check
        if self.disallow_backups_while_server_running and self._server.is_running():
            raise ValidationError("Cannot create backup while server is running.")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Execute
        zip_path = self._backups.create_backup_zip(
            data_path=data_root,
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
        """
        self._require_no_map_generation("restore a backup")
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

    def set_backups_enabled(self, enabled: bool) -> None:
        if enabled:
            state = self.get_state()
            validate_backup_settings(state)
        self.update_state(lambda s: replace(s, backups_enabled=bool(enabled)))
        self.save_state()

    def open_backup_folder(self) -> None:
        self._backups.open_backup_folder(self.get_state())

    def open_data_folder(self) -> None:
        self._backups.open_data_folder(self.get_state())

    # -------------------------
    # Mod Orchestration
    # -------------------------

    def list_mods(self) -> List[Any]:
        """Scans the active server data path for mods."""
        state = self.get_state()
        if not state.data_path:
            return []
        return self._mods.list_available_mods(state.data_path)

    def default_mod_repository_path(self) -> str:
        """Returns the project-local default mod repository folder."""
        return str(self._project_root() / "mods")

    def _legacy_mod_repository_path(self) -> str:
        return str(self._project_root() / "mod")

    def _migrate_mod_repository_path(self, repository_path: str) -> str:
        if not repository_path:
            return ""

        current = Path(repository_path).expanduser().resolve()
        legacy_default = Path(self._legacy_mod_repository_path()).resolve()
        if current == legacy_default:
            return self.default_mod_repository_path()

        return str(current)

    def _project_root(self) -> Path:
        return self._app_dir.parent if self._app_dir.name.lower() == "src" else self._app_dir

    def _default_server_exe_path(self) -> str:
        candidates = []
        appdata = os.environ.get("APPDATA")
        local_appdata = os.environ.get("LOCALAPPDATA")
        program_files = os.environ.get("ProgramFiles")
        program_files_x86 = os.environ.get("ProgramFiles(x86)")

        if appdata:
            candidates.append(Path(appdata) / "Vintagestory" / "VintagestoryServer.exe")
        if local_appdata:
            candidates.append(Path(local_appdata) / "Programs" / "Vintagestory" / "VintagestoryServer.exe")
            candidates.append(Path(local_appdata) / "Vintagestory" / "VintagestoryServer.exe")
        if program_files:
            candidates.append(Path(program_files) / "Vintagestory" / "VintagestoryServer.exe")
        if program_files_x86:
            candidates.append(Path(program_files_x86) / "Vintagestory" / "VintagestoryServer.exe")

        for candidate in candidates:
            try:
                if candidate.exists():
                    return str(candidate.resolve())
            except OSError:
                continue
        return ""

    def server_storage_root(self) -> Path:
        root = self._project_root() / "servers"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def list_server_worlds(self) -> List[dict]:
        self.discover_server_worlds()
        servers = self.get_state().servers
        return sorted(
            (self._server_info_for_display(item) for item in servers.values()),
            key=lambda item: (
                str(item.get("name") or item.get("id") or "").lower(),
                str(item.get("id") or "").lower(),
            ),
        )

    def discover_server_worlds(self) -> List[dict]:
        root = self.server_storage_root()
        state = self.get_state()
        servers = dict(state.servers)

        changed = False
        for child in root.iterdir():
            if not child.is_dir():
                continue

            marker = child / ".vs_manager_server.json"
            info = None
            if marker.exists():
                try:
                    info = json.loads(marker.read_text(encoding="utf-8"))
                except Exception as e:
                    self._log(f"[WARN] Failed reading server marker {marker}: {e}")

            server_id = str((info or {}).get("id") or child.name)
            name = str((info or {}).get("name") or child.name)
            existing = servers.get(server_id, {})
            merged = {
                **existing,
                **(info or {}),
                "id": server_id,
                "name": name,
                "data_path": str(child.resolve()),
            }
            if servers.get(server_id) != merged:
                servers[server_id] = merged
                changed = True

        if changed:
            self.update_state(lambda s: replace(s, servers=servers))

        selected_changed = self._sync_selected_server_state(servers)

        if changed or selected_changed:
            self.save_state()

        return sorted(
            (self._server_info_for_display(item) for item in servers.values()),
            key=lambda item: (
                str(item.get("name", "")).lower(),
                str(item.get("id", "")).lower(),
            ),
        )

    def select_server_world(self, server_id: str) -> dict:
        servers = {item["id"]: item for item in self.list_server_worlds()}
        info = servers.get(server_id)
        if not info:
            raise ValidationError(f"Server world not found: {server_id}")

        state = self.get_state()
        if state.map_generation_in_progress and server_id != state.map_generation_server_id:
            raise ValidationError("Map generation is in progress. Wait for it to finish before selecting another server.")

        data_path = str(Path(info["data_path"]).expanduser().resolve())
        port = int(info.get("port") or self.get_state().port)
        self.update_state(lambda s: replace(
            s,
            selected_server_id=server_id,
            data_path=data_path,
            port=port,
            world_settings=dict(info.get("world_settings") or s.world_settings),
            active_mods=list(info.get("active_mods") or s.active_mods),
        ))
        self.save_state()
        self._log(f"[OK] Selected server world: {info.get('name', server_id)}")
        return info

    def selected_server_info(self) -> Optional[dict]:
        selected_id = self.get_state().selected_server_id
        if not selected_id:
            return None
        servers = {item["id"]: item for item in self.list_server_worlds()}
        return servers.get(selected_id)

    def server_run_readiness(self) -> dict:
        self._sync_selected_server_state()
        state = self.get_state()
        info = self.selected_server_info()
        reasons = []

        if state.map_generation_in_progress:
            reasons.append("Map generation is already in progress.")

        if not info:
            reasons.append("Select a server world.")

        try:
            validate_paths_for_start(state)
        except ValidationError as e:
            reasons.append(str(e))

        if info:
            map_status = str(info.get("map_status") or "Unknown")
            data_path = str(info.get("data_path") or "")
            prepared = self._server_is_prepared_for_generation(Path(data_path).expanduser()) if data_path else False
            if map_status != "Active" and not prepared:
                reasons.append("Selected server has no active map. Use Generate Map before starting it here.")

        return {
            "ready": not reasons,
            "reasons": reasons,
            "server": info,
        }

    def map_generation_status(self) -> dict:
        state = self.get_state()
        info = state.servers.get(state.map_generation_server_id, {}) if state.map_generation_server_id else {}
        return {
            "in_progress": bool(state.map_generation_in_progress),
            "server_id": state.map_generation_server_id,
            "server_name": info.get("name") or state.map_generation_server_id,
            "started_at": state.map_generation_started_at,
            "alert_auto_close": bool(state.generation_alert_auto_close),
        }

    def consume_map_generation_notice(self) -> Optional[dict]:
        notice = self._pending_generation_notice
        self._pending_generation_notice = None
        return notice

    def set_generation_alert_auto_close(self, enabled: bool) -> None:
        self.update_state(lambda s: replace(s, generation_alert_auto_close=bool(enabled)))
        self.save_state()

    def register_current_data_path_as_server(self, name: Optional[str] = None) -> dict:
        self._require_no_map_generation("register a server world")
        data_root = self._require_existing_data_path()
        server_name = (name or data_root.name).strip() or data_root.name
        server_id = self._safe_server_id(data_root.name)
        existing = self.get_state().servers.get(server_id)
        if existing and Path(existing.get("data_path", "")).expanduser().resolve() != data_root:
            server_id = self._unique_server_id(server_name, preferred=data_root.name)
        info = self._server_info(server_id, server_name, data_root, self.get_state().world_settings)
        self._write_server_marker(info)

        def mut(s: AppState) -> AppState:
            servers = dict(s.servers)
            servers[server_id] = info
            return replace(s, servers=servers, selected_server_id=server_id, data_path=str(data_root))

        self.update_state(mut)
        self.save_state()
        self._log(f"[OK] Registered server world: {server_name}")
        return info

    def get_mod_repository_path(self) -> str:
        state = self.get_state()
        return state.mod_repository_path or self.default_mod_repository_path()

    def set_mod_repository_path(self, repository_path: str) -> None:
        clean_path = str(Path(repository_path).expanduser().resolve()) if repository_path else ""
        self.update_state(lambda s: replace(s, mod_repository_path=clean_path))
        self.save_state()
        self._log(f"[OK] Mod repository set: {self.get_mod_repository_path()}")

    def use_default_mod_repository(self) -> str:
        default_path = self.default_mod_repository_path()
        Path(default_path).mkdir(parents=True, exist_ok=True)
        self.set_mod_repository_path(default_path)
        return default_path

    def use_server_mods_as_repository(self) -> str:
        self._require_no_map_generation("use server mods as the repository")
        state = self.get_state()
        if not state.data_path:
            raise ValidationError("Data Path must be set before using server Mods as the repository.")

        server_mods = Path(state.data_path).expanduser().resolve() / "Mods"
        server_mods.mkdir(parents=True, exist_ok=True)
        self.set_mod_repository_path(str(server_mods))
        return str(server_mods)

    def list_mod_repository(self) -> List[Any]:
        repository = Path(self.get_mod_repository_path()).expanduser().resolve()
        repository.mkdir(parents=True, exist_ok=True)
        return self._mods.list_mods_in_folder(repository)

    def get_active_mod_names(self) -> List[str]:
        return list(self.get_state().active_mods)

    def set_active_mod_names(self, mod_filenames: Iterable[str]) -> List[str]:
        active_mods = []
        seen = set()
        for raw_name in mod_filenames:
            filename = Path(str(raw_name)).name
            if filename and filename not in seen:
                seen.add(filename)
                active_mods.append(filename)

        self.update_state(lambda s: replace(s, active_mods=active_mods))
        self.save_state()
        self._log(f"[OK] Active mod list saved with {len(active_mods)} mod(s).")
        return active_mods

    def apply_active_mods_to_server(self) -> int:
        self._require_no_map_generation("apply active mods")
        state = self.get_state()
        if not state.data_path:
            raise ValidationError("Data Path must be set before applying active mods.")
        if not state.active_mods:
            raise ValidationError("No active mods selected.")

        repository = self.get_mod_repository_path()
        return self._mods.copy_mods_to_server(repository, state.data_path, state.active_mods)

    def bundle_mods_for_players(
        self,
        profile_name: str = "Standard",
        mod_filenames: Optional[Iterable[str]] = None,
    ) -> Optional[Path]:
        """Zips up the current mod folder for distribution."""
        state = self.get_state()
        if not state.data_path:
            raise ValidationError("Data Path must be set to bundle mods.")

        export_root = state.backup_root or str(self._app_dir)
        if not state.backup_root:
            self._log("[WARN] Backup Root is not set; exporting mod bundle to the app folder.")

        mods_to_bundle = list(mod_filenames) if mod_filenames is not None else state.active_mods
        if not mods_to_bundle:
            raise ValidationError("No active mods selected to bundle.")

        return self._mods.create_bundle_from_folder(
            self.get_mod_repository_path(),
            export_root,
            profile_name,
            mods_to_bundle,
        )

    def fetch_online_mods(self) -> List[Any]:
        """Fetches and parses the online mod catalog."""
        raw_data = self._net.fetch_mod_db()
        if not raw_data:
            return []
        return self._mods.parse_api_response(raw_data)

    def install_mod_from_url(self, url: str, filename: str) -> None:
        """Downloads a mod directly to the /Mods folder."""
        self._require_no_map_generation("install mods to the server")
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

    def install_mod_to_repository_from_url(self, url: str, filename: str) -> None:
        """Downloads a mod directly to the configured repository folder."""
        repository = Path(self.get_mod_repository_path()).expanduser().resolve()
        repository.mkdir(parents=True, exist_ok=True)

        dest = repository / Path(filename).name
        success = self._net.download_file(url, str(dest))
        if success:
            self._log(f"[OK] Added mod to repository: {dest.name}")
        else:
            raise ValidationError(f"Failed to download {filename}")

    # -------------------------
    # World Gen Orchestration
    # -------------------------

    def update_world_settings(self, new_settings: dict) -> None:
        """Updates the AppState with new world generation parameters."""
        self._require_no_map_generation("save world settings")
        validate_world_gen_settings(new_settings)
        # 1. Update Memory
        self.update_state(lambda s: replace(s, world_settings=new_settings))
        # 2. Persist to Disk (Added Fix)
        self.save_state()
        self._log("[OK] World generation settings updated in state.")

        if self.get_state().active_mods and self.get_state().data_path:
            try:
                copied = self.apply_active_mods_to_server()
                self._log(f"[OK] Active world mods applied during world settings save: {copied}")
            except ValidationError as e:
                self._log(f"[WARN] World settings saved, but active mods were not applied: {e}")

    def list_world_profiles(self) -> dict:
        """Returns built-in world presets overlaid by saved user profiles."""
        profiles = self.default_world_profiles()
        profiles.update({
            str(name): dict(settings)
            for name, settings in self.get_state().world_profiles.items()
        })
        return dict(sorted(profiles.items(), key=lambda item: item[0].lower()))

    def default_world_profiles(self) -> dict:
        base = self._standard_world_settings()
        return {
            "Standard": base,
            "Continents & Oceans": {
                **base,
                "WorldName": "Continents",
                "landcover": 0.70,
                "oceanscale": 0.5,
                "upheavelCommonness": 0.30,
                "landformScale": 1.0,
            },
            "Island Chains": {
                **base,
                "WorldName": "Islands",
                "landcover": 0.70,
                "oceanscale": 0.1,
                "upheavelCommonness": 0.30,
                "landformScale": 1.0,
            },
            "Lush Jungle": {
                **base,
                "WorldName": "Jungle",
                "startingClimate": "hot",
                "polarEquatorDistance": 50000,
                "globalTemperature": 1.35,
                "globalPrecipitation": 1.75,
                "globalForestation": 0.65,
                "landcover": 0.92,
                "oceanscale": 2.0,
            },
            "Wild Highlands": {
                **base,
                "WorldName": "Highlands",
                "landcover": 0.95,
                "oceanscale": 3.0,
                "upheavelCommonness": 0.60,
                "geologicActivity": 0.18,
                "landformScale": 2.4,
            },
            "Crazy Caves": {
                **base,
                "WorldName": "Caves",
                "landcover": 0.90,
                "oceanscale": 2.0,
                "upheavelCommonness": 0.55,
                "geologicActivity": 0.25,
                "landformScale": 2.6,
                "caveIns": "on",
                "blockGravity": "sandgravelsoil",
                "propickNodeSearchRadius": 8,
            },
            "Easy Builders": {
                **base,
                "WorldName": "Builders",
                "deathPunishment": "keep",
                "graceTimer": 5,
                "playerHungerSpeed": 0.5,
                "creatureHostility": "passive",
                "toolDurability": 2.0,
                "temporalStorms": "rare",
                "temporalRifts": "invisible",
            },
        }

    def save_world_profile(self, name: str, settings: dict) -> None:
        self._require_no_map_generation("save a world profile")
        clean_name = self._clean_profile_name(name)
        validate_world_gen_settings(settings)

        def mut(s: AppState) -> AppState:
            profiles = dict(s.world_profiles)
            profiles[clean_name] = dict(settings)
            return replace(s, world_profiles=profiles, world_settings=dict(settings))

        self.update_state(mut)
        self.save_state()
        self._log(f"[OK] World profile saved: {clean_name}")

    def delete_world_profile(self, name: str) -> None:
        self._require_no_map_generation("delete a world profile")
        clean_name = self._clean_profile_name(name)
        profiles = dict(self.get_state().world_profiles)
        if clean_name not in profiles:
            if clean_name in self.default_world_profiles():
                raise ValidationError("Built-in profiles cannot be deleted. Save over them to customize, or pick another profile.")
            raise ValidationError(f"World profile not found: {clean_name}")

        def mut(s: AppState) -> AppState:
            updated = dict(s.world_profiles)
            updated.pop(clean_name, None)
            return replace(s, world_profiles=updated)

        self.update_state(mut)
        self.save_state()
        self._log(f"[OK] World profile deleted: {clean_name}")

    def _clean_profile_name(self, name: str) -> str:
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValidationError("Enter a world profile name.")
        return clean_name

    def _standard_world_settings(self) -> dict:
        return {
            "WorldName": "NewWorld",
            "Seed": "",
            "worldWidth": 1024000,
            "worldLength": 1024000,
            "MapSizeY": 256,
            "polarEquatorDistance": 100000,
            "landcover": 0.975,
            "oceanscale": 5.0,
            "upheavelCommonness": 0.30,
            "geologicActivity": 0.05,
            "landformScale": 1.0,
            "worldClimate": "realistic",
            "worldEdge": "traversable",
            "globalTemperature": 1.0,
            "globalPrecipitation": 1.0,
            "globalForestation": 0.0,
            "globalDepositSpawnRate": 1.0,
            "surfaceCopperDeposits": 0.12,
            "surfaceTinDeposits": 0.007,
            "snowAccum": True,
            "gameMode": "survival",
            "startingClimate": "temperate",
            "spawnRadius": 50,
            "graceTimer": 0,
            "deathPunishment": "drop",
            "droppedItemsTimer": 600,
            "seasons": "enabled",
            "playerlives": -1,
            "playerHungerSpeed": 1.0,
            "creatureHostility": "aggressive",
            "creatureStrength": 1.0,
            "playerHealthPoints": 15.0,
            "blockGravity": "sandgravel",
            "caveIns": "off",
            "microblockChiseling": "stonewood",
            "classExclusiveRecipes": True,
            "toolDurability": 1.0,
            "toolMiningSpeed": 1.0,
            "propickNodeSearchRadius": 6,
            "allowMap": True,
            "allowCoordinateHud": True,
            "temporalStability": True,
            "temporalStorms": "sometimes",
            "tempstormDurationMul": 1.0,
            "temporalRifts": "visible",
            "temporalGearRespawnUses": 20,
            "temporalStormSleeping": 0,
            "ExtraConfig": {},
        }

    def prepare_world_generation(self, new_settings: Optional[dict] = None) -> Path:
        """Creates the data folder layout and applies active mods before first server start."""
        self._require_no_map_generation("prepare world generation")
        self._require_server_stopped("prepare world generation")
        data_root = self._require_data_path()
        self._ensure_server_data_layout(data_root)

        if new_settings is not None:
            self.update_world_settings(new_settings)
        elif self.get_state().active_mods:
            self.apply_active_mods_to_server()

        self._log(f"[OK] World data prepared: {data_root}")
        return data_root

    def create_server_world(self, new_settings: dict, *, start_after_create: bool = False) -> dict:
        """Creates a managed local server world under project-root/servers."""
        self._require_no_map_generation("create a server world")
        self._require_server_stopped("create a server world")
        validate_world_gen_settings(new_settings)

        world_name = (new_settings.get("WorldName") or "NewWorld").strip() or "NewWorld"
        server_id = self._unique_server_id(world_name)
        data_root = self.server_storage_root() / server_id
        self._ensure_server_data_layout(data_root)

        active_mods = self.get_state().active_mods
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        info = self._server_info(server_id, world_name, data_root, new_settings, created_at=created_at)

        def mut(s: AppState) -> AppState:
            servers = dict(s.servers)
            servers[server_id] = info
            return replace(
                s,
                world_settings=new_settings,
                data_path=str(data_root),
                selected_server_id=server_id,
                servers=servers,
            )

        self.update_state(mut)
        self.save_state()

        if active_mods:
            try:
                copied = self.apply_active_mods_to_server()
                info["active_mods"] = list(active_mods)
                info["mods_applied_count"] = copied
            except ValidationError as e:
                self._log(f"[WARN] Server world created, but active mods were not applied: {e}")

        self._write_world_generation_server_config(data_root, new_settings, self.get_state().port)
        self._write_server_marker(info)
        self._log(f"[OK] Created server world '{world_name}' at {data_root}")

        if start_after_create:
            try:
                self.start_server()
                info["start_requested"] = True
                self._log("[OK] Server start requested for world generation.")
            except ValidationError as e:
                info["start_requested"] = False
                info["start_blocked_reason"] = str(e)
                self._log(f"[WARN] Server world prepared, but it was not started: {e}")

        return info

    def generate_map(self, new_settings: dict, *, start_after_create: bool = True) -> dict:
        """
        Prepares a managed server for map generation and starts it.

        If the selected or same-name managed server has no active Saves content, it
        is reused. Existing active maps must be reset or deleted explicitly first.
        """
        self._require_server_stopped("generate a map")
        self._require_no_map_generation("generate another map")
        validate_world_gen_settings(new_settings)
        self.discover_server_worlds()

        world_name = (new_settings.get("WorldName") or "NewWorld").strip() or "NewWorld"
        target = self._find_generation_target(world_name)
        if target is None:
            return self.create_server_world(new_settings, start_after_create=start_after_create)

        server_id = str(target["id"])
        data_root = Path(target["data_path"]).expanduser().resolve()
        if self._server_has_active_map(data_root):
            raise ValidationError(
                "This server already has an active map. Use Reset Map or Delete Map first, "
                "or change the World Name to create a separate server."
            )

        self._ensure_server_data_layout(data_root)

        port = int(target.get("port") or self.get_state().port)
        info = self._server_info(server_id, world_name, data_root, new_settings, port=port)

        def mut(s: AppState) -> AppState:
            servers = dict(s.servers)
            servers[server_id] = info
            return replace(
                s,
                world_settings=new_settings,
                data_path=str(data_root),
                selected_server_id=server_id,
                port=port,
                servers=servers,
            )

        self.update_state(mut)
        self.save_state()

        if self.get_state().active_mods:
            try:
                copied = self.apply_active_mods_to_server()
                info["active_mods"] = list(self.get_state().active_mods)
                info["mods_applied_count"] = copied
            except ValidationError as e:
                self._log(f"[WARN] Map generation prepared, but active mods were not applied: {e}")

        self._write_world_generation_server_config(data_root, new_settings, port)
        self._write_server_marker(info)
        self._log(f"[OK] Map generation prepared for '{world_name}' at {data_root}")

        if start_after_create:
            try:
                self.start_server()
                info["start_requested"] = True
                self._log("[OK] Server start requested for map generation.")
            except ValidationError as e:
                info["start_requested"] = False
                info["start_blocked_reason"] = str(e)
                self._log(f"[WARN] Map generation prepared, but the server was not started: {e}")

        return self._server_info_for_display(info)

    def reset_world_map_keep_players(self) -> Optional[Path]:
        """
        Archives Saves for a fresh map while keeping top-level server/player files.

        Vintage Story player inventory/world position is typically save-bound, so this
        does not promise inventory preservation.
        """
        self._require_no_map_generation("reset the map")
        self._require_server_stopped("reset the map")
        data_root = self._require_existing_data_path()
        saves_dir = data_root / "Saves"
        archived = self._archive_path_if_exists(saves_dir, "reset")
        self._ensure_server_data_layout(data_root)

        if archived:
            self._log(f"[OK] Map reset. Previous Saves archived as: {archived}")
        else:
            self._log("[OK] Map reset requested. No existing Saves folder was found.")
        return archived

    def delete_world_map(self) -> Optional[Path]:
        """Archives the Saves folder without recreating any world files."""
        self._require_no_map_generation("delete the map")
        self._require_server_stopped("delete the map")
        data_root = self._require_existing_data_path()
        archived = self._archive_path_if_exists(data_root / "Saves", "deleted")
        if archived:
            self._log(f"[OK] Map deleted. Previous Saves archived as: {archived}")
        else:
            self._log("[OK] Delete map requested. No existing Saves folder was found.")
        return archived

    def full_server_wipe(self) -> Optional[Path]:
        """Archives the entire data folder and recreates an empty one."""
        self._require_no_map_generation("wipe the server")
        self._require_server_stopped("wipe the server")
        state = self.get_state()
        data_root = self._require_data_path()

        if not data_root.exists():
            self._ensure_server_data_layout(data_root)
            self._rewrite_selected_server_marker_if_needed(state, data_root)
            self._log(f"[OK] Server data folder created empty: {data_root}")
            return None

        archive_path = self._archive_destination(data_root, "wipe")
        shutil.move(str(data_root), str(archive_path))
        self._ensure_server_data_layout(data_root)
        self._rewrite_selected_server_marker_if_needed(state, data_root)
        self._log(f"[OK] Full server wipe completed. Previous data archived as: {archive_path}")
        return archive_path

    def delete_server_world(self, server_id: Optional[str] = None) -> Optional[Path]:
        """
        Removes a server from the managed list.

        Project-local managed server folders are archived outside the live servers
        directory so discovery will not immediately add them back.
        """
        self._require_no_map_generation("delete the server")
        self._require_server_stopped("delete the server")
        self.discover_server_worlds()

        state = self.get_state()
        target_id = server_id or state.selected_server_id
        if not target_id:
            raise ValidationError("Select a server world first.")

        info = state.servers.get(target_id)
        if not info:
            raise ValidationError(f"Server world not found: {target_id}")

        data_root = Path(info.get("data_path", "")).expanduser().resolve()
        storage_root = self.server_storage_root().resolve()
        archived = None

        if data_root.exists() and self._path_is_relative_to(data_root, storage_root):
            archive_path = self._server_archive_destination(data_root, "deleted")
            shutil.move(str(data_root), str(archive_path))
            archived = archive_path
        elif data_root.exists():
            self._log(f"[WARN] Server path is outside local storage; unregistering only: {data_root}")

        remaining = dict(state.servers)
        remaining.pop(target_id, None)
        next_id = self._next_server_id(remaining)
        next_info = remaining.get(next_id, {}) if next_id else {}

        def mut(s: AppState) -> AppState:
            return replace(
                s,
                servers=remaining,
                selected_server_id=next_id,
                data_path=str(next_info.get("data_path", "")),
                port=int(next_info.get("port") or s.port),
            )

        self.update_state(mut)
        self.save_state()

        if archived:
            self._log(f"[OK] Deleted server '{info.get('name', target_id)}'. Archived as: {archived}")
        else:
            self._log(f"[OK] Removed server '{info.get('name', target_id)}' from the managed list.")
        return archived

    def _require_server_stopped(self, action: str) -> None:
        if self._server.is_running():
            raise ValidationError(f"Stop the server before you {action}.")

    def _require_no_map_generation(self, action: str) -> None:
        status = self.map_generation_status()
        if status["in_progress"]:
            name = status.get("server_name") or status.get("server_id") or "the selected server"
            raise ValidationError(f"Map generation is in progress for {name}. Wait for it to finish before you {action}.")

    def _mark_map_generation_started_if_needed(self) -> None:
        state = self.get_state()
        info = state.servers.get(state.selected_server_id)
        if not info or not info.get("data_path"):
            return

        data_root = Path(str(info["data_path"])).expanduser().resolve()
        if self._server_has_active_map(data_root):
            return
        if not self._server_is_prepared_for_generation(data_root):
            return

        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.update_state(lambda s: replace(
            s,
            map_generation_in_progress=True,
            map_generation_server_id=str(info.get("id") or state.selected_server_id),
            map_generation_started_at=started_at,
        ))
        self.save_state()
        self._log(f"[INFO] Map generation started for {info.get('name') or info.get('id')}.")

    def _observe_map_generation_output(self, line: str) -> None:
        state = self.get_state()
        if not state.map_generation_in_progress:
            return

        text = line.lower()
        if "fatal" in text or "killing server" in text:
            self._finish_map_generation("failed", f"Map generation failed for {self._generation_server_name()}. Check the server log for details.")
            return

        ready_markers = (
            "entering runphase run",
            "entering runphase rungame",
            "server startup complete",
            "server now running",
            "server started",
        )
        if any(marker in text for marker in ready_markers) and self._generation_has_active_map():
            self._finish_map_generation("completed", f"Map generation completed for {self._generation_server_name()}.")

    def _finalize_generation_if_process_stopped(self) -> None:
        state = self.get_state()
        if not state.map_generation_in_progress or self._server.is_running():
            return

        if self._generation_has_active_map():
            self._finish_map_generation("completed", f"Map generation completed for {self._generation_server_name()}.")
        else:
            self._finish_map_generation("failed", f"Map generation stopped before an active map was detected for {self._generation_server_name()}.")

    def _finalize_generation_if_ready_without_marker(self) -> None:
        state = self.get_state()
        if not state.map_generation_in_progress or not self._server.is_running():
            return
        if self._generation_has_active_map() and PortChecker.is_port_listening(state.port):
            self._finish_map_generation("completed", f"Map generation completed for {self._generation_server_name()}.")

    def _finish_map_generation(self, status: str, message: str) -> None:
        state = self.get_state()
        if not state.map_generation_in_progress:
            return

        notice = {
            "status": status,
            "message": message,
            "server_id": state.map_generation_server_id,
            "server_name": self._generation_server_name(),
            "started_at": state.map_generation_started_at,
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.update_state(lambda s: replace(
            s,
            map_generation_in_progress=False,
            map_generation_server_id="",
            map_generation_started_at="",
        ))
        self.save_state()
        self._pending_generation_notice = notice
        level = "[OK]" if status == "completed" else "[WARN]"
        self._log(f"{level} {message}")

    def _generation_server_name(self) -> str:
        state = self.get_state()
        info = state.servers.get(state.map_generation_server_id, {})
        return str(info.get("name") or state.map_generation_server_id or "selected server")

    def _generation_has_active_map(self) -> bool:
        state = self.get_state()
        info = state.servers.get(state.map_generation_server_id)
        if not info or not info.get("data_path"):
            return False
        return self._server_has_active_map(Path(str(info["data_path"])).expanduser().resolve())

    def _require_data_path(self) -> Path:
        self._sync_selected_server_state()
        state = self.get_state()
        if not state.data_path:
            raise ValidationError("Select or generate a server world first.")
        return Path(state.data_path).expanduser().resolve()

    def _require_existing_data_path(self) -> Path:
        data_root = self._require_data_path()
        if not data_root.exists():
            raise ValidationError(f"Data Path does not exist: {data_root}")
        return data_root

    def _archive_path_if_exists(self, path: Path, reason: str) -> Optional[Path]:
        if not path.exists():
            return None
        archive_path = self._archive_destination(path, reason)
        shutil.move(str(path), str(archive_path))
        return archive_path

    def _archive_destination(self, path: Path, reason: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = path.with_name(f"{path.name}.{reason}_{timestamp}")
        counter = 1
        while destination.exists():
            destination = path.with_name(f"{path.name}.{reason}_{timestamp}_{counter}")
            counter += 1
        return destination

    def _server_archive_destination(self, data_root: Path, reason: str) -> Path:
        archive_root = self._project_root() / "server_archives"
        archive_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = archive_root / f"{data_root.name}.{reason}_{timestamp}"
        counter = 1
        while destination.exists():
            destination = archive_root / f"{data_root.name}.{reason}_{timestamp}_{counter}"
            counter += 1
        return destination

    def _server_info(
        self,
        server_id: str,
        name: str,
        data_root: Path,
        world_settings: dict,
        *,
        created_at: Optional[str] = None,
        port: Optional[int] = None,
    ) -> dict:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        existing = self.get_state().servers.get(server_id, {})
        return {
            **existing,
            "id": server_id,
            "name": name,
            "data_path": str(data_root.resolve()),
            "port": port if port is not None else self.get_state().port,
            "world_settings": dict(world_settings),
            "active_mods": list(self.get_state().active_mods),
            "created_at": created_at or existing.get("created_at") or now,
            "updated_at": now,
        }

    def _server_info_for_display(self, info: dict) -> dict:
        data_path = str(info.get("data_path") or "")
        enriched = dict(info)
        enriched["map_status"] = self._server_map_status(Path(data_path).expanduser()) if data_path else "Missing"
        return enriched

    def _ensure_server_data_layout(self, data_root: Path) -> None:
        """Create the standard folders expected under a Vintage Story data root."""
        data_root.mkdir(parents=True, exist_ok=True)
        for folder in ("Mods", "Saves", "Cache", "Logs"):
            (data_root / folder).mkdir(parents=True, exist_ok=True)

    def _sync_selected_server_state(self, servers: Optional[dict] = None) -> bool:
        state = self.get_state()
        servers = dict(servers if servers is not None else state.servers)
        if not servers:
            return False

        selected_id = state.selected_server_id if state.selected_server_id in servers else ""
        if not selected_id and state.data_path:
            current_data = Path(state.data_path).expanduser().resolve()
            for server_id, info in servers.items():
                raw_path = str(info.get("data_path") or "")
                if raw_path and Path(raw_path).expanduser().resolve() == current_data:
                    selected_id = server_id
                    break

        if not selected_id:
            selected_id = self._next_server_id(servers)

        info = servers.get(selected_id)
        if not info:
            return False

        data_path = str(Path(str(info.get("data_path") or "")).expanduser().resolve()) if info.get("data_path") else state.data_path
        port = int(info.get("port") or state.port)
        if (
            state.selected_server_id == selected_id
            and state.data_path == data_path
            and int(state.port) == port
        ):
            return False

        self.update_state(lambda s: replace(
            s,
            selected_server_id=selected_id,
            data_path=data_path,
            port=port,
        ))
        return True

    def _write_world_generation_server_config(self, data_root: Path, settings: dict, port: int) -> None:
        config_path = data_root / SERVER_CONFIG_FILENAME
        config = {}
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception as e:
                self._log(f"[WARN] Could not read existing {SERVER_CONFIG_FILENAME}; rewriting world generation fields: {e}")

        width = int(settings.get("worldWidth") or settings.get("WorldWidth") or 1024000)
        length = int(settings.get("worldLength") or settings.get("WorldLength") or width)
        height = int(settings.get("MapSizeY") or settings.get("WorldHeight") or 256)
        world_name = (settings.get("WorldName") or "NewWorld").strip() or "NewWorld"

        config["Port"] = int(port)
        config["MapSizeX"] = width
        config["MapSizeY"] = height
        config["MapSizeZ"] = length
        config.setdefault("ModPaths", ["Mods"])
        config.setdefault("ConfigVersion", "1.10")
        config.setdefault("ServerName", "Vintage Story Server")
        config.setdefault("WelcomeMessage", "Welcome {0}, may you survive well and prosper")
        config.setdefault("AdvertiseServer", False)
        config.setdefault("MaxClients", 16)
        config.setdefault("ServerLanguage", "en")
        config.setdefault("DefaultRoleCode", "suplayer")
        self._ensure_default_server_roles(config)

        world_config = dict(config.get("WorldConfig") or {})
        world_config["Seed"] = settings.get("Seed") or None
        world_config["SaveFileLocation"] = str((data_root / "Saves" / "default.vcdbs").resolve())
        world_config["WorldName"] = world_name
        world_config["PlayStyle"] = settings.get("PlayStyle", world_config.get("PlayStyle", "surviveandbuild"))
        world_config["PlayStyleLangCode"] = settings.get(
            "PlayStyleLangCode",
            world_config.get("PlayStyleLangCode", "preset-surviveandbuild"),
        )
        world_config["WorldType"] = settings.get("WorldType", world_config.get("WorldType", "standard"))
        world_config["MapSizeY"] = height

        generated = dict(world_config.get("WorldConfiguration") or {})
        for key in self._worldconfig_keys():
            if key in settings:
                generated[key] = self._format_worldconfig_value(settings[key])

        world_config["WorldConfiguration"] = generated
        config["WorldConfig"] = world_config

        data_root.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        self._log(f"[OK] Wrote world generation config: {config_path}")

    def _ensure_default_server_roles(self, config: dict) -> None:
        roles = config.get("Roles")
        if not isinstance(roles, list):
            roles = []

        by_code = {
            str(role.get("Code")): role
            for role in roles
            if isinstance(role, dict) and role.get("Code")
        }
        by_code.setdefault("suplayer", self._default_survival_player_role())
        by_code.setdefault("admin", self._default_admin_role())
        config["Roles"] = list(by_code.values())

    def _repair_server_config_for_start(self, data_root: Path) -> None:
        config_path = data_root / SERVER_CONFIG_FILENAME
        if not config_path.is_file():
            return

        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as e:
            self._log(f"[WARN] Could not inspect {SERVER_CONFIG_FILENAME} before start: {e}")
            return

        before = json.dumps(config, sort_keys=True)
        config.setdefault("DefaultRoleCode", "suplayer")
        self._ensure_default_server_roles(config)

        if json.dumps(config, sort_keys=True) == before:
            return

        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        self._log(f"[OK] Repaired server roles in {config_path}")

    def _default_survival_player_role(self) -> dict:
        return {
            "Code": "suplayer",
            "PrivilegeLevel": 0,
            "Name": "Survival Player",
            "Description": "Can use/place/break blocks in unprotected areas, create/manage player groups and chat.",
            "DefaultSpawn": None,
            "ForcedSpawn": None,
            "Privileges": [
                "controlplayergroups",
                "manageplayergroups",
                "chat",
                "areamodify",
                "build",
                "useblock",
                "attackcreatures",
                "attackplayers",
                "selfkill",
            ],
            "RuntimePrivileges": [],
            "DefaultGameMode": 1,
            "Color": "White",
            "LandClaimAllowance": 262144,
            "LandClaimMinSize": {"X": 5, "Y": 5, "Z": 5},
            "LandClaimMaxAreas": 3,
            "AutoGrant": False,
        }

    def _default_admin_role(self) -> dict:
        return {
            "Code": "admin",
            "PrivilegeLevel": 99999,
            "Name": "Admin",
            "Description": "Has all privileges, including giving other players admin status.",
            "DefaultSpawn": None,
            "ForcedSpawn": None,
            "Privileges": [
                "build",
                "useblock",
                "buildblockseverywhere",
                "useblockseverywhere",
                "attackplayers",
                "attackcreatures",
                "freemove",
                "gamemode",
                "pickingrange",
                "chat",
                "kick",
                "ban",
                "whitelist",
                "setwelcome",
                "announce",
                "readlists",
                "give",
                "areamodify",
                "setspawn",
                "controlserver",
                "tp",
                "time",
                "grantrevoke",
                "root",
                "commandplayer",
                "controlplayergroups",
                "manageplayergroups",
                "selfkill",
                "manageotherplayergroups",
            ],
            "RuntimePrivileges": [],
            "DefaultGameMode": 1,
            "Color": "LightBlue",
            "LandClaimAllowance": 2147483647,
            "LandClaimMinSize": {"X": 5, "Y": 5, "Z": 5},
            "LandClaimMaxAreas": 99999,
            "AutoGrant": True,
        }

    def _worldconfig_keys(self) -> tuple[str, ...]:
        return (
            "gameMode",
            "startingClimate",
            "spawnRadius",
            "graceTimer",
            "deathPunishment",
            "droppedItemsTimer",
            "seasons",
            "playerlives",
            "blockGravity",
            "caveIns",
            "creatureHostility",
            "creatureStrength",
            "playerHealthPoints",
            "playerHungerSpeed",
            "toolDurability",
            "toolMiningSpeed",
            "propickNodeSearchRadius",
            "microblockChiseling",
            "allowMap",
            "allowCoordinateHud",
            "loreContent",
            "temporalStability",
            "temporalStorms",
            "tempstormDurationMul",
            "temporalRifts",
            "temporalGearRespawnUses",
            "temporalStormSleeping",
            "worldClimate",
            "landcover",
            "oceanscale",
            "upheavelCommonness",
            "geologicActivity",
            "landformScale",
            "worldWidth",
            "worldLength",
            "worldEdge",
            "polarEquatorDistance",
            "globalTemperature",
            "globalPrecipitation",
            "globalForestation",
            "globalDepositSpawnRate",
            "surfaceCopperDeposits",
            "surfaceTinDeposits",
            "snowAccum",
            "classExclusiveRecipes",
            "allowLandClaiming",
        )

    def _format_worldconfig_value(self, value: Any) -> Any:
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        return str(value)

    def _server_map_status(self, data_root: Path) -> str:
        if not data_root.exists():
            return "Missing"
        if self._server_has_active_map(data_root):
            return "Active"
        if any(data_root.glob("Saves.deleted_*")):
            return "Deleted"
        if any(data_root.glob("Saves.reset_*")):
            return "Reset"
        return "No Map"

    def _server_has_active_map(self, data_root: Path) -> bool:
        saves_dir = data_root / "Saves"
        if not saves_dir.is_dir():
            return False
        try:
            next(saves_dir.iterdir())
            return True
        except StopIteration:
            return False

    def _server_is_prepared_for_generation(self, data_root: Path) -> bool:
        return (data_root / SERVER_CONFIG_FILENAME).is_file()

    def _find_generation_target(self, world_name: str) -> Optional[dict]:
        state = self.get_state()
        selected = state.servers.get(state.selected_server_id)
        if selected and self._server_matches_world_name(selected, world_name):
            return selected

        matches = [
            info for info in state.servers.values()
            if self._server_matches_world_name(info, world_name)
        ]
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]

        reusable = [
            info for info in matches
            if info.get("data_path")
            and not self._server_has_active_map(Path(info["data_path"]).expanduser().resolve())
        ]
        if len(reusable) == 1:
            return reusable[0]

        raise ValidationError(
            f"Multiple managed servers are named '{world_name}'. Select the exact server in the Server tab first."
        )

    def _server_matches_world_name(self, info: dict, world_name: str) -> bool:
        expected_id = self._safe_server_id(world_name).lower()
        actual_id = str(info.get("id") or "").lower()
        actual_name = str(info.get("name") or "").strip().lower()
        return actual_name == world_name.strip().lower() or actual_id == expected_id

    def _next_server_id(self, servers: dict) -> str:
        if not servers:
            return ""
        ordered = sorted(
            servers.values(),
            key=lambda item: (
                str(item.get("name") or item.get("id") or "").lower(),
                str(item.get("id") or "").lower(),
            ),
        )
        return str(ordered[0].get("id") or "")

    def _path_is_relative_to(self, path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

    def _write_server_marker(self, info: dict) -> None:
        data_path = Path(info["data_path"]).expanduser().resolve()
        data_path.mkdir(parents=True, exist_ok=True)
        marker = data_path / ".vs_manager_server.json"
        marker.write_text(json.dumps(info, indent=2), encoding="utf-8")

    def _rewrite_selected_server_marker_if_needed(self, state: AppState, data_root: Path) -> None:
        info = state.servers.get(state.selected_server_id)
        if not info:
            return
        if Path(info.get("data_path", "")).expanduser().resolve() != data_root:
            return
        updated = {**info, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        self._write_server_marker(updated)

    def _unique_server_id(self, name: str, preferred: Optional[str] = None) -> str:
        base = self._safe_server_id(preferred or name)
        used_ids = set(self.get_state().servers.keys())
        used_dirs = {item.name.lower() for item in self.server_storage_root().iterdir() if item.is_dir()}
        candidate = base
        counter = 2
        while candidate in used_ids or candidate.lower() in used_dirs:
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def _safe_server_id(self, name: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", (name or "NewWorld").strip()).strip(".-")
        return safe or "NewWorld"

    # -------------------------
    # Network helpers
    # -------------------------

    def is_port_listening_localhost(self, port: Optional[int] = None) -> bool:
        return PortChecker.is_port_listening(port or self.get_state().port)
