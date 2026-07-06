# src/ui_core/tabs/registry.py
from __future__ import annotations

from .base_tab import BaseTab
from .dashboard_tab import DashboardTab
from .server_tab import ServerTab
from .player_tab import PlayerTab
from .world_tab import WorldTab
from .mods_tab import ModsTab
from .backup_tab import BackupsTab

def get_tab_classes() -> list[type[BaseTab]]:
    """Central place to register tabs."""
    tabs: list[type[BaseTab]] = [
        DashboardTab,
        ServerTab,
        PlayerTab,
        WorldTab,
        ModsTab,
        BackupsTab,
    ]

    # Sort by the ORDER attribute defined in each class
    return sorted(tabs, key=lambda t: getattr(t, "ORDER", 100))