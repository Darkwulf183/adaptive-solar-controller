ASC v0.4.6 RC4 - Sicherheits- und Robustheits-Update (Regelungslogik unveraendert)

NOCH NICHT AN ECHTER HARDWARE GETESTET. .storage vorher sichern. Monitor-Modus zuerst.

Batterieschutz
- Nicht verfuegbare Sensoren (Spannung/Strom/Netz/Inverter-Ausgang) werden NICHT mehr als 0 gelesen.
  Regelung pausiert mit blocked_reason "sensor_invalid:<name>".
- Fehlt die Batteriespannung, wird erst nach 120 s verriegelt (vorher sofort wie 0 V).
- Unterspannung wird entprellt: mindestens 2 Messungen UND 10 s unterhalb der Grenze.
  Klemmenspannung <= Notabschaltung minus 1,0 V verriegelt weiterhin sofort.
- Die Pruefung laeuft jetzt bei JEDEM Zyklus zuerst (auch bei Solar-Freigabe aus, Warmup,
  pausierter Regelung) und zusaetzlich im Watchdog, wenn der Netzsensor veraltet ist.
- Ohne eigenen Inverter-Power-Schalter: einmalige persistente Benachrichtigung statt Log-Spam.
- Neuer Verriegelungszustand wird sofort gespeichert.
- Neue Statuswerte in "Battery hard cutoff status":
  undervoltage_pending, sensor_invalid_pending, trip_*-Zustaende wechseln direkt zu cutoff_*.

Zielwert-Helper
- Wert wird auf min/max des input_number-Helpers begrenzt (z. B. 0 W bei FULL-Sperre -> Helper-Minimum),
  blockierender Aufruf mit Fehlerlog statt stillem Fehlschlag.

PV-CSV
- Konfigurierter Tageserzeugungs-Sensor statt fest verdrahtetem Namen; Export mit genau
  einem Sensor wird auch bei anderem Namen akzeptiert.
- Neue Option "Vorhandene Tage ersetzen". Parsing im Executor, csv-Fehler werden gemeldet.
- Prognose: +/-7-Tage-Fenster ueber alle Jahre (Fallback Monatsmittel), vorher nur Monatsmittel.

Sonstiges
- manifest: dependencies http+recorder, iot_class calculated, Version 0.4.6rc4.
- Statischer Pfad wird nur einmal je HA-Lauf registriert (Reload-sicher).
- Uebersetzungen vervollstaendigt (absorption_*, inverter_power_switch); en.json neu.
- Flight Recorder liest den Header nur noch einmal je Tagesdatei.
- Panel: Dateiauswahl bleibt bei Neuzeichnen erhalten, unveraenderte Zustaende zeichnen nicht neu,
  Entity-Werte werden HTML-escaped.

Update: Ordner ersetzen, panel_custom_v0.4.6_RC4.yaml verwenden (entry_id eintragen), HA neu starten.
Tests (ohne HA): python3 -m unittest discover -s tests -v

Panel-Redesign (Seitenleiste "ASC Panel")
- Fuenf Tabs: Uebersicht, Planer & Prognose, Batterie & Lernen, Sicherheit, Steuerung.
- Uebersicht: Live-Energiefluss PV -> Akku -> Wechselrichter -> Haus, Kennzahlen (Reserve, PV heute,
  Energie-Budget, Planungsvertrauen) und 24-h-Verlaeufe (Spannung, Strom, PV, Netz & Zielwert).
  Die Verlaeufe kommen aus dem Recorder (history/history_during_period) und sind optional.
- Warnbanner bei Batterieschutz, ungueltigem Sensor, ausgeschaltetem Regler.
- Sicherheit: Spannungsleiter mit Notabschaltung, LOW-Grenze und aktueller Batteriespannung.
- Technische Zustandswerte auf Deutsch (Rohwert im Tooltip). Unbekannte Werte werden lesbar gemacht.
- Neu gelesen: sensor.adaptive_solar_controller_estimated_house_load und ..._predicted_load (Hauslast).
- Unveraendert: alle Entity-IDs, Services, CSV-Import. Panel-YAML: module_url ...?v=046rc4ui2
