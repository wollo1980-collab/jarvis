# PROJECT STATE

Stand: 2026-07-02
Quelle: `README.md`, `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_5.docx`, `docs/logbook.md`, `docs/CHANGELOG.md`, `docs/adr/*.md`

## Current Version
`v0.7.0` (zwei Bausteine umgesetzt: PC-Analyse Phase 1, Ereignisprotokoll-Analyse Phase 2) - `v0.7` als Gesamtversion ist NOCH NICHT getaggt (weitere Kap.-17-Bausteine offen). `v0.4`/`v0.5`/`v0.6` bleiben abgeschlossen und getaggt. Handbook ist auf `v3.5` (inkl. Kap.-2-Konsistenzkorrektur, siehe Git-Historie).

## Status
`v0.3`, `v0.4`, `v0.5` und `v0.6` sind abgeschlossen und getaggt (`v0.4`, `v0.5`, `v0.6`).
`v0.7 "PC-Admin"` hat begonnen. Umgesetzt:
- **PC-Analyse, Phase 1** (`commands/monitor.py::AnalyzePcCommand`, Intent `analyze_pc`, Sicherheitsstufe 0, ADR-020): Festplattenbelegung, Top-5-Prozesse nach CPU/RAM, mehrfach laufende Prozesse (nur Hinweis), Autostart-Programme (Registry Run-Keys HKCU+HKLM sowie Startup-Ordner, nur anzeigen). Python sammelt/strukturiert deterministisch, die KI (`AIEngine.answer()`) formuliert nur den Bericht - wie bei `calculate_kpi` (ADR-016). Zweiter Command mit direktem KI-Zugriff, eigenes zu `reports.py` bewusst dupliziertes `configure()`-Muster (keine gemeinsame Abstraktion, solange nur zwei Verwender). **Keine Änderung an `core/ai.py`, `core/planner.py`, `core/tool_manager.py`, `executor/executor.py` oder anderen `commands/*.py`-Dateien** (per `git diff --stat` verifiziert).
- **Ereignisprotokoll-Analyse, Phase 2** (`commands/monitor.py::AnalyzeEventLogCommand`, Intent `analyze_event_log`, Sicherheitsstufe 0, ADR-021): liest die jüngsten Fehler/Warnungen aus `System`- und `Application`-Log über `wevtutil` (Windows-Bordmittel, `subprocess`, keine neue Abhängigkeit), serverseitig gefiltert (Level Error/Warning), begrenzt auf 20 Einträge je Log. `/f:RenderedXml` für sprachversions-unabhängiges Parsen (`xml.etree.ElementTree`). Jede Log-Quelle einzeln abgesichert (Teilergebnis statt Totalausfall); schlagen beide fehl, liefert der Command `Status.FAILED` ohne KI-Aufruf. Nutzt die bereits vorhandene `configure()`-Infrastruktur aus Phase 1 - **keine Änderung an `main.py`** nötig. **Keine Änderung an `core/ai.py`, `core/planner.py`, `core/tool_manager.py`, `executor/executor.py`** (per `git diff --stat` verifiziert: nur `commands/monitor.py`, `tests/test_commands_monitor.py`, `docs/adr/ADR-021.md`).
- Tests: `180 / 180` grün.
- Security-Log, Löschen von Log-Einträgen, automatische Reparaturmaßnahmen, Optimierung/Bereinigung, Registry-Änderungen, Dienste, Treiber, Autostart-Schreibzugriff sind bewusst NICHT enthalten (Phase 1/2).

Aus v0.6 weiterhin gültig:
- **Telegram-Fernzugriff** (`telegram_main.py`, ADR-018), manueller Smoke-Test bestanden (02.07.2026). Web-Interface/WireGuard VPN/Eigene App bewusst nicht umgesetzt (Handbook Kap. 16, v3.5).

Aus v0.5 weiterhin gültig:
- **Excel-Lesen, Phase 1** (`commands/excel.py::ReadExcelCommand`, ADR-014), **Tabellen-Auswertung** (`commands/reports.py::AnalyzeReportCommand`, ADR-015), **KPI** (`commands/reports.py::CalculateKpiCommand`, ADR-016). Power BI weiterhin nicht enthalten (Handbook Kap. 29 Backlog).

