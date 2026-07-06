from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class AppState:
    # [cite_start]Existing Server Paths [cite: 61]
    server_exe_path: str = ""
    data_path: str = ""
    port: int = 42420

    # [cite_start]Existing Backup Settings [cite: 61]
    backup_root: str = ""
    backup_interval_minutes: int = 60
    backup_retention_days: int = 7
    backups_enabled: bool = False

    # New: World Generation Granularity
    # Stores keys like: "seed", "worldWidth", "worldHeight", "mapRegionSize", etc.
    world_settings: Dict[str, Any] = field(default_factory=dict)
    world_profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # New: Mod Management
    # Stores profiles like: {"Hardcore": ["mod1.zip", "mod2.zip"], "Creative": [...]}
    mod_profiles: Dict[str, list] = field(default_factory=dict)
    mod_repository_path: str = ""
    active_mods: list = field(default_factory=list)

    # Local generated server worlds managed by this app.
    servers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    selected_server_id: str = ""

    # Map generation lifecycle.
    map_generation_in_progress: bool = False
    map_generation_server_id: str = ""
    map_generation_started_at: str = ""
    generation_alert_auto_close: bool = False

    # [cite_start]Timestamps [cite: 61]
    last_started_at: str = ""
    last_backup_at: str = ""
