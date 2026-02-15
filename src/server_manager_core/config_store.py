import json
from dataclasses import asdict
from pathlib import Path

from .models import AppState


class ConfigStore:
    def __init__(self, config_path: Path):
        self.config_path = config_path

    def load(self) -> AppState:
        if not self.config_path.exists():
            return AppState()
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            return AppState(**data)
        except Exception:
            # If config is corrupt, fall back safely
            return AppState()

    def save(self, state: AppState) -> None:
        self.config_path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")