Aus v0.4 weiterhin gültig:
- **Kurz-/Langzeitgedaechtnis** (Handbook Kap. 9/13/27): Kurzzeit-Anteil (`memory/store.py::JsonMemoryStore`) persistiert Gespraechsverlauf tagesuebergreifend; Langzeit-Anteil (`memory/long_term.py::LongTermMemory`, ADR-009), nur auf ausdruecklichen Zuruf.
- **PC-Grundsteuerung** (Kap. 17/27): oeffnen (`open_program`), ueberwachen (`system_status`, ADR-011), installieren (`install_program`, ADR-012).

## Current Development Phase
`v0.7 "PC-Admin"` laut Handbook Kap. 13 - Phase 1 (System-Analyse: Festplatte/Prozesse/Autostart, ADR-020) und Phase 2 (Ereignisprotokoll-Analyse, ADR-021) umgesetzt. Weitere Kap.-17-Bausteine (Treiber, Dienste, Bereinigung, Autostart-Schreibzugriff) NICHT begonnen - naechste Priorisierung liegt beim Product Owner.

## Next Planned Version
Weiterhin `v0.7` - noch NICHT abgeschlossen/getaggt. Offene Entscheidung: naechsten Kap.-17-Baustein priorisieren (z. B. Autostart-Verwaltung mit Schreibzugriff, Bereinigung, Dienste, Treiber - alle vier bedeuten einen Sicherheitsstufen-Sprung ueber Stufe 0 hinaus) oder v0.7 mit dem aktuellen Umfang als abgeschlossen betrachten und taggen. Kein technischer Vorschlag fuer einen weiteren Baustein bisher erstellt, kein Code geschrieben.

## Next Goal According To Handbook
`v0.6` ist inhaltlich vollstaendig und im Handbook (v3.5) selbst als abgeschlossen markiert. `v0.7 "PC-Admin"` (Kap. 13/17) hat mit Phase 1 (System-Analyse: Festplatte/Prozesse/Autostart, nur lesen, ADR-020) und Phase 2 (Ereignisprotokoll-Analyse, nur lesen, ADR-021) begonnen.
Kap. 17 nennt fuer v0.7 weiterhin offen: Treiber pruefen/aktualisieren, Dienste starten/stoppen, Autostart *verwalten* (Phase 1 deckt nur *anzeigen* ab), Temp-/Festplatten-Bereinigung.
Vor jedem weiteren Baustein gilt weiterhin: Handbook-Pruefung (Scope/DoD/Architektur/Sicherheitsmodell) + technischer Vorschlag zur Freigabe durch den Product Owner, bevor Code geschrieben wird (Muster aus ADR-013 bis ADR-021).

## Tests
Letzter Check am 2026-07-02: `pytest tests -v` mit zusaetzlichem `PYTHONPATH`.

### Test Status
`180 / 180` bestanden

### Known Failure
Keiner aktuell. `tests/test_integration.py::test_end_to_end_tool_execution` (vormals bekannter, Windows-spezifischer Fehlschlag wegen `os.startfile` vs. gemocktem POSIX-Pfad) lief in den letzten Durchlaeufen gruen durch. Falls der Fehlschlag erneut auftritt, siehe `docs/logbook.md` (Eintraege 2026-07-01) fuer die dokumentierte Ursache.

## Offene Aufgaben

### Technische TODOs (Definition of Done / Betrieb, kein neuer Scope)
- Manueller Live-Test der uebrigen Kernfunktionen mit echtem API-Key auf dem echten Windows-Rechner (Definition of Done, Kap. 28) - bisher nur automatisiert/gemockt getestet: `system_status`, `install_program`, `remember_fact`/`forget_fact`, `read_excel`, `analyze_report`, `calculate_kpi`, `analyze_pc` (Telegram-Fernzugriff ist seit 02.07.2026 real getestet). Insbesondere `install_program` real ausfuehren ist ein bewusster, expliziter Schritt (installiert wirklich Software) und sollte gezielt vom Product Owner freigegeben/begleitet werden.
- Piper-Sprachmodell herunterladen und `tts_enabled: true` fuer einen Live-TTS-Test setzen.
- Zwei bis drei Piper-Stimmen pruefen und danach `offline vs. Cloud-TTS` entscheiden.
- `.git_broken_5/` (Reste eines fruehen, abgebrochenen git-init-Versuchs) liegt noch im Arbeitsordner, ist per `.gitignore` von der Versionierung ausgeschlossen. Kann bei Gelegenheit manuell aufgeraeumt werden, wurde bewusst nicht geloescht (keine destruktive Aktion ohne Rueckfrage).

