# PROJECT STATE

Stand: 2026-07-02
Quelle: `README.md`, `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_5.docx`, `docs/logbook.md`, `docs/CHANGELOG.md`, `docs/adr/*.md`

## Current Version
`v0.6` - abgeschlossen und als Tag `v0.6` gesetzt (zusammen mit `v0.4`, `v0.5`). Handbook wurde danach gemäß Kap. 2 auf `v3.5` aktualisiert. `v0.7` ist noch nicht begonnen - Planung steht noch aus.

## Status
`v0.3`, `v0.4`, `v0.5` und `v0.6` sind abgeschlossen und getaggt (`v0.4`, `v0.5`, `v0.6`).
`v0.6 "Handy"` umgesetzt:
- **Telegram-Fernzugriff** (`telegram_main.py`, ADR-018): separater Einstiegspunkt (Long-Polling über `python-telegram-bot`, kein Webhook/FastAPI/ngrok). Nur `chat`/`remember_fact`/`forget_fact`/`system_status` erreichbar (Sicherheitsstufe 0 + ausgewählte Stufe-1-Speicher-Interaktionen); Stufe 2/3/4 über zwei unabhängige Mechanismen gesperrt (Intent-Whitelist + `requires_confirmation`-Check). Mehrschritt-Pläne mit einem nicht erlaubten Schritt werden komplett abgelehnt. Autorisierung/Secrets ausschließlich über `JARVIS_TELEGRAM_BOT_TOKEN`/`JARVIS_TELEGRAM_ALLOWED_CHAT_ID` (Env-Var). Kein gleichzeitiger Betrieb von Konsole und Telegram. **Keine Änderung an `core/ai.py`, `core/planner.py`, `core/tool_manager.py`, `executor/executor.py`, `main.py` oder `commands/*.py`** (per `git diff --stat` verifiziert).
- **Manueller Smoke-Test bestanden** (02.07.2026, vom Product Owner mit echtem Bot-Token/Chat durchgeführt und ausdrücklich bestätigt) - erfüllt die allgemeinen Definition-of-Done-Kriterien aus Handbook Kap. 14/15/28 (Smoke Test, manueller Test aller Kernfunktionen).
- Web-Interface (FastAPI+ngrok), WireGuard VPN und Eigene App (Handbook Kap. 16) sind bewusst NICHT umgesetzt - alternative bzw. spätere Lösungswege, keine Pflichtbestandteile von v0.6 (jetzt auch im Handbook selbst so festgehalten, v3.5).
- Tests: `152 / 152` grün.

Aus v0.5 weiterhin gültig:
- **Excel-Lesen, Phase 1** (`commands/excel.py::ReadExcelCommand`, ADR-014), **Tabellen-Auswertung** (`commands/reports.py::AnalyzeReportCommand`, ADR-015), **KPI** (`commands/reports.py::CalculateKpiCommand`, ADR-016). Power BI weiterhin nicht enthalten (Handbook Kap. 29 Backlog).

Aus v0.4 weiterhin gültig:
- **Kurz-/Langzeitgedaechtnis** (Handbook Kap. 9/13/27): Kurzzeit-Anteil (`memory/store.py::JsonMemoryStore`) persistiert Gespraechsverlauf tagesuebergreifend; Langzeit-Anteil (`memory/long_term.py::LongTermMemory`, ADR-009), nur auf ausdruecklichen Zuruf.
- **PC-Grundsteuerung** (Kap. 17/27): oeffnen (`open_program`), ueberwachen (`system_status`, ADR-011), installieren (`install_program`, ADR-012).

## Current Development Phase
`v0.6` abgeschlossen. Laut Handbook Kap. 13 ist die naechste Roadmap-Phase `v0.7 "PC-Admin"` (System-Analyse, Treiber, Reinigung). Diese Version ist noch NICHT begonnen - Planung steht als naechster gemeinsamer Schritt mit dem Product Owner an, noch kein Code, noch kein technischer Vorschlag.

## Next Planned Version
`v0.7 "PC-Admin"` laut Handbook-Roadmap (Kap. 13): Schwerpunkt System-Analyse, Treiber, Reinigung (Lerninhalte: Windows APIs, winget). Siehe auch Kap. 17 (PC-Steuerung) fuer weitere geplante Faehigkeiten (Treiber pruefen/aktualisieren, Dienste starten/stoppen, Autostart verwalten, Temp-/Festplatten-Bereinigung, Windows-Ereignisprotokoll) und die "System-Analyst-Vision" dort. Noch KEIN technischer Vorschlag erarbeitet, noch keine Freigabe, noch kein Code.

## Next Goal According To Handbook
`v0.6` (Kap. 13/16/27, praezisiert in v3.5/ADR-019) ist inhaltlich vollstaendig und im Handbook selbst als abgeschlossen markiert: Telegram-Bot/Fernzugriff umgesetzt (ADR-018), Web-Interface/WireGuard VPN/Eigene App ausdruecklich als nicht-verpflichtende Alternativen bzw. Langzeitziel dokumentiert.
Naechster Baustein laut Roadmap (Kap. 13): `v0.7 PC-Admin (System-Analyse, Treiber, Reinigung)`.
Vor jedem weiteren Baustein gilt weiterhin: Handbook-Pruefung (Scope/DoD/Architektur/Sicherheitsmodell) + technischer Vorschlag zur Freigabe durch den Product Owner, bevor Code geschrieben wird (Muster aus ADR-013 bis ADR-019).

