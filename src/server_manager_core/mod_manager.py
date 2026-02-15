import os
import shutil
import zipfile
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class ModInfo:
    filename: str
    path: str
    size_bytes: int
    is_enabled: bool = True

class ModManager:
    def __init__(self, log_fn):
        self.log = log_fn

    def list_available_mods(self, data_path: str) -> List[ModInfo]:
        """Scans the /Mods folder in the Vintage Story data directory."""
        mods_dir = Path(data_path).expanduser().resolve() / "Mods"
        if not mods_dir.exists():
            self.log(f"[WARN] Mods directory not found at: {mods_dir}")
            return []

        mod_list = []
        # Vintage Story mods are typically .zip or .dll files
        for item in mods_dir.glob("*.*"):
            if item.suffix.lower() in [".zip", ".dll"]:
                mod_list.append(ModInfo(
                    filename=item.name,
                    path=str(item),
                    size_bytes=item.stat().st_size
                ))
        
        # Sort alphabetically for the UI
        return sorted(mod_list, key=lambda x: x.filename.lower())

    def create_client_bundle(self, data_path: str, export_root: str, profile_name: str) -> Optional[Path]:
        """
        Zips all current mods into a single package for players to download.
        Saves to <backup_root>/ModExports/
        """
        mods_source = Path(data_path).expanduser().resolve() / "Mods"
        export_dir = Path(export_root).expanduser().resolve() / "ModExports"
        
        if not mods_source.exists():
            self.log("[ERROR] Cannot bundle mods: Source directory missing.")
            return None

        export_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = export_dir / f"VS_ModBundle_{profile_name}.zip"

        try:
            with zipfile.ZipFile(bundle_path, 'w', zipfile.ZIP_DEFLATED) as bundle:
                for mod_file in mods_source.glob("*.*"):
                    if mod_file.suffix.lower() in [".zip", ".dll"]:
                        bundle.write(mod_file, arcname=mod_file.name)
            
            self.log(f"[OK] Created client mod bundle: {bundle_path}")
            return bundle_path
        except Exception as e:
            self.log(f"[ERROR] Failed to create mod bundle: {e}")
            return None

    def apply_mod_profile(self, target_data_path: str, profile_mods: List[str], storage_repository: str):
        """
        Future Logic: Copy specific mods from a 'master repository' 
        into the active server 'Mods' folder.
        """
        target_dir = Path(target_data_path).expanduser().resolve() / "Mods"
        repo_dir = Path(storage_repository).expanduser().resolve()
        
        if not repo_dir.exists():
            self.log(f"[ERROR] Mod repository not found: {repo_dir}")
            return

        target_dir.mkdir(parents=True, exist_ok=True)

        for mod_name in profile_mods:
            src = repo_dir / mod_name
            dest = target_dir / mod_name
            if src.exists():
                shutil.copy2(src, dest)
                self.log(f"[INFO] Applied mod: {mod_name}")
            else:
                self.log(f"[WARN] Mod {mod_name} not found in repository.")