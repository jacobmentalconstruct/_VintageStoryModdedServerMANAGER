import queue
import threading
import subprocess


class ServerProcess:
    def __init__(self, log_fn):
        self.log = log_fn
        self.proc: subprocess.Popen | None = None
        self._out_thread = None
        self._out_queue = queue.Queue()
        self._stop_read = threading.Event()

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, exe_path: str, data_path: str, extra_args=None):
        if self.is_running():
            self.log("[WARN] Server already running.")
            return

        args = [exe_path, "--dataPath", data_path]
        if extra_args:
            args.extend(extra_args)

        self.log(f"[INFO] Starting server: {' '.join(args)}")
        self._stop_read.clear()

        self.proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )

        self._out_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._out_thread.start()

    def _reader_loop(self):
        if not self.proc or not self.proc.stdout:
            return
        for line in self.proc.stdout:
            if self._stop_read.is_set():
                break
            self._out_queue.put(line.rstrip("\n"))
        self._out_queue.put("[INFO] Server output stream ended.")

    def poll_output(self, max_lines: int = 100):
        lines = []
        for _ in range(max_lines):
            try:
                lines.append(self._out_queue.get_nowait())
            except queue.Empty:
                break
        return lines

    def poll_exit(self):
        """Return the process returncode if it has exited, else None."""
        if self.proc is None:
            return None
        return self.proc.poll()

    def send_command(self, cmd: str):
        if not self.is_running():
            self.log("[WARN] Server not running; cannot send command.")
            return
        try:
            assert self.proc is not None
            if self.proc.stdin:
                self.proc.stdin.write(cmd + "\n")
                self.proc.stdin.flush()
        except Exception as e:
            self.log(f"[ERROR] Failed to send command: {e}")

    def stop_graceful(self):
        if not self.is_running():
            return
        self.log("[INFO] Attempting graceful stop...")
        self.send_command("/stop")

    def stop_force(self):
        if not self.is_running():
            return
        self.log("[WARN] Forcing server termination...")
        try:
            assert self.proc is not None
            self.proc.terminate()
        except Exception:
            pass

    def kill(self):
        if not self.is_running():
            return
        try:
            assert self.proc is not None
            self.proc.kill()
        except Exception:
            pass