## Handbook-Update: v3.4 -> v3.5 (02.07.2026, ADR-019)
**Anlass:** Abschluss von v0.6 (Tag `v0.6` gesetzt, manueller Smoke-Test vom Product Owner bestaetigt) - gemaess Kap. 2 (Handbook wird nur zwischen zwei Versionen geaendert) war der Zeitpunkt fuer den Nachzug erreicht.
**Aenderungen:** Kap. 13 (Roadmap) aktualisiert (v0.6 als abgeschlossen markiert, Lerninhalte-Spalte auf das tatsaechlich Genutzte korrigiert), Kap. 16 (Telegram-Bot-Status auf "Umgesetzt", neue Praezisierung: Web-Interface/WireGuard VPN sind Alternativen, kein Pflichtbestandteil), Kap. 10 (neues, dauerhaftes Fernzugriff-Sicherheitsprinzip fuer alle kuenftigen Fernzugriffskanaele), Kap. 27 (Praezisierung v3.5), Kap. 28 (neuer v0.6-DoD-Abschnitt), Kap. 29 (Backlog um die Generalisierung der Post-Arbeitsmodule ergaenzt - Wolfgangs Hinweis vom 01.07.2026, reine Richtungsdokumentation, keine Architekturaenderung).
**Details:** ADR-019 (docs/adr/ADR-019.md).

## Tests
Letzter Check am 2026-07-02: `pytest tests -v` mit zusaetzlichem `PYTHONPATH`.

### Test Status
`152 / 152` bestanden

### Known Failure
Keiner aktuell. `tests/test_integration.py::test_end_to_end_tool_execution` (vormals bekannter, Windows-spezifischer Fehlschlag wegen `os.startfile` vs. gemocktem POSIX-Pfad) lief in den letzten Durchlaeufen gruen durch. Falls der Fehlschlag erneut auftritt, siehe `docs/logbook.md` (Eintraege 2026-07-01) fuer die dokumentierte Ursache.

## Offene Aufgaben

### Technische TODOs (Definition of Done / Betrieb, kein neuer Scope)
- Manueller Live-Test der uebrigen Kernfunktionen mit echtem API-Key auf dem echten Windows-Rechner (Definition of Done, Kap. 28) - bisher nur automatisiert/gemockt getestet: `system_status`, `install_program`, `remember_fact`/`forget_fact`, `read_excel`, `analyze_report`, `calculate_kpi` (Telegram-Fernzugriff ist seit 02.07.2026 real getestet, siehe oben). Insbesondere `install_program` real ausfuehren ist ein bewusster, expliziter Schritt (installiert wirklich Software) und sollte gezielt vom Product Owner freigegeben/begleitet werden.
- Piper-Sprachmodell herunterladen und `tts_enabled: true` fuer einen Live-TTS-Test setzen.
- Zwei bis drei Piper-Stimmen pruefen und danach `offline vs. Cloud-TTS` entscheiden.
- `.git_broken_5/` (Reste eines fruehen, abgebrochenen git-init-Versuchs) liegt noch im Arbeitsordner, ist per `.gitignore` von der Versionierung ausgeschlossen. Kann bei Gelegenheit manuell aufgeraeumt werden, wurde bewusst nicht geloescht (keine destruktive Aktion ohne Rueckfrage).

### Feature-TODOs (naechste Roadmap-Bausteine, NICHT jetzt umsetzen)
- `v0.7 PC-Admin`: System-Analyse, Treiber, Reinigung (Kap. 13/17) - Planung noch nicht begonnen, keine Freigabe/Code.
- Generalisierung "Tabellen-Auswertung" -> allgemeine Excel-/Report-Analyse - jetzt im Handbook selbst als Backlog-Punkt dokumentiert (Kap. 29, v3.5), NICHT umsetzen ohne explizite Priorisierung, kein Refactoring der bestehenden v0.5-Commands.
- Erweiterung des Telegram-Befehlsumfangs (z. B. Excel/Reports/KPI, evtl. Sicherheitsstufe-2-Aktionen mit einer echten `TelegramSpeech.listen()`-Implementierung statt fail-closed) - keine Priorisierung, kein Handbook-Auftrag dafuer.
- Web-Interface (FastAPI+ngrok) und WireGuard VPN (Handbook Kap. 16) - ausdruecklich als Alternativen dokumentiert, keine eigene Priorisierung.
- Eigene App (Handbook Kap. 16) - explizit als Langzeitziel markiert.
- Alias-Liste fuer Standort-/Ist-Wert-Spalten (ADR-016) erweitern, sobald sich an echten Reports zeigt, dass andere Spaltennamen gebraucht werden.
- Power BI - im Handbook selbst (Kap. 29 Backlog) als optionale Unternehmensintegration/spaeterer Baustein dokumentiert.
- Eigene `AIEngine.summarize_report()`-Methode - nur pruefen, falls die Wiederverwendung von `answer()` bei `analyze_report` sich als inhaltlich unzureichend erweist (ADR-015).
- Excel Phase 2 (Schreiben, Formatieren, Power Query, Makros) - explizit nicht Teil von Phase 1 (ADR-013/ADR-014), keine Priorisierung dafuer.
- `.xls` (Legacy-Format) - von `openpyxl` nicht unterstuetzt, keine eigene Priorisierung bisher.
- Outlook-Integration - explizit aus v0.5 ausgeklammert (Handbook, Kap. 27), eigene, spaetere Priorisierung noetig.
- `Deinstallieren` (winget) - im Handbook (Kap. 17) genannt, aber nicht Teil der v0.4-Priorisierung (Kap. 27, siehe ADR-012); braucht eigene Priorisierung und vermutlich eigene Sicherheitsstufen-Bewertung.
- Festplatten-Ueberwachung/-Bereinigung - separater Handbook-Punkt (Kap. 17); voraussichtlich Teil von v0.7, noch nicht priorisiert.
- Temperatur-Monitoring - unter Windows von `psutil` nicht unterstuetzt (Plattform-Limitierung, kein Priorisierungsthema).

