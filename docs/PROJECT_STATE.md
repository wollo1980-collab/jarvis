# PROJECT STATE

Stand: 2026-07-01
Quelle: `README.md`, `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_3.docx`, `docs/logbook.md`, `docs/CHANGELOG.md`, `docs/adr/*.md`

## Current Version
`v0.5.1` (zweiter Baustein: Tabellen-Auswertung) - `v0.5` läuft weiter, noch NICHT abgeschlossen. `v0.4` bleibt abgeschlossen und als Tag `v0.4` gesetzt.

## Status
`v0.3` und `v0.4` sind abgeschlossen.
`v0.5 "Arbeitsmodule"` läuft. Umgesetzt:
- **Excel-Lesen, Phase 1** (`commands/excel.py::ReadExcelCommand`, Intent `read_excel`, Sicherheitsstufe 0, ADR-014): liest `.xlsx`/`.xlsm` über `openpyxl` (read-only), Blattnamen/Dimensionen im Ergebnistext, Rohdaten in `Result.data["sheets"]` (pro Blatt auf 500 Zeilen begrenzt). Kein Sonderfall in `core/ai.py` - Registry-Beschreibung reicht (verifiziert). Lese-Logik jetzt in wiederverwendbarer Funktion `read_workbook_sheets()`.
- **Tabellen-Auswertung: Datenauswertung** (`commands/reports.py::AnalyzeReportCommand`, Intent `analyze_report`, Sicherheitsstufe 0, ADR-015): liest einen Datentabelle (baut auf `read_workbook_sheets()` auf) und lässt `AIEngine.answer()` die Daten analysieren, mit Pflicht-Disclaimer am Ende jeder Antwort. Erster Command mit direktem KI-Zugriff (`AIEngine` per `commands.reports.configure(ai)` injiziert, `main.py` verdrahtet das).
- Tests: `117 / 117` grün.

Aus v0.4 weiterhin gültig:
- **Kurz-/Langzeitgedaechtnis** (Handbook Kap. 9/13/27): Kurzzeit-Anteil (`memory/store.py::JsonMemoryStore`) persistiert Gespraechsverlauf tagesuebergreifend; Langzeit-Anteil (`memory/long_term.py::LongTermMemory`, ADR-009), nur auf ausdruecklichen Zuruf.
- **PC-Grundsteuerung** (Kap. 17/27): oeffnen (`open_program`), ueberwachen (`system_status`, ADR-011), installieren (`install_program`, ADR-012).

## Current Development Phase
`v0.5 "Arbeitsmodule"` laut Handbook Kap. 13 - zwei Teilschritte umgesetzt (Excel-Lesen, Tabellen-Auswertung). Aktive Reihenfolge laut Wolfgang (Stand 01.07.2026, siehe Product-Owner-Entscheidung unten): Excel-Integration -> Tabellen-Auswertung -> KPI. **Power BI ist aus dem aktiven v0.5-Scope herausgenommen worden.**

## Next Planned Version
Weiterhin `v0.5` - noch NICHT abgeschlossen. Naechster und laut aktueller Priorisierung letzter aktiver Teilschritt: **KPI aus Excel-/Reportdaten berechnen**. Kein technischer Vorschlag dafuer bisher erstellt, kein Code geschrieben.

## Next Goal According To Handbook
`v0.5` (Kap. 13/27, praezisiert in v3.3/ADR-013) hat als Kerninhalt "Tabellen-Auswertung, KPI, Power BI, Excel". Excel Phase 1 (ADR-014) und Tabellen-Auswertung/Datenauswertung (ADR-015) sind erledigt. Naechster offener Baustein laut Wolfgangs expliziter Reihenfolge: KPI.
**Power BI** steht zwar weiterhin im Handbook-Text (Kap. 13/27) als Teil von "Arbeitsmodule", ist aber per Product-Owner-Entscheidung (01.07.2026, siehe unten) fuer die aktive v0.5-Umsetzung ausgeklammert - Grund: Power BI liegt auf dem Firmenrechner/im Firmenumfeld, keine praktische Implementierung in diesem Rahmen. Diese Entscheidung gilt bis zur naechsten Handbook-Version als verbindlich (Kap. 2: Handbook wird nur zwischen zwei Jarvis-Versionen geaendert) und hat in der Zwischenzeit Vorrang vor dem aktuellen Handbook-Wortlaut.
Vor jedem weiteren Baustein gilt weiterhin: Handbook-Pruefung (Scope/DoD/Architektur/Sicherheitsmodell) + technischer Vorschlag zur Freigabe durch den Product Owner, bevor Code geschrieben wird (Muster aus ADR-013/ADR-014/ADR-015).

