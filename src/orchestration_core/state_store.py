from __future__ import annotations

import threading
from copy import deepcopy
from typing import Callable

from src.server_manager_core.models import AppState


class StateStore:
    """
    Holds the live AppState + provides thread-safe get/set/update.
    - UI and background threads (backup scheduler / server output pump) may both touch state.
    - We store a private copy; get() returns a deepcopy so callers can't mutate without set/update.
    """

    def __init__(self, initial: AppState | None = None):
        self._lock = threading.RLock()
        self._state = initial if initial is not None else AppState()

    def get(self) -> AppState:
        with self._lock:
            return deepcopy(self._state)

    def set(self, new_state: AppState) -> None:
        with self._lock:
            self._state = deepcopy(new_state)

    def update(self, fn: Callable[[AppState], AppState]) -> AppState:
        """
        Apply fn to a mutable copy of state, store the result, return stored copy.
        """
        with self._lock:
            draft = deepcopy(self._state)
            updated = fn(draft)
            self._state = deepcopy(updated)
            return deepcopy(self._state)

