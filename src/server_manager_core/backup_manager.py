import os
import time
import shutil
import zipfile
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


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
    def __init__(self, log_fn):
        self.log = log_fn
        self.can_backup_fn = None  # optional: callable -> bool (True means backups allowed)
        self._stop_event = threading.Event()
        self._thread = None

    def start_scheduler(self, get_state_fn, set_state_fn, can_backup_fn=None):
        if self._thread and self._thread.is_alive():
            return
        self.can_backup_fn = can_backup_fn
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._scheduler_loop,
            args=(get_state_fn, set_state_fn, can_backup_fn),
            daemon=True
        )
        self._thread.start()

    def stop_scheduler(self):
        self._stop_event.set()

    def _scheduler_loop(self, get_state_fn, set_state_fn, can_backup_fn=None):
        while not self._stop_event.is_set():
            state = get_state_fn()
            if state.backups_enabled:
                # Wait in small increments so disabling backups takes effect quickly
                total_sleep = max(1, int(state.backup_interval_minutes * 60))
                slept = 0
                while slept < total_sleep and not self._stop_event.is_set():
                    time.sleep(1)
                    slept += 1
                    # Re-check enabled flag quickly
                    if not get_state_fn().backups_enabled:
                        break

                # If still enabled, do a backup
                if get_state_fn().backups_enabled:
                    try:
                        if can_backup_fn and not can_backup_fn():
                            self.log("[WARN] Backup skipped: server running or backups disallowed right now.")
                        else:
                            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                            state = get_state_fn()
                            backup_root = Path(state.backup_root).expanduser().resolve()
                            backup_root.mkdir(parents=True, exist_ok=True)

                            source_path = Path(state.data_path).expanduser().resolve()
                            if not source_path.exists():
                                self.log(f"[WARN] Backup skipped: data path does not exist: {source_path}")
                            else:
                                filename = f"vs_backup_{ts}.zip"
                                dest_zip = backup_root / filename
                                self._create_zip_backup(source_path, dest_zip)
                                self.log(f"[OK] Backup created: {dest_zip}")

                                # Update last_backup_at
                                state.last_backup_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                set_state_fn(state)

                                # Retention cleanup
                                self._cleanup_retention(backup_root, state.backup_retention_days)

                    except Exception as e:
                        self.log(f"[ERROR] Backup failed: {e}")
            else:
                # Idle sleep
                time.sleep(1)

    def _create_zip_backup(self, source_path: Path, dest_zip: Path):
        # Use ZIP_DEFLATED for a reasonable balance of size/speed
        with zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(source_path):
                rootp = Path(root)
                for f in files:
                    fp = rootp / f
                    rel = fp.relative_to(source_path)
                    zf.write(fp, arcname=str(rel))

    def _cleanup_retention(self, backup_root: Path, retention_days: int):
        # Remove backups older than retention_days (based on file mtime)
        if retention_days <= 0:
            return
        cutoff = time.time() - (retention_days * 86400)
        removed = 0
        for p in backup_root.glob("vs_backup_*.zip"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
                    removed += 1
            except Exception:
                pass
        if removed:
            self.log(f"[OK] Retention cleanup removed {removed} old backup(s).")

    # ------------------------------------------------------------
    # Wave B1: Vault helpers
    # ------------------------------------------------------------

    def list_backups(self, backup_root: Path) -> list[BackupInfo]:
        """Return backups sorted newest-first."""
        backup_root = Path(backup_root).expanduser().resolve()
        if not backup_root.exists():
            return []

        items: list[BackupInfo] = []
        for p in backup_root.glob("vs_backup_*.zip"):
            try:
                st = p.stat()
                items.append(
                    BackupInfo(
                        filename=p.name,
                        path=str(p),
                        size_bytes=int(st.st_size),
                        mtime_epoch=float(st.st_mtime),
                    )
                )
            except Exception:
                continue

        items.sort(key=lambda b: b.mtime_epoch, reverse=True)
        return items

    def restore_backup_zip(
        self,
        zip_path: Path,
        restore_target_dir: Path,
        safety_rename: bool = True,
    ) -> Path:
        """
        Restore a snapshot zip into restore_target_dir.

        Atomic-ish restore strategy:
          1) If restore_target_dir exists and safety_rename=True, rename it to <name>.bak_<timestamp>
          2) Create restore_target_dir fresh
          3) Extract zip into restore_target_dir

        Returns:
          Path to the renamed backup folder if it existed, else Path("")
        """
        zip_path = Path(zip_path).expanduser().resolve()
        restore_target_dir = Path(restore_target_dir).expanduser().resolve()

        if not zip_path.exists():
            raise FileNotFoundError(f"Backup zip not found: {zip_path}")

        renamed_path = Path("")

        if restore_target_dir.exists() and safety_rename:
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            renamed_path = restore_target_dir.with_name(restore_target_dir.name + f".bak_{ts}")
            # Ensure we don't collide
            if renamed_path.exists():
                # extremely unlikely, but keep deterministic
                renamed_path = restore_target_dir.with_name(restore_target_dir.name + f".bak_{ts}_{int(time.time())}")

            self.log(f"[WARN] Renaming current folder to: {renamed_path}")
            restore_target_dir.rename(renamed_path)

        # fresh target
        restore_target_dir.mkdir(parents=True, exist_ok=True)

        self.log(f"[INFO] Restoring backup zip: {zip_path}")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(path=restore_target_dir)

        self.log(f"[OK] Restore complete: {restore_target_dir}")
        return renamed_path

    def open_backup_folder(self, state):
        try:
            p = Path(state.backup_root).expanduser().resolve()
            p.mkdir(parents=True, exist_ok=True)
            # Cross-platform open
            if os.name == "nt":
                os.startfile(str(p))  # type: ignore[attr-defined]
            else:
                # Linux/macOS
                import subprocess
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            self.log(f"[ERROR] Could not open backup folder: {e}")

    def open_data_folder(self, state):
        try:
            p = Path(state.data_path).expanduser().resolve()
            if not p.exists():
                self.log(f"[WARN] Data path does not exist: {p}")
                return
            if os.name == "nt":
                os.startfile(str(p))  # type: ignore[attr-defined]
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            self.log(f"[ERROR] Could not open data folder: {e}")