## Product-Owner-Entscheidung: Power BI aus v0.5-Scope genommen (01.07.2026)
**Entscheidung:** Power BI wird in v0.5 nicht praktisch implementiert. Fuer Jarvis v0.5 bleibt der Fokus auf drei Bausteinen: (1) Excel lesen, (2) Tabellen-Auswertung analysieren, (3) KPI aus Excel-/Reportdaten berechnen. Power BI wird als optionale Unternehmensintegration bzw. spaeterer Baustein behandelt, kein aktiver v0.5-Scope.
**Begruendung:** Power BI liegt auf dem Firmenrechner/im Firmenumfeld - keine praktische Implementierbarkeit im aktuellen Jarvis-Rahmen.
**Charakter der Entscheidung:** Priorisierungs-/Scope-Entscheidung des Product Owner, keine Architekturentscheidung - deshalb bewusst KEINE eigene ADR (siehe Kap. 20: ADRs sind fuer Architekturentscheidungen vorgesehen).
**Handbook-Bezug:** Das Master-Handbook (Kap. 13/27) nennt Power BI weiterhin als Teil von "Arbeitsmodule/v0.5". Gemaess der in Handbook v3.3/Kap. 2 festgelegten Regel ("Handbook wird nur ZWISCHEN zwei Versionen geaendert") wird der Handbook-Text erst bei der naechsten geplanten Handbook-Version entsprechend nachgezogen. Bis dahin gilt diese Product-Owner-Entscheidung als verbindlich und hat Vorrang fuer die weitere Entwicklung von v0.5.
**Status:** Aktiv, keine Code-Aenderung ausgeloest.

## Tests
Letzter Check am 2026-07-01: `pytest tests -v` mit zusaetzlichem `PYTHONPATH`.

### Test Status
`117 / 117` bestanden

### Known Failure
Keiner aktuell. `tests/test_integration.py::test_end_to_end_tool_execution` (vormals bekannter, Windows-spezifischer Fehlschlag wegen `os.startfile` vs. gemocktem POSIX-Pfad) lief in den letzten Durchlaeufen gruen durch. Falls der Fehlschlag erneut auftritt, siehe `docs/logbook.md` (Eintraege 2026-07-01) fuer die dokumentierte Ursache.

## Offene Aufgaben

### Technische TODOs (Definition of Done / Betrieb, kein neuer Scope)
- Manueller Live-Test aller Kernfunktionen mit echtem API-Key auf dem echten Windows-Rechner (Definition of Done, Kap. 28) - bisher nur automatisiert/gemockt getestet: `system_status`, `install_program`, `remember_fact`/`forget_fact`, `read_excel`, `analyze_report`. Insbesondere `install_program` real ausfuehren ist ein bewusster, expliziter Schritt (installiert wirklich Software) und sollte gezielt vom Product Owner freigegeben/begleitet werden. `analyze_report` real mit einem echten Datentabelle zu testen wuerde ausserdem zeigen, ob die generische `answer()`-Wiederverwendung inhaltlich ausreicht (siehe ADR-015).
- Piper-Sprachmodell herunterladen und `tts_enabled: true` fuer einen Live-TTS-Test setzen.
- Zwei bis drei Piper-Stimmen pruefen und danach `offline vs. Cloud-TTS` entscheiden.
- `.git_broken_5/` (Reste eines fruehen, abgebrochenen git-init-Versuchs) liegt noch im Arbeitsordner, ist per `.gitignore` von der Versionierung ausgeschlossen. Kann bei Gelegenheit manuell aufgeraeumt werden, wurde bewusst nicht geloescht (keine destruktive Aktion ohne Rueckfrage).

