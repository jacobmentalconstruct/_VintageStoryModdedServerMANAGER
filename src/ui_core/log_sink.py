from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List
import threading


@dataclass
class LogLine:
    text: str


class LogSink:
    """
    Thread-safe log buffer.
    - Controller and background threads can call .write()
    - UI drains with .drain()
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._lines: List[LogLine] = []

    def write(self, text: str) -> None:
        with self._lock:
            self._lines.append(LogLine(text=str(text)))

    def drain(self, max_lines: int = 500) -> List[str]:
        with self._lock:
            if not self._lines:
                return []
            take = self._lines[:max_lines]
            self._lines = self._lines[max_lines:]
        return [l.text for l in take]

