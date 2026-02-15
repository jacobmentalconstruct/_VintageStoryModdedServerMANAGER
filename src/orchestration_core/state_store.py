from __future__ import annotations
import threading
from copy import deepcopy
from typing import Callable, TypeVar, Generic

T = TypeVar("T")

class StateStore(Generic[T]):
    """
    Thread-safe container for immutable application state.
    Uses RLock to allow re-entrant access if needed.
    """
    def __init__(self, initial_state: T):
        self._state = initial_state
        self._lock = threading.RLock()

    def get_state(self) -> T:
        """Returns a deep copy of the current state to prevent race conditions."""
        with self._lock:
            return deepcopy(self._state)

    def update(self, transform: Callable[[T], T]) -> T:
        """
        Applies a transformation function to the state safely.
        Returns the NEW state.
        """
        with self._lock:
            # Pass a copy to the transform function to ensure isolation
            current = deepcopy(self._state)
            new_state = transform(current)
            self._state = new_state
            return new_state