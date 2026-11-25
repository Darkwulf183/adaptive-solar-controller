"""Entities the sidebar panel needs from the config entry (no Home Assistant dependency)."""
from __future__ import annotations

from typing import Any, Mapping

# panel key -> config key
PANEL_SOURCES = {
    "grid": "grid_sensor",
    "target": "target_helper",
    "battery": "battery_voltage_sensor",
    "current": "battery_current_sensor",
    "pv": "pv_sensor",
}


def panel_entities(cfg: Mapping[str, Any]) -> dict[str, str]:
    """Return the user's configured entity ids for the panel; missing ones are empty strings."""
    out: dict[str, str] = {}
    for key, conf_key in PANEL_SOURCES.items():
        value = cfg.get(conf_key)
        out[key] = value if isinstance(value, str) else ""
    return out
