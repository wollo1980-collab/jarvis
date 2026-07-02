# PROJECT STATE

Stand: 2026-07-02
Quelle: `README.md`, `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_7.docx`, `docs/logbook.md`, `docs/CHANGELOG.md`, `docs/adr/*.md`

**Hinweis (ab v3.6, siehe Handbook Kap. 19):** Dieses Dokument ist ein temporärer Arbeitsbereich zwischen zwei Handbook-Versionen, keine dauerhafte Wissensquelle. Nach jedem Konsolidierungsprozess wird es auf den aktuellen Projektstatus zurückgebaut - dauerhaft gültige Entscheidungen (Roadmap, Backlog, Governance-Regeln) leben im Handbook, nicht hier.

## Current Version
`v0.7` - abgeschlossen, konsolidiert (Handbook v3.6) und getaggt (`v0.7`, zeigt auf `a7eb86d`). `v0.4`/`v0.5`/`v0.6`/`v0.7` sind damit alle abgeschlossen und getaggt.

Danach abgeschlossen: der **Infrastruktur-/Runtime-Baustein zwischen v0.7 und v0.8** (Jarvis-Runtime v1/v2, Single-Instance-Schutz, Jarvis-Eigenstart; ADR-024 bis ADR-028) - bewusst ohne eigene vX.Y-Versionsnummer und ohne Git-Tag. Mit Handbook v3.7 ist dieser Baustein konsolidiert; die dauerhaft gültige Architektur steht im Handbook (Kap. 7 „Runtime & Kanäle", Kap. 13 Roadmap).

## Status
Umgesetzt in v0.7 "PC-Admin" (Details: `docs/CHANGELOG.md`, ADRs):
- **PC-Analyse** (`analyze_pc`, Sicherheitsstufe 0, ADR-020)
- **Ereignisprotokoll-Analyse** (`analyze_event_log`, Sicherheitsstufe 0, ADR-021)
- **Autostart-Verwaltung** (`disable_/enable_autostart_entry`, Sicherheitsstufe 2, Benutzer-Scope, ADR-022)
- **Temp-Bereinigung** (`analyze_/clean_temp_files`, Sicherheitsstufe 0/3, Benutzer-Scope, ADR-023) - inkl. optionalem `preview()`-Hook in `executor/executor.py` (rückwärtskompatibel)

Umgesetzt im Infrastruktur-/Runtime-Baustein (zwischen v0.7 und v0.8, jetzt im Handbook Kap. 7/13 dauerhaft dokumentiert):
- **Jarvis-Runtime** (`jarvis_runtime.py`) - koordinierender Einstiegspunkt, `queue.Queue` + ein Worker-Thread, `submit(text, reply_callback)`, `ConsoleDummyChannel` (ADR-024/025)
- **Single-Instance-Schutz** (`core/single_instance.py`) - `jarvis.lock` pro `memory_dir`, atomar + `msvcrt.locking()` (ADR-026)
- **TelegramChannel** (`telegram_channel.py`) - erster konsolenfreier Runtime-Kanal, Whitelist aus `telegram_main.py` wiederverwendet, Asyncio-Brücke (ADR-027)
- **Jarvis-Eigenstart** (`enable_/disable_jarvis_autostart` in `commands/monitor.py`) - Windows-Autostart über HKCU Run-Key, Ziel `pythonw.exe` (ADR-028)

Bewusst nicht enthalten und ins Handbook-Backlog (Kap. 29) verschoben: Treiber, Dienste, HKLM-Autostart-Erweiterung, Papierkorb, `C:\Windows\Temp`, Browser-Cache/-Profile sowie abstraktes Channel-Interface, Runtime-UI/Tray/Wake-Word, Eigenstart-Pfadpflege.

Tests: `280 / 280` grün (225 aus v0.7 + 55 aus dem Infrastruktur-/Runtime-Baustein: 11 Runtime v1 (ADR-025) + 13 Single-Instance-Schutz (ADR-026) + 15 Runtime v2/TelegramChannel (ADR-027) + 16 Jarvis-Eigenstart (ADR-028)).

Aus v0.6/v0.5/v0.4 weiterhin gültig: Telegram-Fernzugriff (ADR-018), Excel-Lesen/Tabellen-Auswertung/KPI (ADR-014/015/016), Kurz-/Langzeitgedächtnis (ADR-009), PC-Grundsteuerung (ADR-011/012) - siehe Handbook Kap. 13/27 für den vollständigen Roadmap-Stand.

## Next Planned Version
`v0.8 "Multi-KI"` (Handbook Kap. 13: "Claude + GPT + Copilot orchestrieren") ist der nächste geplante Baustein - noch nicht begonnen, kein technischer Vorschlag erstellt. Der Infrastruktur-/Runtime-Baustein davor ist abgeschlossen und konsolidiert (Handbook v3.7).

## Tests
Letzter Check am 2026-07-02: `pytest tests -v` mit zusätzlichem `PYTHONPATH`.

### Test Status
`280 / 280` bestanden

### Known Failure
Keiner aktuell.

## Offene Aufgaben

### Technische TODOs (Definition of Done / Betrieb, kein neuer Scope)
- Manueller Live-Test der übrigen Kernfunktionen mit echtem API-Key auf dem echten Windows-Rechner (Definition of Done, Handbook Kap. 28) - bisher nur automatisiert/gemockt getestet. `install_program` real ausführen ist ein bewusster, expliziter Schritt und sollte gezielt vom Product Owner freigegeben/begleitet werden.
- Manueller Smoke-Test der Jarvis-Runtime mit echtem Bot-Token (TelegramChannel) sowie ein realer Jarvis-Eigenstart-Test nach Windows-Anmeldung - bisher nur automatisiert/gemockt getestet (Definition of Done, Handbook Kap. 28).
- Piper-Sprachmodell herunterladen und `tts_enabled: true` für einen Live-TTS-Test setzen.
- `.git_broken_5/` (Reste eines frühen, abgebrochenen git-init-Versuchs) liegt noch im Arbeitsordner, per `.gitignore` ausgeschlossen - bewusst nicht gelöscht (keine destruktive Aktion ohne Rückfrage).

### Feature-TODOs (nächste Roadmap-Bausteine, NICHT jetzt umsetzen)
Die Roadmap- und Backlog-Bausteine leben jetzt vollständig im Handbook (Kap. 13 Roadmap, Kap. 29 Backlog) - u. a. v0.8 „Multi-KI", abstraktes Channel-Interface, Runtime-UI/Tray/Wake-Word, Jarvis-Eigenstart-Pfadpflege. Hier nur technische Detail-Notizen, die (noch) keinen eigenen Handbook-Backlog-Eintrag brauchen:
- Dritter KI-Verwender: falls ein weiteres Modul KI-Zugriff braucht, `configure()`-Duplizierung (`reports.py`/`monitor.py`) zu einer gemeinsamen Abstraktion zusammenführen prüfen (Wolfgangs Entscheidung bei ADR-020).
- Den `preview()`-Hook (ADR-023) für weitere schreibende PC-Admin-Commands (Dienste, Treiber) nutzen, sobald diese umgesetzt werden.
- Alias-Liste für Standort-/Ist-Wert-Spalten (ADR-016) erweitern, sobald sich an echten Reports zeigt, dass andere Spaltennamen gebraucht werden.
- Eigene `AIEngine.summarize_report()`-Methode - nur prüfen, falls die Wiederverwendung von `answer()` sich als inhaltlich unzureichend erweist (ADR-015).
- Verknüpfungsziele im Startup-Ordner auflösen (bräuchte `pywin32`) - bewusst nicht in Phase 1, nur Dateinamen (ADR-020).

Im Code wurden keine `TODO`-/`FIXME`-Marker gefunden.

## Latest ADR
`ADR-028 - Jarvis-Eigenstart - Windows-Autostart über jarvis_runtime.py`

## Latest Architecture Change
Infrastruktur-/Runtime-Baustein zwischen v0.7 und v0.8 (ADR-024 bis ADR-028): neuer koordinierender Einstiegspunkt `jarvis_runtime.py` (queue.Queue + Worker-Thread, `submit()`+optionaler `plan_filter`), `core/single_instance.py` (Single-Instance-Schutz pro `memory_dir`), `telegram_channel.py` (TelegramChannel als erster echter Runtime-Kanal, Asyncio-Brücke) sowie `enable_/disable_jarvis_autostart` in `commands/monitor.py` (Windows-Autostart über `pythonw.exe`). `main.py`/`telegram_main.py` bleiben als eigenständige Einstiegspunkte erhalten (Koexistenz). Dauerhafte Architektur jetzt im Handbook Kap. 7 „Runtime & Kanäle". Details: ADR-024 bis ADR-028.

## Known Limitations
- Langzeitgedächtnis funktioniert nur auf Zuruf; keine automatische Fakten-Extraktion.
- Mikrofon/Wake-Word weiterhin nicht umgesetzt.
- Kokoro TTS unterstützt aktuell kein Deutsch.
- `system_status`/`analyze_pc`: keine Temperatur (psutil-Limitierung unter Windows).
- `read_excel`/`analyze_report`/`calculate_kpi`: nur `.xlsx`/`.xlsm`, nur Werte, 500 Zeilen/Blatt.
- `telegram_main.py`: nur vier Intents erreichbar, kein gleichzeitiger Betrieb mit der Konsole, `TelegramSpeech.listen()` fail-closed (ADR-018).
- `analyze_pc`/`analyze_event_log`/`disable_/enable_autostart_entry`/`analyze_/clean_temp_files`: alle Windows-exklusiv, jeweiliger Scope siehe Handbook Kap. 17 (Umsetzungsstand-Annotationen).
- `jarvis_runtime.py`: kein UI/Tray/Wake-Word, kein abstraktes Channel-Interface. `ConsoleDummyChannel` bleibt für unbeaufsichtigten Betrieb ungeeignet (blockiert auf `input()`) - wird beim Jarvis-Eigenstart (`pythonw.exe`) deshalb gar nicht erst gestartet; Telegram (`telegram_channel.py`) übernimmt dann die Erreichbarkeit.
- Single-Instance-Schutz (ADR-026) schützt nur vor gleichzeitigem *Prozessstart* gegen dasselbe `memory_dir` - kein Schutz gegen externes Löschen der Lock-Datei durch Dritte (Virenscanner, manuelles Löschen), während eine Instanz noch läuft (bekanntes, akzeptiertes Restrisiko).
- `telegram_main.py` (eigenständig) und `TelegramChannel` (über die Runtime) dürfen nicht gleichzeitig mit demselben Bot-Token laufen - Telegram erlaubt pro Bot nur eine aktive Long-Polling-Verbindung. Der Single-Instance-Schutz verhindert das im Normalfall bereits indirekt (gleiches `memory_dir`), ist aber kein expliziter Schutz für dieses Szenario.
- Jarvis-Eigenstart (ADR-028): fester HKCU-Run-Key-Eintragsname `"Jarvis"` setzt eine einzige Installation pro Windows-Benutzerkonto voraus - mehrere parallele Projektkopien würden sich beim Eintrag gegenseitig überschreiben. Veraltete Registry-Pfade nach einem Projekt-/Interpreter-Umzug werden nicht automatisch erkannt/repariert - Selbstbedienung (erneutes `enable_jarvis_autostart`) reicht laut ADR-028 aus, bleibt aber ein bewusst akzeptiertes Restrisiko bis dahin.

## Git
Initial-Commit getaggt als `v0.4`. Danach Handbook v3.3/ADR-013, Excel-Lesen (ADR-014), Tabellen-Auswertung (ADR-015), Power-BI-Scope-Entscheidung, KPI (ADR-016), v0.5-Abschluss, getaggt als `v0.5`. Danach Handbook v3.4/ADR-017, Telegram-Fernzugriff (ADR-018), getaggt als `v0.6`, danach Handbook v3.5/ADR-019 inkl. Kap.-2-Konsistenzkorrektur. Danach `48f0f83` (PC-Analyse, ADR-020), `5f330fb` (Ereignisprotokoll-Analyse, ADR-021), `efe067f` (PROJECT_STATE-Korrektur), `b108c06` (Autostart-Verwaltung, ADR-022), `a765c9d` (Temp-Bereinigung, ADR-023), `920e32c` (v0.7-Abschlussdokumentation), `a7eb86d` (Handbook v3.6, Entwicklungsprozess-Konsolidierung) - getaggt als `v0.7`.

Infrastruktur-/Runtime-Baustein (zwischen v0.7 und v0.8, alle ungetaggt - kein eigener Versionsblock): `a085c49` (ADR-024-Dokumentation), `057706d` (Kap.-19-Architekturrichtung), `95e5af9` (Jarvis-Runtime v1, ADR-025), `987ed0b` (Single-Instance-Schutz, ADR-026), `3b05a95` (ADR-027-Dokumentation), `7f9ccb8` (Runtime v2/TelegramChannel, ADR-027), `f5c0a06` (ADR-028-Dokumentation), `3fc13e1` (Jarvis-Eigenstart, ADR-028). Die Konsolidierung auf Handbook v3.7 ist noch nicht committed. Frühere Versionen (v0.1-v0.3) existieren nur als Text in `docs/CHANGELOG.md`/`docs/logbook.md`.
