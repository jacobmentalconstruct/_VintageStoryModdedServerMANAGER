import os
import shutil
import zipfile
import threading
import time
import subprocess
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List, Callable, Optional

@dataclass
class BackupInfo:
    filename: str
    path: str
    size_bytes: int
    mtime_epoch: float

    @property
    def mtime_local(self) -> str:
        return datetime.fromtimestamp(self.mtime_epoch).strftime("%Y-%m-%d %H:%M:%S")

    @property
    def size_kib(self) -> float:
        return self.size_bytes / 1024.0

class BackupManager:
    def __init__(self, log_fn: Callable[[str], None]):
        self._log = log_fn
        self._stop_event = threading.Event()
        self._scheduler_thread: Optional[threading.Thread] = None

    def create_backup_zip(self, data_path: Path, backup_root: Path, prefix: str = "Backup") -> Path:
        """Compresses the 'Saves' folder inside data_path to a zip."""
        saves_dir = data_path / "Saves"
        if not saves_dir.exists():
            raise FileNotFoundError(f"Saves directory not found: {saves_dir}")

        if not backup_root.exists():
            backup_root.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        zip_name = f"{prefix}_{timestamp}.zip"
        zip_path = backup_root / zip_name

        self._log(f"[BACKUP] Zipping {saves_dir} -> {zip_path} ...")
        
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(saves_dir):
                for file in files:
                    abs_file = Path(root) / file
                    rel_path = abs_file.relative_to(saves_dir)
                    zf.write(abs_file, arcname=str(rel_path))
        
        return zip_path

    def restore_backup_zip(self, zip_path: Path, target_dir: Path, safety_rename: bool = True) -> Optional[Path]:
        """Extracts a zip to target_dir with safety rename."""
        renamed_path = None
        
        if target_dir.exists() and safety_rename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            renamed_path = target_dir.parent / f"{target_dir.name}.bak_{ts}"
            try:
                target_dir.rename(renamed_path)
            except OSError as e:
                self._log(f"[ERROR] Restore safety move failed: {e}")
                raise

        target_dir.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target_dir)
            
        return renamed_path

    def list_backups(self, backup_root: Path) -> List[BackupInfo]:
        """Returns list of BackupInfo objects."""
        if not backup_root.exists():
            return []
            
        results = []
        for item in backup_root.glob("*.zip"):
            stat = item.stat()
            results.append(BackupInfo(
                filename=item.name,
                path=str(item),
                size_bytes=stat.st_size,
                mtime_epoch=stat.st_mtime
            ))
        
        # Sort newest first
        return sorted(results, key=lambda x: x.mtime_epoch, reverse=True)

    def prune_old_backups(self, backup_root: Path, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
            
        now = time.time()
        cutoff = now - (retention_days * 86400)
        count = 0
        
        for item in backup_root.glob("*.zip"):
            if item.stat().st_mtime < cutoff:
                try:
                    item.unlink()
                    count += 1
                except Exception as e:
                    self._log(f"[WARN] Failed to delete old backup {item.name}: {e}")
        return count

    # ---------------------------------------------------------
    # Scheduler Logic (THE BUG FIX)
    # ---------------------------------------------------------

    def start_scheduler(
        self, 
        interval_minutes_fn: Callable[[], int], 
        is_enabled_fn: Callable[[], bool], 
        on_backup_due: Callable[[], None]
    ) -> None:
        """
        Starts a background thread that checks every minute if a backup is due.
        """
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return

        self._stop_event.clear()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            args=(interval_minutes_fn, is_enabled_fn, on_backup_due),
            daemon=True
        )
        self._scheduler_thread.start()
        self._log("[SYS] Backup scheduler started.")

    def stop_scheduler(self) -> None:
        if self._scheduler_thread:
            self._stop_event.set()
            self._scheduler_thread.join(timeout=2)
            self._scheduler_thread = None
            self._log("[SYS] Backup scheduler stopped.")

    def _scheduler_loop(self, get_interval, get_enabled, callback):
        last_run = time.time()
        
        while not self._stop_event.is_set():
            # Tick every 10 seconds
            if self._stop_event.wait(10):
                break

            if not get_enabled():
                continue

            interval_sec = get_interval() * 60
            if time.time() - last_run >= interval_sec:
                callback() 
                last_run = time.time()

    # ---------------------------------------------------------
    # UI Helpers (RESTORED)
    # ---------------------------------------------------------

    def open_backup_folder(self, state):
        self._open_folder(state.backup_root)

    def open_data_folder(self, state):
        self._open_folder(state.data_path)

    def _open_folder(self, path_str):
        try:
            p = Path(path_str).expanduser().resolve()
            if not p.exists():
                p.mkdir(parents=True, exist_ok=True)
            
            if os.name == "nt":
                os.startfile(str(p))
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            self._log(f"[ERROR] Could not open folder: {e}")