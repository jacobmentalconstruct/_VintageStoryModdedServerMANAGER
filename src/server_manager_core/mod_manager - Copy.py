import shutil
import zipfile
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ModInfo:
    filename: str
    path: str
    size_bytes: int
    side: str = "Unknown"  # 'Client', 'Server', 'Both'
    is_enabled: bool = True
    # For online mods
    modid: int = 0
    download_url: str = ""
    tags: List[str] = field(default_factory=list)

class ModManager:
    def __init__(self, log_fn):
        self.log = log_fn

    def list_available_mods(self, data_path: str) -> List[ModInfo]:
        """Scans the /Mods folder in the Vintage Story data directory."""
        mods_dir = Path(data_path).expanduser().resolve() / "Mods"
        if not mods_dir.exists():
            return []

        mod_list = []
        for item in mods_dir.glob("*.*"):
            if item.suffix.lower() in [".zip", ".dll"]:
                mod_list.append(ModInfo(
                    filename=item.name,
                    path=str(item),
                    size_bytes=item.stat().st_size,
                    side="Local" 
                ))
        
        return sorted(mod_list, key=lambda x: x.filename.lower())

    def parse_api_response(self, json_data: dict) -> List[ModInfo]:
        """Converts raw API JSON into ModInfo objects."""
        if not json_data or "mods" not in json_data:
            self.log("[MOD-ERR] API response missing 'mods' key.")
            return []
        
        raw_mods = json_data["mods"]
        results = []
        
        for m in raw_mods:
            try:
                # Basic Fields
                name = m.get("name", "Unknown Mod")
                modid = m.get("modid", 0)
                
                # Side Logic
                raw_side = m.get("side", "both")
                side_str = str(raw_side).title() if raw_side else "Both"

                # Tags / Categories Extraction
                tags_raw = m.get("tags", [])
                if isinstance(tags_raw, str):
                    tags = [t.strip().lower() for t in tags_raw.split(",")]
                elif isinstance(tags_raw, list):
                    tags = [str(t).strip().lower() for t in tags_raw]
                else:
                    tags = []

                # URL Logic
                url = ""
                if "lastrelease" in m and m["lastrelease"]:
                    rel = m["lastrelease"]
                    url = rel.get("mainfile", "")
                    if not url and "fileid" in rel:
                        url = f"https://mods.vintagestory.at/files/asset/{rel['fileid']}"
                
                # Add to results
                results.append(ModInfo(
                    filename=name,
                    path="",
                    size_bytes=0,
                    side=side_str,
                    modid=modid,
                    download_url=url,
                    tags=tags
                ))

            except Exception:
                continue
                
        self.log(f"[MOD] Successfully parsed {len(results)} items.")
        return sorted(results, key=lambda x: x.filename)

    def create_client_bundle(self, data_path: str, export_root: str, profile_name: str) -> Optional[Path]:
        """Zips mods into a single package."""
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