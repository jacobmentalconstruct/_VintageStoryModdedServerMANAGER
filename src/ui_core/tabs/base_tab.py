from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from src.orchestration_core import AppController


class BaseTab(ABC):
    """
    Contract for modular tabs.

    build(parent) -> returns frame
    refresh() -> called periodically by UiApp (optional)
    """

    TAB_ID: str = "base"
    TAB_TITLE: str = "Base"
    ORDER: int = 100

    def __init__(self, controller: AppController, log_fn: Callable[[str], None]):
        self.controller = controller
        self.log = log_fn
        self.frame = None  # assigned by build()

    @abstractmethod
    def build(self, parent):
        raise NotImplementedError

    def on_show(self) -> None:
        """Called when tab becomes visible (optional)."""
        return

    def refresh(self) -> None:
        """Called by UiApp timer (optional)."""
        return

