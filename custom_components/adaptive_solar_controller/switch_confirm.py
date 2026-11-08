"""Bestätigung von Abschaltbefehlen: Ist der Schalter nach `turn_off` wirklich aus?

Reine Logik ohne Home Assistant. Der Aufrufer meldet gesendete Befehle (`sent`) und
den beobachteten Schalterzustand (`observe`). Es wird nie selbst geschaltet.
"""
from __future__ import annotations

IDLE = "idle"                  # kein offener Abschaltbefehl
CONFIRMED = "confirmed_off"    # Schalter meldet nach unserem Befehl `off`
PENDING = "pending"            # Befehl gesendet, Wartezeit läuft noch
RETRY = "retry"                # Wartezeit abgelaufen, Schalter noch `on`: erneut senden
UNAVAILABLE = "unavailable"    # Schalter meldet keinen gültigen Zustand
_INVALID = (None, "unavailable", "unknown")


class SwitchOffTracker:
    def __init__(self, confirm_after_s: float = 15.0, alert_after_attempts: int = 3) -> None:
        self.confirm_after_s = confirm_after_s
        self.alert_after_attempts = alert_after_attempts
        self.reset()

    def reset(self) -> None:
        self.attempts = 0
        self.last_sent: float | None = None

    @property
    def unconfirmed(self) -> bool:
        """True, wenn nach mehreren Versuchen der Schalter weiter `on` meldet."""
        return self.attempts >= self.alert_after_attempts

    def sent(self, now_s: float) -> None:
        self.attempts += 1
        self.last_sent = now_s

    def observe(self, switch_state: str | None, now_s: float) -> str:
        if self.attempts == 0:
            return IDLE
        if switch_state == "off":
            self.reset()
            return CONFIRMED
        if switch_state in _INVALID:
            return UNAVAILABLE
        if self.last_sent is not None and now_s - self.last_sent < self.confirm_after_s:
            return PENDING
        return RETRY
