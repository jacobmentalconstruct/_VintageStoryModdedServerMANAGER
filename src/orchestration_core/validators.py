from pathlib import Path
from .errors import ValidationError
from src.server_manager_core.models import AppState


def validate_paths_for_start(state: AppState) -> None:
    exe = Path(state.server_exe_path).expanduser()
    data = Path(state.data_path).expanduser()

    if not state.server_exe_path.strip():
        raise ValidationError("server_exe_path is empty.")
    if not exe.exists():
        raise ValidationError(f"Server executable not found: {exe}")
    if not state.data_path.strip():
        raise ValidationError("data_path is empty.")
    if not data.exists():
        raise ValidationError(f"Data path not found: {data}")
    if not (1 <= int(state.port) <= 65535):
        raise ValidationError(f"Port out of range: {state.port}")


def validate_backup_settings(state: AppState) -> None:
    if not state.backup_root.strip():
        raise ValidationError("backup_root is empty.")
    if state.backup_interval_minutes <= 0:
        raise ValidationError("backup_interval_minutes must be > 0.")
    if state.backup_retention_days < 0:
        raise ValidationError("backup_retention_days must be >= 0.")


def validate_world_gen_settings(settings: dict) -> None:
    """Ensures world generation parameters are within sane limits."""
    # Seed validation
    if "seed" in settings:
        try:
            # Vintage Story seeds are usually numeric strings
            str(settings["seed"])
        except (ValueError, TypeError):
            raise ValidationError("World seed must be a valid string or number.")

    # Size validation
    for dim in ["worldWidth", "worldHeight"]:
        if dim in settings:
            val = int(settings[dim])
            if val < 1024 or val > 1000000:
                raise ValidationError(f"{dim} must be between 1,024 and 1,000,000.")

    # Biome/Climate validation
    if "biomeScale" in settings:
        scale = float(settings["biomeScale"])
        if not (0.1 <= scale <= 2.0):
            raise ValidationError("Biome scale must be between 0.1 and 2.0.")