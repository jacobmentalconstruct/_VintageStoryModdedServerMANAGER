import shutil
import zipfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

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
        return self.list_mods_in_folder(mods_dir)

    def list_mods_in_folder(self, folder_path: str | Path) -> List[ModInfo]:
        """Scans a folder for mod package files."""
        mods_dir = Path(folder_path).expanduser().resolve()
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

    def copy_mods_to_server(
        self,
        repository_path: str | Path,
        data_path: str | Path,
        mod_filenames: Iterable[str],
    ) -> int:
        """Copies selected repository mods into the server data Mods folder."""
        repository = Path(repository_path).expanduser().resolve()
        target = Path(data_path).expanduser().resolve() / "Mods"

        if not repository.exists():
            self.log(f"[ERROR] Mod repository does not exist: {repository}")
            return 0

        target.mkdir(parents=True, exist_ok=True)
        copied = 0
        for raw_name in mod_filenames:
            filename = Path(str(raw_name)).name
            source = repository / filename
            if not source.exists() or not source.is_file():
                self.log(f"[WARN] Active mod missing from repository: {filename}")
                continue
            if source.suffix.lower() not in {".zip", ".dll"}:
                self.log(f"[WARN] Skipping unsupported mod file: {filename}")
                continue

            shutil.copy2(source, target / filename)
            copied += 1

        self.log(f"[OK] Copied {copied} active mod(s) to server Mods folder.")
        return copied

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
                    if not url or not url.startswith("http"):
                        if "fileid" in rel:
                            url = f"https://mods.vintagestory.at/files/asset/{rel['fileid']}"
                
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

    def create_client_bundle(
        self,
        data_path: str,
        export_root: str,
        profile_name: str,
        mod_filenames: Optional[Iterable[str]] = None,
    ) -> Optional[Path]:
        """Zips selected mods into a single package."""
        mods_source = Path(data_path).expanduser().resolve() / "Mods"
        return self.create_bundle_from_folder(mods_source, export_root, profile_name, mod_filenames)

    def create_bundle_from_folder(
        self,
        mods_source: str | Path,
        export_root: str,
        profile_name: str,
        mod_filenames: Optional[Iterable[str]] = None,
    ) -> Optional[Path]:
        """Zips selected mods from a mod folder into a single package."""
        mods_source = Path(mods_source).expanduser().resolve()
        export_dir = Path(export_root).expanduser().resolve() / "ModExports"
        
        if not mods_source.exists():
            self.log("[ERROR] Cannot bundle mods: Source directory missing.")
            return None

        export_dir.mkdir(parents=True, exist_ok=True)
        safe_profile_name = self._safe_bundle_name(profile_name)
        bundle_path = export_dir / f"VS_ModBundle_{safe_profile_name}.zip"
        bundle_files = self._resolve_bundle_files(mods_source, mod_filenames)

        if not bundle_files:
            self.log("[ERROR] Cannot bundle mods: No matching mod files found.")
            return None

        try:
            with zipfile.ZipFile(bundle_path, 'w', zipfile.ZIP_DEFLATED) as bundle:
                for mod_file in bundle_files:
                    bundle.write(mod_file, arcname=mod_file.name)
            
            self.log(f"[OK] Created client mod bundle with {len(bundle_files)} mods: {bundle_path}")
            return bundle_path
        except Exception as e:
            self.log(f"[ERROR] Failed to create mod bundle: {e}")
            return None

    def _resolve_bundle_files(
        self,
        mods_source: Path,
        mod_filenames: Optional[Iterable[str]],
    ) -> List[Path]:
        allowed_suffixes = {".zip", ".dll"}

        if mod_filenames is None:
            candidates = [
                item
                for item in mods_source.glob("*.*")
                if item.is_file() and item.suffix.lower() in allowed_suffixes
            ]
            return sorted(candidates, key=lambda item: item.name.lower())

        bundle_files = []
        seen_names = set()
        for raw_name in mod_filenames:
            filename = Path(str(raw_name)).name
            if not filename or filename in seen_names:
                continue
            seen_names.add(filename)

            mod_path = mods_source / filename
            if mod_path.suffix.lower() not in allowed_suffixes:
                self.log(f"[WARN] Skipping unsupported mod file: {filename}")
                continue
            if not mod_path.exists() or not mod_path.is_file():
                self.log(f"[WARN] Skipping missing mod file: {filename}")
                continue

            bundle_files.append(mod_path)

        return bundle_files

    def _safe_bundle_name(self, profile_name: str) -> str:
        safe = "".join(
            ch if ch.isalnum() or ch in ("-", "_", ".") else "_"
            for ch in (profile_name or "Custom").strip()
        ).strip("._")
        return safe or "Custom"