### Feature-TODOs (naechste Roadmap-Bausteine, NICHT jetzt umsetzen)
- `v0.7`, weitere Kap.-17-Bausteine: Treiber pruefen/aktualisieren, Dienste starten/stoppen, Autostart *verwalten* (Schreibzugriff, ueber Phase-1-Anzeige hinaus), Temp-/Festplatten-Bereinigung - keine Priorisierung, kein Code. Alle vier bedeuten einen Sicherheitsstufen-Sprung ueber Stufe 0 hinaus (mindestens Stufe 2).
- Security-Log in die Ereignisprotokoll-Analyse aufnehmen - bewusst nicht in Phase 2 (sensibler, oft rechteeingeschraenkt, ADR-021), eigene spaetere Diskussion.
- Dritter KI-Verwender: falls ein weiteres Modul KI-Zugriff braucht, `configure()`-Duplizierung (`reports.py`/`monitor.py`) zu einer gemeinsamen Abstraktion zusammenfuehren pruefen (Wolfgangs Entscheidung bei ADR-020) - `monitor.py` hat inzwischen zwei Commands (ADR-020, ADR-021), die sich dieselbe Infrastruktur teilen, weiterhin nur zwei Module (`reports.py`, `monitor.py`) insgesamt.
- `Deinstallieren` (winget) - im Handbook (Kap. 17) genannt, noch nicht priorisiert; braucht eigene Sicherheitsstufen-Bewertung.
- Generalisierung "Tabellen-Auswertung" -> allgemeine Excel-/Report-Analyse - im Handbook als Backlog-Punkt dokumentiert (Kap. 29, v3.5), NICHT umsetzen ohne explizite Priorisierung, kein Refactoring der bestehenden v0.5-Commands.
- Erweiterung des Telegram-Befehlsumfangs (z. B. Excel/Reports/KPI/PC-Analyse, evtl. Sicherheitsstufe-2-Aktionen mit einer echten `TelegramSpeech.listen()`-Implementierung statt fail-closed) - keine Priorisierung.
- Web-Interface (FastAPI+ngrok) und WireGuard VPN (Handbook Kap. 16) - ausdruecklich als Alternativen dokumentiert, keine eigene Priorisierung.
- Eigene App (Handbook Kap. 16) - explizit als Langzeitziel markiert.
- Alias-Liste fuer Standort-/Ist-Wert-Spalten (ADR-016) erweitern, sobald sich an echten Reports zeigt, dass andere Spaltennamen gebraucht werden.
- Power BI - im Handbook selbst (Kap. 29 Backlog) als optionale Unternehmensintegration/spaeterer Baustein dokumentiert.
- Eigene `AIEngine.summarize_report()`-Methode - nur pruefen, falls die Wiederverwendung von `answer()` sich als inhaltlich unzureichend erweist (ADR-015).
- Excel Phase 2 (Schreiben, Formatieren, Power Query, Makros) - explizit nicht Teil von Phase 1 (ADR-013/ADR-014).
- `.xls` (Legacy-Format) - von `openpyxl` nicht unterstuetzt, keine eigene Priorisierung.
- Outlook-Integration - explizit aus v0.5 ausgeklammert (Handbook, Kap. 27), eigene, spaetere Priorisierung noetig.
- Verknuepfungsziele im Startup-Ordner aufloesen (bräuchte `pywin32`) - bewusst nicht in Phase 1, nur Dateinamen (ADR-020).
- Temperatur-Monitoring - unter Windows von `psutil` nicht unterstuetzt (Plattform-Limitierung, kein Priorisierungsthema).

Im Code wurden keine `TODO`-/`FIXME`-Marker gefunden.

## Latest ADR
`ADR-021 - Windows-Ereignisprotokoll analysieren (v0.7 Phase 2) - wevtutil statt neuer Abhaengigkeit`

## Latest Architecture Change
`commands/monitor.py::AnalyzeEventLogCommand` (Intent `analyze_event_log`, Sicherheitsstufe 0) ist der dritte Command mit direktem `AIEngine`-Zugriff (nach `analyze_report`/`calculate_kpi`, `analyze_pc`) - nutzt die aus ADR-020 bereits vorhandene `configure()`-Infrastruktur in `commands/monitor.py`, keine neue Duplizierung, keine Aenderung an `main.py` noetig. Datenquelle `wevtutil` (Windows-Bordmittel) ueber `subprocess` statt einer neuen Abhaengigkeit wie `pywin32`; `/f:RenderedXml`-Ausgabeformat fuer sprachversions-unabhaengiges Parsen (`xml.etree.ElementTree`). Keine Aenderung an `core/ai.py`, `core/planner.py`, `core/tool_manager.py`, `executor/executor.py` oder anderen `commands/*.py`-Dateien (per `git diff --stat` verifiziert leer).

