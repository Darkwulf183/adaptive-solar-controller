"""Besitzmarke der FULL-Sperre: Abgleich, wenn sich der konfigurierte Schalter geändert hat."""
from __future__ import annotations

SAME = "same"                      # Marke passt zum konfigurierten Schalter
NOT_OWNED = "not_owned"            # ASC besitzt keine Sperre
ADOPTED = "owner_switch_adopted"   # neuer Schalter ist bereits aus: als eigene Sperre übernommen
RELEASED = "stale_owner_released"  # neuer Schalter ist an: alte Marke verworfen, Sperre wird neu gesetzt
PENDING = "owner_switch_pending"   # neuer Schalter nicht verfügbar: abwarten


def reconcile_lock_owner(owned: bool, stored_entity: str, configured_entity: str,
                         configured_state: str | None) -> tuple[str, bool, str]:
    """Liefert (Ergebnis, neues owned, neue Entität).

    Es wird nie ein Schalter bedient. Nur die gespeicherte Marke wird dem
    aktuell konfigurierten Schalter angepasst.
    """
    if not owned:
        return NOT_OWNED, False, stored_entity or ""
    if (stored_entity or "") == configured_entity:
        return SAME, True, stored_entity
    if configured_state == "off":
        return ADOPTED, True, configured_entity
    if configured_state == "on":
        return RELEASED, False, ""
    return PENDING, True, stored_entity or ""
