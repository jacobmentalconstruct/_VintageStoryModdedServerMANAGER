import subprocess
import threading
import queue
import time
from typing import Optional, List, Callable

class ServerProcess:
    def __init__(self, log_fn: Callable[[str], None]):
        self._log = log_fn
        self._process: Optional[subprocess.Popen] = None
        self._out_queue: queue.Queue = queue.Queue()
        self._stop_threads = False

    def start(self, exe_path: str, data_path: str, port: int = 42420) -> None:
        if self.is_running():
            return

        cmd = [
            exe_path,
            f"--dataPath={data_path}",
            f"--port={port}"
        ]
        
        self._log(f"[SYS] Launching: {' '.join(cmd)}")
        
        # Launch process with pipes
        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # Line buffered
                creationflags=subprocess.CREATE_NO_WINDOW  # Windows specific: cleaner background run
            )
            
            self._stop_threads = False
            t = threading.Thread(target=self._monitor_output, daemon=True)
            t.start()
            
        except Exception as e:
            self._log(f"[ERROR] Failed to launch server: {e}")
            raise

    def stop_graceful(self) -> None:
        if not self.is_running():
            return
        
        self._log("[SYS] Sending stop command...")
        self.write_stdin("/stop")
        
        # Wait a bit, then kill if needed
        try:
            self._process.wait(timeout=10)
            self._log("[SYS] Server stopped gracefully.")
        except subprocess.TimeoutExpired:
            self._log("[WARN] Server did not stop; forcing kill.")
            self.kill()

    def kill(self) -> None:
        if self._process:
            self._process.kill()
            self._process = None
            self._log("[SYS] Server process killed.")

    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    def write_stdin(self, cmd: str) -> None:
        if self.is_running() and self._process.stdin:
            try:
                self._process.stdin.write(cmd + "\n")
                self._process.stdin.flush()
            except Exception as e:
                self._log(f"[ERROR] Write failed: {e}")

    def read_output_lines(self, max_lines: int = 100) -> List[str]:
        """Drains the output queue up to max_lines."""
        lines = []
        try:
            while len(lines) < max_lines:
                line = self._out_queue.get_nowait()
                lines.append(line)
        except queue.Empty:
            pass
        return lines

    def _monitor_output(self):
        """Background thread to capture stdout."""
        if not self._process or not self._process.stdout:
            return

        try:
            for line in iter(self._process.stdout.readline, ''):
                if self._stop_threads:
                    break
                if line:
                    self._out_queue.put(line.strip())
        except Exception:
            pass
        finally:
            if self._process:
                self._process.stdout.close()