## Known Limitations
- Langzeitgedaechtnis funktioniert nur auf Zuruf; es gibt keine automatische Fakten-Extraktion.
- `listen()` (Konsole) bleibt Konsole; Mikrofon/Wake-Word ist weiterhin nicht umgesetzt.
- Kokoro TTS unterstuetzt aktuell kein Deutsch.
- Fehlt ein TTS-Modell oder Backend, faellt Jarvis auf reine Konsolenausgabe zurueck.
- `system_status` liest keine Temperatur aus (`psutil` unterstuetzt das unter Windows nicht) - unveraendert seit ADR-011, `analyze_pc` deckt Festplattenbelegung inzwischen ab.
- `install_program` deckt kein "Deinstallieren" ab (bewusst nicht in v0.4-Scope, siehe ADR-012) und braucht `winget` (App Installer aus dem Microsoft Store) auf dem Zielsystem.
- `read_excel`/`analyze_report`/`calculate_kpi` lesen nur `.xlsx`/`.xlsm` (kein `.xls`), nur Werte (keine Formeln/Formatierung/Makros), pro Arbeitsblatt auf 500 Zeilen begrenzt.
- `analyze_report`/`analyze_pc` liefern eine KI-generierte Analyse, die falsch liegen kann - deshalb Pflicht-Disclaimer in jeder Antwort (ADR-015/ADR-020).
- `calculate_kpi` erkennt Standort-/Ist-Wert-Spalten nur ueber eine feste Alias-Liste (ADR-016).
- `telegram_main.py`: nur vier Intents erreichbar (weder `analyze_pc` noch die v0.5-Commands), kein gleichzeitiger Betrieb mit der Konsole, `TelegramSpeech.listen()` bewusst nicht funktionsfaehig (fail-closed, ADR-018).
- `analyze_pc`: Windows-exklusiv (klarer Fehler auf anderen Plattformen), keine Aufloesung von Startup-Ordner-Verknuepfungszielen (nur Dateinamen), kein Ereignisprotokoll (ADR-020, jetzt separat durch `analyze_event_log` abgedeckt, ADR-021).
- `analyze_event_log`: Windows-exklusiv (klarer Fehler auf anderen Plattformen), nur `System`/`Application` (kein Security-Log), nur die letzten 20 Eintraege je Log, Meldungstext auf 200 Zeichen gekuerzt, kein Loeschen/Reparieren (ADR-021).

## Git
Ein einzelner, ehrlicher Initial-Commit aus dem aktuellen Arbeitsstand (kein rekonstruierter Verlauf aus alten ZIP-Staenden), getaggt als `v0.4`. Danach je ein Commit fuer Handbook v3.3/ADR-013, Excel-Lesen (ADR-014), Tabellen-Auswertung (ADR-015), die Power-BI-Scope-Entscheidung, KPI (ADR-016) und die v0.5-Abschlusspruefung, getaggt als `v0.5`. Danach Commits fuer Handbook v3.4/ADR-017, Telegram-Fernzugriff (ADR-018), getaggt als `v0.6`, danach Handbook v3.5/ADR-019 inkl. einer kleinen Kap.-2-Konsistenzkorrektur. Danach Commit `48f0f83` fuer PC-Analyse (v0.7 Phase 1, ADR-020). Fruehere Versionen (v0.1-v0.3) existieren nur als Text in `docs/CHANGELOG.md`/`docs/logbook.md`, nicht als eigene Git-Commits/Tags (keine kuenstliche Fake-Historie). Die Ereignisprotokoll-Analyse (v0.7 Phase 2, ADR-021, dieser Stand) ist noch nicht committed. Kein neuer Tag - `v0.7` wird erst bei Abschluss aller vorgesehenen v0.7-Bausteine getaggt.

## Product Owner Rules
- Product Owner entscheidet Prioritaeten.
- KI darf Umsetzung vorschlagen, aber keine Roadmap aendern.
- Bei Konflikt gewinnt das Master-Handbook.
