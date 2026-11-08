**Pre-release, Release Candidate.** Nicht an echter Hardware langzeitgetestet. Vor dem Update `.storage` sichern und zuerst im Modus `monitor` beobachten.

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

## Installation
HACS → Benutzerdefinierte Repositories → `https://github.com/Darkwulf183/adaptive-solar-controller` (Kategorie Integration), „Beta-Versionen anzeigen“ aktivieren, herunterladen, Home Assistant neu starten.

Entstanden in Zusammenarbeit von Darkwulf183, ChatGPT und Claude.
