**Release Candidate.** Vor dem Update `.storage` sichern und die Änderungen unten lesen.

## Was ist neu
- **Notstrom-Vorsorge:** Neuer Schalter. Ist er an, bleibt der Wechselrichter aus und der Akku wird nur per PV geladen (z. B. vor einem Sturm). Handeinschalten wird respektiert.
- **Wiedereinschalten nach Notabschaltung:** Der Wechselrichter geht nach einer Unterspannungs-Abschaltung erst mit einem neuen bestätigten FULL-Anker (1 h gehalten) wieder an.
- **Handy-Benachrichtigung:** Optionales Feld `notify.<dienst>` in der Konfiguration, Push bei Notabschaltung und beim Wiedereinschalten.
- **FULL-Lernen:** Der FULL-Spitzenwert gilt nur noch pro Ladephase (max. gelernt + 0,3 V). Ein alter Ausreißer blockiert FULL nicht mehr. Neuer Knopf *Reset learned full charge voltage*.
- **FULL-Zyklus:** Eine kurze PV-Zwischenladung beendet den Zyklus nicht mehr, Entladung wird netto gerechnet, FULL-Anker gilt 5 Tage. Niedrig-Anker und Kapazitätslernen werden nicht mehr zu Unrecht abgelehnt.
- **Panel:** Entitäten aus der Konfiguration, Notstrom-Schalter und -Hinweis, Reset-Knopf, Status der Wechselrichter-Sperre, Recorder-Download, deutsche Texte.
- **Versionsnummer** kommt überall aus `manifest.json` (neuer Sensor *ASC version*). Neuer Sensor *Inverter switch status*.
- **Flight Recorder:** Zeilen auch bei pausierter Regelung, neue Spalten `emergency_reserve`, `cutoff_credit_v`, `cutoff_relaxed_v`.
- **Tests:** 84 Tests mit simuliertem Home Assistant.

## Wichtig beim Update
Nach dem Einspielen Home Assistant neu starten und den Browser-Cache leeren (Strg+F5), damit das neue Panel geladen wird. Einstellungen und Gelerntes bleiben erhalten. Das Handy-Feld ist leer, bis du es in den Optionen einträgst.

## Installation
HACS → Benutzerdefinierte Repositories → `https://github.com/Darkwulf183/adaptive-solar-controller` (Kategorie Integration), herunterladen, Home Assistant neu starten.

Der gesamte Verlauf steht im [CHANGELOG](https://github.com/Darkwulf183/adaptive-solar-controller/blob/main/CHANGELOG.md). Entstanden in Zusammenarbeit von Darkwulf183, ChatGPT und Claude.
