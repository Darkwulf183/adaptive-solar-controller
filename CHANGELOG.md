# Changelog

## 0.4.9 dev1 (Teststand, nicht veröffentlicht)

Aus der Notabschaltung vom 27.11.2026 (Recorder 24.–27.11.).

### Planer: Energie einteilen (neu)
- Sind mehrere schwache Tage zu erwarten (48-h- und 72-h-Horizont im Defizit), verteilt ASC das nutzbare Batteriebudget auf die Zeit bis zur nächsten
  Lademöglichkeit (bis 10:00 Uhr des nächsten Tages plus 24 h je weiterem schwachen Tag) und begrenzt die Ausgangsleistung entsprechend
  (PV-Leistung kommt oben drauf). Bisher fuhr der Planer den vollen Akku am ersten Abend mit 660 W leer (24.11.). Bei guter Prognose ändert sich nichts.
  Neue Recorder-Spalte `rationing_limit_w`.

### Lernen / Batterieschätzung
- **Messqualität:** Der Zeitabstand zwischen Spannungs- und Stromsensor wird jetzt aus `last_reported` (mit Rückfall auf `last_updated`) gebildet.
  Bisher galt ein über Stunden gleich bleibender Nachtstrom als „veraltet“, dadurch wurden ~41 % aller Messwerte als `degraded` verworfen
  (keine Energie-Integration, keine Plausibilitätskorrektur). Folge war eine zu hohe Reserveschätzung (52 % bei 22,85 V).
- **Spannungs-Untergrenze:** Nahe der Abschaltgrenze (≤ Grenze + 0,25 V) bei kleiner Last (0,3–5 A Entladung), 5 Minuten lang, wird die geschätzte
  Reserve auf höchstens 10 % der Kapazität begrenzt (Ereignis `RESERVE_CAPPED_BY_VOLTAGE`).

## 0.4.8 RC1

(Zusammenfassung der Teststände dev1 und dev2.)

### Handy-Benachrichtigung bei Notabschaltung (neu)
- Neues optionales Feld in der Konfiguration: **Handy-Benachrichtigung** (z. B. `notify.mobile_app_meinhandy`). Bei einer Batterie-Notabschaltung
  sendet ASC eine Push-Nachricht, bei Wiedereinschalten nach FULL ebenfalls. Zusätzlich immer eine Benachrichtigung in Home Assistant.
  Ein fehlender oder fehlerhafter Dienst stört die Abschaltung nicht.


### Wiedereinschalten nach Batterie-Notabschaltung (neu)
- Nach einer Notabschaltung (Unterspannung) bleibt der Wechselrichter aus, bis ein **neuer FULL-Anker** (jünger als die Abschaltung) bestätigt ist
  und 1 Stunde gehalten hat. Dann schaltet ASC den Wechselrichter-Schalter selbst wieder ein (`turn_on_sent`).
- Status: `recovered_wait_for_full` (Sperre aufgehoben, wartet auf FULL), `awaiting_full_after_cutoff` (alter FULL zählt nicht).
- Schaltest du von Hand ein, wird das respektiert und das Warten beendet. Nur wenn ASC den Schalter selbst ausgeschaltet hat (Schalter steht beim Erholen auf „aus"), übernimmt ASC ihn.

## 0.4.8 dev1

Notstrom-Vorsorge, zwei Lernfehler-Korrekturen aus dem Flight Recorder (24./25.11.2026), Recorder-Erweiterungen.
Nur im Zweig `dev` und als ZIP; `.storage` vor dem Test sichern.

### Notstrom-Vorsorge (neu)
- Neuer Schalter **Emergency power reserve**. Ist er an, schaltet ASC den konfigurierten Wechselrichter-Schalter aus und lässt ihn aus;
  der Akku wird nur noch per PV geladen und bleibt voll (z. B. vor einem Sturm oder erwarteten Stromausfall). Nur dieser Schalter wird bedient.
- Schaltest du den Wechselrichter von Hand wieder ein (Notfall), respektiert ASC das (`emergency_manual_on`) und schaltet ihn nicht wieder aus,
  bis du ihn selbst wieder ausgeschaltet hast. Kein automatisches Einschalten bei Netzausfall.
- Schaltest du die Notstrom-Vorsorge aus, übernimmt die normale FULL-Sperre: der Wechselrichter wird erst nach bestätigtem FULL wieder eingeschaltet.
- Die Batterie-Notabschaltung (Unterspannung) hat weiterhin Vorrang.
- Statuswerte im Recorder (`inverter_switch_action`): `emergency_off`, `emergency_turn_off_confirmed`, `emergency_turn_off_pending`,
  `emergency_already_off`, `emergency_manual_on`. Neue Recorder-Spalte `emergency_reserve`.

### Panel und Aufräumen
- Panel liest Netz-/Ziel-/Batterie-/PV-Entitäten aus der Konfiguration (keine festen IDs mehr).
- Notstrom-Schalter in Steuerung und Kopfzeile, Reset-Knopf für den FULL-Wert (zweistufig), Status der Wechselrichter-Sperre im Reiter Sicherheit
  (neuer Sensor *Inverter switch status*), deutsche Texte für alle Sperr-Status.
- Versionsnummer kommt überall aus `manifest.json` (neuer Diagnose-Sensor *ASC version*); Dashboard-Beispiel ohne Versionsnummern im Titel.
- Recorder-Dateien lassen sich im Panel herunterladen. Sensornamen vereinheitlicht (nur Namen, Entity-IDs unverändert).

### Lernen
- **FULL-Spitzenwert:** `full_charge_peak_v` gilt nur noch für die laufende Ladephase und darf den gelernten Wert höchstens um 0,3 V überschreiten.
  Ein einmaliger Ausreißer zieht den gelernten FULL-Wert nicht mehr bei jeder Ladung wieder hoch (dadurch wurde FULL im November nicht mehr erkannt).
- **FULL-Zyklus:** Eine kurze PV-Zwischenladung beendet den FULL-Zyklus nicht mehr. Die Entladung seit FULL wird netto gerechnet
  (Ladung zieht ab). Ein FULL-Anker gilt bis 5 Tage. Damit werden Niedrig-Anker und Kapazitätslernen nicht mehr mit
  `LOW_ANCHOR_REJECTED_NO_FULL` abgelehnt.
- **Neuer Knopf** *Reset learned full charge voltage*: setzt den gelernten FULL-Wert auf 28,8 V und lernt ihn neu (statt `.storage` zu bearbeiten).

### Versionsnummer
- Einzige Quelle ist `manifest.json`; `const.py` liest sie von dort. Das Panel zeigt die laufende Version (neuer Diagnose-Sensor *ASC version*)
  statt einer festen Angabe. Das Dashboard-Beispiel enthält keine Versionsnummern mehr. Ein Test prüft Manifest, CHANGELOG und (bei Releases) die README.

### Flight Recorder
- Neue Spalten `emergency_reserve`, `cutoff_credit_v`, `cutoff_relaxed_v` (angerechnete Erholung / geschätzte entspannte Spannung der Notabschaltung).
  Hinweis: Wegen der geänderten Spalten wird die heutige Datei beim ersten Start als `_old.csv` abgelegt und neu begonnen.
- Pausierte Zyklen (z. B. `solar_release_off`, `sensor_invalid`, `warmup_after_enable`) schreiben jetzt eine schlanke Zeile (höchstens alle 60 s), Ereignis `PAUSED:<Grund>`.
- Panel (Steuerung): Kachel *Flight Recorder · Download* zum Herunterladen der CSV-Dateien (nur Administratoren).

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
