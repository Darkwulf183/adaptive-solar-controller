**Pre-release, Release Candidate.** Nicht an echter Hardware langzeitgetestet. Vor dem Update `.storage` sichern und die Änderungen unten lesen.

## Was ist neu
- **FULL-Sperre:** Wird der Inverter-Schalter in der Konfiguration geändert oder umbenannt, gleicht ASC die gespeicherte Besitzmarke jetzt an. Bisher blieb sie hängen (`config_changed_manual_recovery`) und die Sperre schaltete nicht mehr.
- **Abschaltbestätigung:** Nach `turn_off` (Batterie-Notabschaltung und FULL-Sperre) prüft ASC, ob der Schalter wirklich `off` meldet, wiederholt den Befehl nach 15 s und meldet nach drei erfolglosen Versuchen eine Benachrichtigung in Home Assistant.
- **Flight Recorder:** Die erste Zeile nach jedem Start enthält in `events` den Eintrag `ASC_START:<Version>:<Grund>@<Uhrzeit>` (`ha_start` oder `setup_or_reload`). So sind Neustarts in den Aufzeichnungen erkennbar. Das Spaltenschema bleibt gleich.
- **Tests:** Neue Tests mit simuliertem Home Assistant für Notabschaltung und FULL-Sperre (41 Tests).

## Wichtig beim Update
Greift die Notfallregel der Blei-Säure-Strategie (Standard: nach 10 Tagen ohne FULL), schaltet ASC den Wechselrichter über den konfigurierten Schalter ab und hält ihn aus, bis eine Vollladung bestätigt ist. Das passiert nach der Korrektur auch dann, wenn der Schalter geändert oder umbenannt wurde. Einstellungen und Gelerntes bleiben erhalten.

## Installation
HACS → Benutzerdefinierte Repositories → `https://github.com/Darkwulf183/adaptive-solar-controller` (Kategorie Integration), „Beta-Versionen anzeigen“ aktivieren, herunterladen, Home Assistant neu starten.

Der gesamte Verlauf steht im [CHANGELOG](https://github.com/Darkwulf183/adaptive-solar-controller/blob/main/CHANGELOG.md). Entstanden in Zusammenarbeit von Darkwulf183, ChatGPT und Claude.