### Feature-TODOs (naechste Roadmap-Bausteine, NICHT jetzt umsetzen)
- `v0.5`: KPI aus Excel-/Reportdaten berechnen (naechster und aktuell letzter aktiver v0.5-Schritt).
- Power BI - per Product-Owner-Entscheidung (01.07.2026) aus dem aktiven v0.5-Scope genommen (Firmenrechner/Firmenumfeld, keine praktische Implementierbarkeit hier). Behandelt als optionale Unternehmensintegration/spaeterer Baustein, keine Prioritaet aktuell.
- Eigene `AIEngine.summarize_report()`-Methode - nur pruefen, falls die Wiederverwendung von `answer()` bei `analyze_report` sich als inhaltlich unzureichend erweist (ADR-015).
- Excel Phase 2 (Schreiben, Formatieren, Power Query, Makros) - explizit nicht Teil von Phase 1 (ADR-013/ADR-014), keine Priorisierung dafuer.
- `.xls` (Legacy-Format) - von `openpyxl` nicht unterstuetzt, keine eigene Priorisierung bisher.
- Outlook-Integration - explizit aus v0.5 ausgeklammert (Handbook v3.3, Kap. 27), eigene, spaetere Priorisierung noetig.
- `v0.6 Handy`: Telegram-Bot, Fernzugriff.
- `Deinstallieren` (winget) - im Handbook (Kap. 17) genannt, aber nicht Teil der v0.4-Priorisierung (Kap. 27, siehe ADR-012); braucht eigene Priorisierung und vermutlich eigene Sicherheitsstufen-Bewertung.
- Festplatten-Ueberwachung/-Bereinigung - separater Handbook-Punkt (Kap. 17), nicht in v0.4 enthalten (siehe ADR-011).
- Temperatur-Monitoring - unter Windows von `psutil` nicht unterstuetzt (Plattform-Limitierung, kein Priorisierungsthema).

Im Code wurden keine `TODO`-/`FIXME`-Marker gefunden.

## Latest ADR
`ADR-015 - Tabellen-Auswertung Phase 1: KI-Analyse von Datentabelles`

## Latest Architecture Change
`commands/reports.py::AnalyzeReportCommand` (Intent `analyze_report`, Sicherheitsstufe 0) ist der erste Command mit direktem `AIEngine`-Zugriff (`configure()`-Injection wie bei `LongTermMemory`, ADR-009) - der Executor bleibt unveraendert. `AIEngine.answer()` wird wiederverwendet, keine neue `ai.py`-Methode. Dabei wurde ein potenzieller Zirkelimport (`core.ai` <-> `commands`) entdeckt und ueber einen `TYPE_CHECKING`-Import geloest. Die openpyxl-Leselogik aus `commands/excel.py` wurde in `read_workbook_sheets()` extrahiert, damit beide Excel-basierten Commands sie teilen (DRY).

## Known Limitations
- Langzeitgedaechtnis funktioniert nur auf Zuruf; es gibt keine automatische Fakten-Extraktion.
- `listen()` bleibt Konsole; Mikrofon/Wake-Word ist weiterhin nicht umgesetzt.
- Kokoro TTS unterstuetzt aktuell kein Deutsch.
- Fehlt ein TTS-Modell oder Backend, faellt Jarvis auf reine Konsolenausgabe zurueck.
- Systemueberwachung liest keine Temperatur aus (`psutil` unterstuetzt das unter Windows nicht) und keine Festplattenbelegung (separater, noch nicht priorisierter Handbook-Punkt).
- `install_program` deckt kein "Deinstallieren" ab (bewusst nicht in v0.4-Scope, siehe ADR-012) und braucht `winget` (App Installer aus dem Microsoft Store) auf dem Zielsystem.
- `read_excel`/`analyze_report` lesen nur `.xlsx`/`.xlsm` (kein `.xls`), nur Werte (keine Formeln/Formatierung/Makros), pro Arbeitsblatt auf 500 Zeilen begrenzt.
- `analyze_report` liefert eine KI-generierte Analyse, die falsch liegen kann (kein deterministisches Ergebnis wie bei `read_excel`) - deshalb Pflicht-Disclaimer in jeder Antwort (ADR-015).

## Git
Ein einzelner, ehrlicher Initial-Commit aus dem aktuellen Arbeitsstand (kein rekonstruierter Verlauf aus alten ZIP-Staenden), getaggt als `v0.4`. Danach je ein Commit fuer Handbook v3.3/ADR-013, Excel-Lesen (ADR-014) und Tabellen-Auswertung (ADR-015). Fruehere Versionen (v0.1-v0.3) existieren nur als Text in `docs/CHANGELOG.md`/`docs/logbook.md`, nicht als eigene Git-Commits/Tags - das im Handbook (Kap. 21) urspruenglich vorgesehene inkrementelle Nachziehen der Commit-Historie wurde bewusst nicht gemacht (keine kuenstliche Fake-Historie). Kein neuer Tag seit `v0.4` - `v0.5` wird erst bei Abschluss aller aktiven v0.5-Bausteine getaggt (Wolfgangs Entscheidung). Die Power-BI-Scope-Entscheidung selbst ist reine Doku (dieser Stand), noch nicht committed.

## Product Owner Rules
- Product Owner entscheidet Prioritaeten.
- KI darf Umsetzung vorschlagen, aber keine Roadmap aendern.
- Bei Konflikt gewinnt das Master-Handbook.
