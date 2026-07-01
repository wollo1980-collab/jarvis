# PROJECT STATE

Stand: 2026-07-01
Quelle: `README.md`, `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_2.docx`, `docs/logbook.md`, `docs/CHANGELOG.md`, `docs/adr/*.md`

## Current Version
`v0.4.1` (letzter Patch) - `v0.4` insgesamt ist abgeschlossen und als Tag `v0.4` gesetzt.

## Status
`v0.3` ist abgeschlossen.
`v0.4` ist jetzt ebenfalls abgeschlossen. Umgesetzt:
- **Kurz-/Langzeitgedaechtnis** (Handbook Kap. 9/13/27): Kurzzeit-Anteil (`memory/store.py::JsonMemoryStore`) existiert seit v0.2 und persistiert Gespraechsverlauf tagesuebergreifend in `history.json` (Cap `max_history_entries`, aktiver Kontext 20 Nachrichten); Langzeit-Anteil (`memory/long_term.py::LongTermMemory`, ADR-009) seit v0.4.0, nur auf ausdruecklichen Zuruf.
- **PC-Grundsteuerung** (Kap. 17/27): oeffnen (`open_program`, seit v0.3), ueberwachen (`system_status`, CPU/RAM via psutil, ADR-011), installieren (`install_program`, winget, ADR-012).
- Tests: `101 / 101` gruen.

## Current Development Phase
`v0.4 "Memory + PC"` ist abgeschlossen. Naechste Roadmap-Phase laut Handbook Kap. 13: `v0.5 "Arbeitsmodule"`.

## Next Planned Version
`v0.5` laut Handbook-Roadmap (Kap. 13): Schwerpunkt `Arbeitsmodule` - Tabellen-Auswertung, KPI, Power BI, Excel-Integration (Lerninhalte: Power Query, APIs, RAG). Diese Version ist noch NICHT begonnen - keine neuen Features in dieser Sitzung.

## Next Goal According To Handbook
`v0.4` (Kurz-/Langzeitgedaechtnis + PC-Grundsteuerung) ist inhaltlich vollstaendig - siehe Status oben.
Laut Roadmap (Kap. 13) und Kap. 27 ("Next", v0.4-v0.6) ist der naechste Baustein `v0.5 Arbeitsmodule (Tabellen-Auswertung, KPI, Power BI, Excel)`.
Welcher konkrete v0.5-Teilschritt zuerst kommt, ist eine Product-Owner-Entscheidung (Regel: kein Vorziehen ohne Priorisierung, Kap. 27/29).

## Tests
Letzter Check am 2026-07-01: `pytest tests -v` mit zusaetzlichem `PYTHONPATH`.

### Test Status
`101 / 101` bestanden

### Known Failure
Keiner aktuell. `tests/test_integration.py::test_end_to_end_tool_execution` (vormals bekannter, Windows-spezifischer Fehlschlag wegen `os.startfile` vs. gemocktem POSIX-Pfad) lief im letzten Durchlauf gruen durch. Falls der Fehlschlag erneut auftritt, siehe `docs/logbook.md` (Eintraege 2026-07-01) fuer die dokumentierte Ursache.

## Offene Aufgaben

### Technische TODOs (Definition of Done / Betrieb, kein neuer Scope)
- Manueller Live-Test aller Kernfunktionen mit echtem API-Key auf dem echten Windows-Rechner (Definition of Done, Kap. 28) - bisher nur automatisiert/gemockt getestet: `system_status`, `install_program`, `remember_fact`/`forget_fact`. Insbesondere `install_program` real ausfuehren ist ein bewusster, expliziter Schritt (installiert wirklich Software) und sollte gezielt vom Product Owner freigegeben/begleitet werden.
- Piper-Sprachmodell herunterladen und `tts_enabled: true` fuer einen Live-TTS-Test setzen.
- Zwei bis drei Piper-Stimmen pruefen und danach `offline vs. Cloud-TTS` entscheiden.
- `.git_broken_5/` (Reste eines fruehen, abgebrochenen git-init-Versuchs) liegt noch im Arbeitsordner, ist jetzt per `.gitignore` von der Versionierung ausgeschlossen. Kann bei Gelegenheit manuell aufgeraeumt werden, wurde in dieser Sitzung bewusst nicht geloescht (keine destruktive Aktion ohne Rueckfrage).

### Feature-TODOs (naechste Roadmap-Bausteine, NICHT jetzt umsetzen)
- `v0.5 Arbeitsmodule`: Tabellen-Auswertung, KPI, Power BI, Excel-Integration.
- `v0.6 Handy`: Telegram-Bot, Fernzugriff.
- `Deinstallieren` (winget) - im Handbook (Kap. 17) genannt, aber nicht Teil der v0.4-Priorisierung (Kap. 27, siehe ADR-012); braucht eigene Priorisierung und vermutlich eigene Sicherheitsstufen-Bewertung.
- Festplatten-Ueberwachung/-Bereinigung - separater Handbook-Punkt (Kap. 17), nicht in v0.4 enthalten (siehe ADR-011).
- Temperatur-Monitoring - unter Windows von `psutil` nicht unterstuetzt (Plattform-Limitierung, kein Priorisierungsthema).

Im Code wurden keine `TODO`-/`FIXME`-Marker gefunden.

## Latest ADR
`ADR-012 - PC-Grundsteuerung Teil 2: Programme installieren (winget)`

## Latest Architecture Change
`commands/installer.py::InstallProgramCommand` (Intent `install_program`, Sicherheitsstufe 2) installiert Programme ueber `winget` (Argumentliste, kein Shell-String). Bekannte Namen werden auf exakte Package-IDs abgebildet, sonst Freitext-Suche. Keine Aenderung an `core/ai.py`, `planner.py`, `tool_manager.py` oder `executor.py` noetig (Registry-Mechanismus aus ADR-007).

## Known Limitations
- Langzeitgedaechtnis funktioniert nur auf Zuruf; es gibt keine automatische Fakten-Extraktion.
- `listen()` bleibt Konsole; Mikrofon/Wake-Word ist weiterhin nicht umgesetzt.
- Kokoro TTS unterstuetzt aktuell kein Deutsch.
- Fehlt ein TTS-Modell oder Backend, faellt Jarvis auf reine Konsolenausgabe zurueck.
- Systemueberwachung liest keine Temperatur aus (`psutil` unterstuetzt das unter Windows nicht) und keine Festplattenbelegung (separater, noch nicht priorisierter Handbook-Punkt).
- `install_program` deckt kein "Deinstallieren" ab (bewusst nicht in v0.4-Scope, siehe ADR-012) und braucht `winget` (App Installer aus dem Microsoft Store) auf dem Zielsystem.

## Git
Erster echter Commit dieser Sitzung: ein einzelner, ehrlicher Initial-Commit aus dem aktuellen Arbeitsstand (kein rekonstruierter Verlauf aus alten ZIP-Staenden). Tag `v0.4` markiert diesen Stand. Fruehere Versionen (v0.1-v0.3) existieren nur als Text in `docs/CHANGELOG.md`/`docs/logbook.md`, nicht als eigene Git-Commits/Tags - das im Handbook (Kap. 21) urspruenglich vorgesehene inkrementelle Nachziehen der Commit-Historie wurde bewusst nicht gemacht (keine kuenstliche Fake-Historie).

## Product Owner Rules
- Product Owner entscheidet Prioritaeten.
- KI darf Umsetzung vorschlagen, aber keine Roadmap aendern.
- Bei Konflikt gewinnt das Master-Handbook.
