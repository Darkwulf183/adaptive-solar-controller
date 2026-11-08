"""Marker für den Flight Recorder: dokumentiert, wann und warum ASC gestartet wurde."""
from __future__ import annotations

from datetime import datetime

REASON_HA_START = "ha_start"          # ASC wurde beim Start von Home Assistant eingerichtet
REASON_SETUP_OR_RELOAD = "setup_or_reload"  # Integration neu geladen, aktualisiert oder neu eingerichtet


def build_start_marker(version: str, ha_is_running: bool, now: datetime) -> str:
    """Eintrag für die Spalte `events`, z. B. ``ASC_START:0.4.6rc4:ha_start@16:12:41``.

    Enthält weder Komma noch Senkrechtstrich, damit die Trennung der Events erhalten bleibt.
    """
    reason = REASON_SETUP_OR_RELOAD if ha_is_running else REASON_HA_START
    return f"ASC_START:{version}:{reason}@{now.strftime('%H:%M:%S')}"
