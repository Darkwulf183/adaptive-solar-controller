# Adaptive Solar Controller (ASC)

Selbstlernender Energiemanager für Home Assistant. ASC regelt die Ausgangsleistung eines
batteriegestützten Wechselrichters so, dass der Netzbezug nahe am Wunschwert bleibt, und plant dabei,
wie viel Batterieenergie bis zur nächsten ausreichenden PV-Ladung sicher genutzt werden kann.

[![HACS Custom Repository](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Darkwulf183&repository=adaptive-solar-controller&category=integration)

> **Status: Release Candidate (0.4.6 RC4), Weg zu 0.5.0.** Die Software greift in die Steuerung eines
> Wechselrichters ein und kann ihn bei Unterspannung abschalten. Sie ist nicht über längere Zeit an
> verschiedenen Anlagen getestet und **ersetzt keinen Hardware-Batterieschutz und kein BMS**.
> Nutzung auf eigene Verantwortung, zuerst im Modus `monitor` beobachten.

## Was ASC macht

```
PV-Historie ─┐
Forecast ────┼─► Estimator ─► Strategy Learner ─► Energy Planner ─► Fast Grid Controller ─► Wechselrichter-Zielwert
Batterie ────┘
```

- **Fast Grid Controller:** stellt den Zielwert eines `input_number`-Helpers anhand der Netzleistung ein
  (adaptive Totzone, gelernte Reaktion des Wechselrichters).
- **Energy Planner:** Energiebudget bis zur nächsten PV-Ladung, Zielreserve, 24/48/72-h-Horizont.
- **Batterielernen:** nutzbare Kapazität, Ladezustand aus Energiebilanz, Rückfederung der Spannung,
  FULL-Erkennung über Absorptionszeit.
- **Prognose:** Forecast.Solar-Vertrauen mit Korrekturfaktor, dazu ein saisonales Modell aus PV-Historie.
- **Batterieschutz:** entprellte Notabschaltung über einen eigenen Inverter-Power-Schalter, siehe unten.
- **Panel in der Seitenleiste** mit Energiefluss, 24-h-Verläufen, Planer, Lernstand und Steuerung.
- **Flight Recorder:** protokolliert jeden Zyklus (10 s) als CSV, zur Auswertung und für Replay-Tests.

Chemie-Strategien: Blei-Säure/PzS (mit mehrtägiger Vollladungs-Planung) und LiFePO₄.

## Voraussetzungen

- Home Assistant **2026.9.0 oder neuer** (ältere Versionen wurden nicht getestet; technisch braucht die Integration mindestens 2025.8 wegen `OptionsFlowWithReload`)
- Integrationen `recorder` und `http` (Standard)
Pflichtfelder im Einrichtungsdialog:

- Sensoren: Netzleistung, PV-Leistung, **Tageserzeugung** (kWh, setzt um 0:00 zurück), Batteriespannung,
  Batteriestrom, Ist-Leistung des Wechselrichters
- Zwei `input_number`-Helper: **Zielwert** für die Wechselrichter-Leistung und **Batterie-Low-Helper**
- Eine `number`-Entität für die **Leistung des Backup-Inverters** (in der Entwickler-Anlage ein APsystems EZ1).
  ASC liest sie nur: Liefert der Backup-Inverter mehr als der Wert „Backup-Sperre ab“ (Standard 40 W), pausiert
  die Regelung. Das ist aktuell ein Pflichtfeld. Anlagen ohne Backup-Inverter brauchen eine `number`-Entität,
  die dauerhaft unter diesem Wert liegt (z. B. ein Template-Number mit Wert 0).
- Ein Schalter oder `input_boolean` als **Solar-Freigabe**

Optional:

- Ein **eigener Power-Schalter** für den Wechselrichter. Ohne ihn kann ASC bei Unterspannung nicht abschalten.
- Sensor für die Batterieleistung
- Forecast.Solar-Sensoren (Prognose-Vertrauen und Planung)

## Installation über HACS

1. HACS → ⋮ → **Benutzerdefinierte Repositories** → URL
   `https://github.com/Darkwulf183/adaptive-solar-controller`, Kategorie **Integration**.
2. Da es ein Release Candidate ist: in HACS bei der Integration **Beta-Versionen anzeigen** aktivieren.
3. Herunterladen, Home Assistant neu starten.
4. Einstellungen → Geräte & Dienste → **Integration hinzufügen** → *Adaptive Solar Controller*.

Manuell: Ordner `custom_components/adaptive_solar_controller` nach `<config>/custom_components/` kopieren.

> **Achtung:** Die vorbelegten Entity-IDs im Einrichtungsdialog (`sensor.e320_power_in`,
> `sensor.solar_average_voltage` usw.) stammen aus der Entwickler-Anlage. Bitte alle Felder auf die
> eigenen Entitäten setzen.

## Panel einrichten

Das Panel wird über `configuration.yaml` eingebunden, siehe [`examples/panel_custom.yaml`](examples/panel_custom.yaml):

```yaml
panel_custom:
  - name: adaptive-solar-controller-panel
    sidebar_title: ASC Panel
    sidebar_icon: mdi:solar-power-variant
    url_path: asc-panel
    module_url: /asc_static/asc-panel.js?v=046rc4ui3
    config:
      entry_id: DEINE_ENTRY_ID
```

Die `entry_id` zeigt in *Entwicklerwerkzeuge → Vorlage*:
`{{ config_entry_id('sensor.adaptive_solar_controller_controller_state') }}`
(alternativ in `.storage/core.config_entries` beim Eintrag mit `domain: adaptive_solar_controller`).
Danach Home Assistant neu starten und die Seite hart neu laden (Strg+F5).

Die `entry_id` wird nur für den CSV-Import im Panel gebraucht.

## Batterieschutz (Kurzfassung)

- Unterspannung wird **entprellt**: mindestens 2 Messungen und 10 s unter der Grenze. Klemmenspannung weit
  unter der Notgrenze (−1,0 V) verriegelt sofort.
- Ein **ungültiger Sensor wird nicht als 0 V gelesen**. Die Regelung pausiert, verriegelt wird erst nach 120 s.
- Die Prüfung läuft in jedem Zyklus **zuerst**, auch bei pausierter Regelung oder veraltetem Netzsensor.
- Abschalten kann ASC nur mit einem konfigurierten Inverter-Power-Schalter. Ohne ihn erscheint eine
  Benachrichtigung in Home Assistant.
- Nach einer Notabschaltung schaltet ASC den Wechselrichter **nicht** selbst wieder ein. Das passiert nur
  bei der Freigabe einer eigenen FULL-Sperre.
- Der Modus `monitor` verhindert die Notabschaltung nicht, nur der Schalter „Controller enabled“.

## Bekannte Einschränkungen

- **Panel:** Für fünf externe Entitäten sind die IDs fest im Panel hinterlegt (`sensor.e320_power_in`,
  `sensor.solar_average_voltage`, `sensor.solar_complete_ampere`, `sensor.solar_watt_aktuell`,
  `input_number.inverter_target_power`). Der Zurück-Button führt nach `/dashboard-solar/solar`.
  In anderen Installationen die Werte in `frontend/asc-panel.js` (Funktion `cfg`) anpassen. Eine
  Konfiguration über die Integration ist für 0.5 geplant. Das Panel wurde nur in Chromium getestet.
- **Abschaltbestätigung:** ASC sendet `turn_off`, prüft aber nicht, ob der Schalter danach wirklich aus ist.
- **FULL-Sperre:** Wurde der Inverter-Schalter in der Konfiguration geändert, kann der gespeicherte Besitz
  der Sperre hängen bleiben (Status `config_changed_manual_recovery`). Dann greift die FULL-Haltephase nicht.
- **Tests:** Es gibt Unit-Tests für Schutzlogik und CSV-Import. Controller, Planner und Batterie-Schätzer
  sind noch nicht per Test abgedeckt. Die Replay-Auswertung mit Flight-Recorder-Daten läuft bisher manuell.
- Die Beispiel-Dashboard-Datei [`examples/dashboard_solar_asc.yaml`](examples/dashboard_solar_asc.yaml)
  ist das persönliche Dashboard des Entwicklers und braucht die Karten `modern-circular-gauge` und `apexcharts-card`.

## Roadmap

| Version | Schwerpunkt | Ziel (Planung) |
| --- | --- | --- |
| 0.4.7 | Sicherheit & Stabilität, Tests, CSV-Import | ab 09.11.2026 als RC, sofern testbereit |
| 0.4.8 | Saison- und Batterielernen verfeinern | Nov/Dez 2026 |
| 0.4.9 | Multi-Inverter (APsystems + EZ1), Systemintegration | Dez 2026 / Jan 2027 |
| 0.5.0 | Stable: Migration, Langzeittests, Dokumentation | Jan/Feb 2027, abhängig von den Tests |

Die Termine sind Planungsziele. Eine Version wird erst freigegeben, wenn die Tests bestanden sind.

## Entwicklung

```bash
python -m unittest discover -s tests -v        # Tests ohne Home Assistant
node --check custom_components/adaptive_solar_controller/frontend/asc-panel.js
```

Änderungen stehen im [CHANGELOG](CHANGELOG.md), ältere Hinweise in [`docs/history/`](docs/history/).

## Mitwirkende

Entstanden in Zusammenarbeit von **Darkwulf183**, **ChatGPT** (OpenAI) und **Claude** (Anthropic).
Wer was beigetragen hat, steht in [CONTRIBUTORS.md](CONTRIBUTORS.md).

Lizenz: [GPL-3.0](LICENSE).