Im Code wurden keine `TODO`-/`FIXME`-Marker gefunden.

## Latest ADR
`ADR-019 - Handbook v3.5: v0.6-Abschluss, Fernzugriff-Sicherheitsprinzip, Backlog-Ergaenzung`

## Latest Architecture Change
Keine Code-Architekturaenderung - ADR-019 ist eine reine Dokumentations-/Governance-Aenderung (Handbook-Update). Letzte Code-Architekturaenderung bleibt ADR-018 (`telegram_main.py`, separater Einstiegspunkt, Intent-Whitelist + `requires_confirmation`-Check fuer Fernzugriff).

## Known Limitations
- Langzeitgedaechtnis funktioniert nur auf Zuruf; es gibt keine automatische Fakten-Extraktion.
- `listen()` (Konsole) bleibt Konsole; Mikrofon/Wake-Word ist weiterhin nicht umgesetzt.
- Kokoro TTS unterstuetzt aktuell kein Deutsch.
- Fehlt ein TTS-Modell oder Backend, faellt Jarvis auf reine Konsolenausgabe zurueck.
- Systemueberwachung liest keine Temperatur aus (`psutil` unterstuetzt das unter Windows nicht) und keine Festplattenbelegung (separater, fuer v0.7 vorgesehener Handbook-Punkt).
- `install_program` deckt kein "Deinstallieren" ab (bewusst nicht in v0.4-Scope, siehe ADR-012) und braucht `winget` (App Installer aus dem Microsoft Store) auf dem Zielsystem.
- `read_excel`/`analyze_report`/`calculate_kpi` lesen nur `.xlsx`/`.xlsm` (kein `.xls`), nur Werte (keine Formeln/Formatierung/Makros), pro Arbeitsblatt auf 500 Zeilen begrenzt.
- `analyze_report` liefert eine KI-generierte Analyse, die falsch liegen kann - deshalb Pflicht-Disclaimer in jeder Antwort (ADR-015).
- `calculate_kpi` erkennt Standort-/Ist-Wert-Spalten nur ueber eine feste Alias-Liste (ADR-016).
- `telegram_main.py`: nur vier Intents erreichbar, kein gleichzeitiger Betrieb mit der Konsole, kein automatischer Neustart bei Absturz des Long-Polling-Prozesses, `TelegramSpeech.listen()` ist bewusst nicht funktionsfaehig implementiert (fail-closed) - eine echte Bestaetigungsabfrage per Telegram existiert noch nicht (ADR-018).

## Git
Ein einzelner, ehrlicher Initial-Commit aus dem aktuellen Arbeitsstand (kein rekonstruierter Verlauf aus alten ZIP-Staenden), getaggt als `v0.4`. Danach je ein Commit fuer Handbook v3.3/ADR-013, Excel-Lesen (ADR-014), Tabellen-Auswertung (ADR-015), die Power-BI-Scope-Entscheidung, KPI (ADR-016) und die v0.5-Abschlusspruefung, getaggt als `v0.5`. Danach Commits fuer Handbook v3.4/ADR-017, Telegram-Fernzugriff (ADR-018), getaggt als `v0.6`. Fruehere Versionen (v0.1-v0.3) existieren nur als Text in `docs/CHANGELOG.md`/`docs/logbook.md`, nicht als eigene Git-Commits/Tags - das im Handbook (Kap. 21) urspruenglich vorgesehene inkrementelle Nachziehen der Commit-Historie wurde bewusst nicht gemacht (keine kuenstliche Fake-Historie). Das Handbook-v3.5-Update (dieser Stand) ist noch nicht committed.

## Product Owner Rules
- Product Owner entscheidet Prioritaeten.
- KI darf Umsetzung vorschlagen, aber keine Roadmap aendern.
- Bei Konflikt gewinnt das Master-Handbook.
