from pathlib import Path
from .errors import ValidationError
from src.server_manager_core.models import AppState


def validate_paths_for_start(state: AppState) -> None:
    exe = Path(state.server_exe_path).expanduser()
    data = Path(state.data_path).expanduser()

    if not state.server_exe_path.strip():
        raise ValidationError("Set the Vintage Story server executable.")
    if not exe.exists():
        raise ValidationError(f"Server executable not found: {exe}")
    if not state.data_path.strip():
        raise ValidationError("Select or generate a server world.")
    if not data.exists():
        raise ValidationError(f"Server data root not found: {data}")
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
    seed = settings.get("Seed", settings.get("seed"))
    if seed is not None:
        try:
            # Vintage Story seeds are usually numeric strings
            str(seed)
        except (ValueError, TypeError):
            raise ValidationError("World seed must be a valid string or number.")

    # Size validation
    width = settings.get("worldWidth", settings.get("WorldWidth"))
    if width is not None:
        val = int(width)
        if val < 512 or val > 30000000:
            raise ValidationError("worldWidth must be between 512 and 30,000,000.")

    length = settings.get("worldLength", settings.get("WorldLength"))
    if length is not None:
        val = int(length)
        if val < 512 or val > 30000000:
            raise ValidationError("worldLength must be between 512 and 30,000,000.")

    height = settings.get("MapSizeY", settings.get("WorldHeight"))
    if height is not None:
        val = int(height)
        if val < 256 or val > 1024:
            raise ValidationError("MapSizeY must be between 256 and 1,024.")

    landcover = settings.get("landcover")
    if landcover is not None:
        val = float(landcover)
        if not (0 <= val <= 1):
            raise ValidationError("landcover must be between 0 and 1.")

    oceanscale = settings.get("oceanscale")
    if oceanscale is not None:
        val = float(oceanscale)
        if not (0.1 <= val <= 5):
            raise ValidationError("oceanscale must be between 0.1 and 5.")

    upheaval = settings.get("upheavelCommonness")
    if upheaval is not None:
        val = float(upheaval)
        if not (0 <= val <= 1):
            raise ValidationError("upheavelCommonness must be between 0 and 1.")

    geologic = settings.get("geologicActivity")
    if geologic is not None:
        val = float(geologic)
        if not (0 <= val <= 0.4):
            raise ValidationError("geologicActivity must be between 0 and 0.4.")

    landform = settings.get("landformScale")
    if landform is not None:
        val = float(landform)
        if not (0.2 <= val <= 3):
            raise ValidationError("landformScale must be between 0.2 and 3.")

    # Biome/Climate validation
    global_temperature = settings.get("globalTemperature")
    if global_temperature is not None:
        val = float(global_temperature)
        if not (0 <= val <= 5):
            raise ValidationError("globalTemperature must be between 0 and 5.")

    global_precipitation = settings.get("globalPrecipitation")
    if global_precipitation is not None:
        val = float(global_precipitation)
        if not (0 <= val <= 5):
            raise ValidationError("globalPrecipitation must be between 0 and 5.")

    global_forestation = settings.get("globalForestation")
    if global_forestation is not None:
        val = float(global_forestation)
        if not (-1 <= val <= 1):
            raise ValidationError("globalForestation must be between -1 and 1.")

    global_deposits = settings.get("globalDepositSpawnRate", settings.get("GlobalDepositSpawnRate"))
    if global_deposits is not None:
        val = float(global_deposits)
        if not (0 <= val <= 99):
            raise ValidationError("globalDepositSpawnRate must be between 0 and 99.")
