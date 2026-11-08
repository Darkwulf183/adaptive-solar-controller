# Changelog

## 0.4.7 RC1

Fehlerbehebung an der FULL-Sperre, Abschaltbestätigung und Start-Marker im Flight Recorder.
Nicht an echter Hardware langzeitgetestet; vor dem Update `.storage` sichern.

**Hinweis zum Verhalten:** Greift die Notfallregel der Blei-Säure-Strategie (standardmäßig nach 10 Tagen ohne FULL), schaltet ASC
den Wechselrichter über den konfigurierten Schalter ab und hält ihn aus, bis eine Vollladung bestätigt ist. Mit der Korrektur
der Besitzmarke passiert das jetzt auch dann, wenn der Schalter geändert oder umbenannt wurde.

### Abschaltbestätigung
- Nach jedem `turn_off` (Batterie-Notabschaltung und FULL-Sperre) prüft ASC, ob der Schalter wirklich `off` meldet.
  Bleibt er `on`, wird nach 15 s erneut gesendet. Nach 3 erfolglosen Versuchen erscheint eine Benachrichtigung in
  Home Assistant. Neue Statuswerte: `cutoff_switch_off_pending/retry/confirmed/unconfirmed`,
  `cutoff_switch_unavailable`, `turn_off_pending/retry/confirmed/unconfirmed`.
- Ein träge nachziehender Schalter (z. B. Cloud-Integration) wird nicht mehr als Handeingriff gewertet.
- Neue Tests mit simuliertem Home Assistant (`tests/test_protection_flow.py`) für Notabschaltung und FULL-Sperre.

### FULL-Sperre
- Wird der konfigurierte Inverter-Schalter geändert oder umbenannt, gleicht ASC die gespeicherte Besitzmarke an,
  statt dauerhaft mit `config_changed_manual_recovery` zu blockieren. Ist der neue Schalter `off`, wird er als eigene
  Sperre übernommen (`owner_switch_adopted`). Ist er `on`, wird die alte Marke verworfen (`stale_owner_released`)
  und die Sperre bei Bedarf neu gesetzt. Ist er nicht verfügbar, wartet ASC (`owner_switch_pending`).
  Dabei wird nie der alte Schalter bedient.

### Flight Recorder
- Die erste geschriebene Zeile nach jedem Start enthält in der Spalte `events` den Eintrag
  `ASC_START:<Version>:<Grund>@<Uhrzeit>`. Grund `ha_start` heißt: Home Assistant wurde gestartet,
  `setup_or_reload` heißt: Integration neu geladen, aktualisiert oder neu eingerichtet.
  Damit sind Datenlücken durch Neustarts eindeutig erkennbar, und die Version steht in den Aufzeichnungen.
  Das Spaltenschema bleibt unverändert, bestehende Tagesdateien werden nicht archiviert.

## 0.4.6 RC4

Sicherheits- und Robustheits-Update. Die Regelungslogik (Controller, Planner, Batterie-Schätzer) ist unverändert.
Nicht an echter Hardware langzeitgetestet; vor dem Update `.storage` sichern und zuerst im Modus `monitor` starten.

### Batterieschutz
- Nicht verfügbare Sensoren (Spannung, Strom, Netz, Inverter-Ausgang) werden nicht mehr als 0 gelesen.
  Die Regelung pausiert mit `blocked_reason` `sensor_invalid:<name>`.
- Fehlende Batteriespannung verriegelt erst nach 120 s (vorher sofort wie 0 V).
- Unterspannung wird entprellt: mindestens 2 Messungen und 10 s unter der Grenze. Klemmenspannung
  ≤ Notabschaltung − 1,0 V verriegelt weiterhin sofort.
- Die Prüfung läuft in jedem Zyklus zuerst (auch bei Solar-Freigabe aus, Warmup, pausierter Regelung)
  und zusätzlich im Watchdog bei veraltetem Netzsensor.
- Ohne eigenen Inverter-Power-Schalter: einmalige persistente Benachrichtigung statt Log-Spam.
- Eine neue Verriegelung wird sofort gespeichert.
- Neue Statuswerte für „Battery hard cutoff status“: `undervoltage_pending`, `sensor_invalid_pending`.

### Zielwert-Helper
- Der Wert wird auf Minimum/Maximum des `input_number`-Helpers begrenzt, der Aufruf blockiert, Fehler werden geloggt.

### PV-CSV-Import
- Konfigurierter Tageserzeugungs-Sensor statt fest verdrahtetem Namen. Ein Export mit genau einem Sensor wird auch bei
  anderem Namen akzeptiert.
- Neue Option „Vorhandene Tage ersetzen“. Parsing im Executor, `csv`-Fehler werden gemeldet.
- Saisonprognose nutzt ein ±7-Tage-Fenster über alle Jahre (Fallback Monatsmittel); vorher nur das Monatsmittel.

### Panel
- Komplett neu gestaltet: fünf Tabs (Übersicht, Planer & Prognose, Batterie & Lernen, Sicherheit, Steuerung),
  Energiefluss PV → Akku → Wechselrichter → Haus, 24-h-Verläufe aus dem Recorder, Warnbanner, Spannungsleiter.
- Technische Zustandswerte auf Deutsch (Rohwert im Tooltip).
- Das Panel aktualisiert bei Wertänderungen nur noch die geänderten Elemente, statt sich komplett neu aufzubauen.
  Das behebt das Springen an den Seitenanfang auf dem Handy; Animationen, Fokus und Dateiauswahl bleiben erhalten.
- Liest zusätzlich Hauslast und erwartete Hauslast (`..._estimated_house_load`, `..._predicted_load`).
- Die CSV-Dateiauswahl bleibt beim Neuzeichnen erhalten, Entity-Werte werden HTML-escaped.
- Die `entry_id` der Entwickler-Installation ist nicht mehr als Fallback im Code hinterlegt.

### Sonstiges
- `manifest.json`: `dependencies` `http` und `recorder`, `iot_class` `calculated`, `issue_tracker`.
- Der statische Pfad wird nur einmal je Home-Assistant-Lauf registriert (Reload-sicher).
- Übersetzungen vervollständigt (`absorption_*`, `inverter_power_switch`), neue `en.json`.
- Flight Recorder liest den Header nur noch einmal je Tagesdatei.
- Repository für HACS umgebaut (`custom_components/`, `hacs.json`, GitHub-Workflows, Tests).

## Frühere Versionen

Siehe [`docs/history/`](docs/history/) (0.4.6, RC2 22-V-Notabschaltung, RC3 CSV-Upload-Fix).
