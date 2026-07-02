# PROJECT STATE

Stand: 2026-07-02
Quelle: `README.md`, `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_6.docx`, `docs/logbook.md`, `docs/CHANGELOG.md`, `docs/adr/*.md`

**Hinweis (ab v3.6, siehe Handbook Kap. 19):** Dieses Dokument ist ein temporärer Arbeitsbereich zwischen zwei Handbook-Versionen, keine dauerhafte Wissensquelle. Nach jedem Konsolidierungsprozess wird es auf den aktuellen Projektstatus zurückgebaut - dauerhaft gültige Entscheidungen (Roadmap, Backlog, Governance-Regeln) leben im Handbook, nicht hier.

## Current Version
`v0.7` - abgeschlossen, konsolidiert (Handbook v3.6) und getaggt (`v0.7`, zeigt auf `a7eb86d`). `v0.4`/`v0.5`/`v0.6`/`v0.7` sind damit alle abgeschlossen und getaggt.

## Status
Umgesetzt in v0.7 "PC-Admin" (Details: `docs/CHANGELOG.md`, ADRs):
- **PC-Analyse** (`analyze_pc`, Sicherheitsstufe 0, ADR-020)
- **Ereignisprotokoll-Analyse** (`analyze_event_log`, Sicherheitsstufe 0, ADR-021)
- **Autostart-Verwaltung** (`disable_/enable_autostart_entry`, Sicherheitsstufe 2, Benutzer-Scope, ADR-022)
- **Temp-Bereinigung** (`analyze_/clean_temp_files`, Sicherheitsstufe 0/3, Benutzer-Scope, ADR-023) - inkl. neuem optionalen `preview()`-Hook in `executor/executor.py` (rückwärtskompatibel)

Bewusst nicht enthalten und ins Handbook-Backlog (Kap. 29) verschoben: Treiber, Dienste, HKLM-Autostart-Erweiterung, Papierkorb, `C:\Windows\Temp`, Browser-Cache/-Profile. Neuer Roadmap-Baustein "Jarvis-Eigenstart" zwischen v0.7 und v0.8 im Handbook (Kap. 13) dokumentiert.

Tests: `236 / 236` grün (225 aus v0.7 + 11 neue aus Jarvis-Runtime v1, ADR-025).

Aus v0.6/v0.5/v0.4 weiterhin gültig: Telegram-Fernzugriff (ADR-018), Excel-Lesen/Tabellen-Auswertung/KPI (ADR-014/015/016), Kurz-/Langzeitgedächtnis (ADR-009), PC-Grundsteuerung (ADR-011/012) - siehe Handbook Kap. 13/27 für den vollständigen Roadmap-Stand.

## Next Planned Version
`v0.7` ist vollständig abgeschlossen (Handbook v3.6, Tag `v0.7`). `v0.8 "Multi-KI"` (Handbook Kap. 13: "Claude + GPT + Copilot orchestrieren") ist der nächste geplante Baustein - noch nicht begonnen, kein technischer Vorschlag erstellt. Vor v0.8 steht architektonisch der Jarvis-Eigenstart-Baustein, dessen Implementierung weiterhin verschoben ist - ob Runtime v1 dafür bereits ausreicht, ist eine eigene, spätere Entscheidung.

## Jarvis-Runtime v1 implementiert (ADR-024/ADR-025, wartet auf künftige Konsolidierung)
Architekturrichtung (ADR-024) und Umsetzung von **Runtime v1** (ADR-025) sind beide dokumentiert und (v1) implementiert - `jarvis_runtime.py` existiert jetzt als Datei. Da das Handbook laut Kap. 2 nur zwischen zwei Hauptversionen geändert wird und v3.6 gerade erst konsolidiert wurde, gelten beide ADRs ab sofort maßgeblich (Kap. 19) und werden erst bei der nächsten Konsolidierung (nach v0.8 oder einem weiteren Runtime-Ausbau) formal ins Handbook übernommen.

**Auslöser:** Wolfgang möchte langfristig ein eigenes UI im Stil von Film-Jarvis (UI, Tray, Wake Word, Telegram, Core sollen koordiniert zusammenspielen). Der Windows-Autostart soll deshalb nicht fest auf `main.py` (Konsolenmodus) gebaut werden.

**Umgesetzt (Runtime v1, ADR-025):**
- **`jarvis_runtime.py`** - dritter, koordinierender Einstiegspunkt. **Koexistenz statt Ablösung:** `main.py`/`telegram_main.py` bleiben unverändert bestehen.
- `JarvisRuntime`: instanziiert den Core-Stack einmalig (gleiche Verdrahtung wie `main.py`), Kanäle kommunizieren nur über `submit(text, reply_callback)`.
- `queue.Queue` + ein Worker-Thread (kein `asyncio`, KISS) - serialisierte Verarbeitung löst das Locking-Problem bei `memory_data/`, ohne `JsonMemoryStore`/`Executor` anzufassen. Worker fängt Fehler pro Nachricht ab, stirbt nicht still.
- `_RuntimeSpeech`: fail-closed Speech-Adapter (Sicherheitsstufe 2/3 sicher abgelehnt, gleiches Prinzip wie `TelegramSpeech`, dupliziert statt importiert).
- `ConsoleDummyChannel`: einziger Kanal in v1, kein Produktivkanal - beweist nur das Runtime-Gerüst.
- **Keine Änderung an `main.py`, `telegram_main.py`, `core/*`, `commands/*`, `executor/*`** (per `git diff --stat` verifiziert).

**Weiterhin offen/nicht Bestandteil von v1:** UI, Tray, Wake-Word, Telegram-Integration in die Runtime, Windows-Autostart, abstraktes Channel-Interface (erst beim zweiten echten Kanal), Jarvis-Eigenstart-Implementierung (Ziel weiterhin `jarvis_runtime.py`).

**Wake-Word-Backlog-Korrektur:** Handbook Kap. 29 nennt fälschlich noch "v0.4" als Prüfzeitpunkt für Wake-Word (Porcupine) - Korrektur bei nächster Konsolidierung fällig, jetzt nur vermerkt (ADR-024).

Details, Begründung und Alternativen: `docs/adr/ADR-024.md` (Architekturrichtung), `docs/adr/ADR-025.md` (Umsetzung v1).

## Tests
Letzter Check am 2026-07-02: `pytest tests -v` mit zusätzlichem `PYTHONPATH`.

### Test Status
`236 / 236` bestanden

### Known Failure
Keiner aktuell.

## Offene Aufgaben

### Technische TODOs (Definition of Done / Betrieb, kein neuer Scope)
- Manueller Live-Test der übrigen Kernfunktionen mit echtem API-Key auf dem echten Windows-Rechner (Definition of Done, Handbook Kap. 28) - bisher nur automatisiert/gemockt getestet. `install_program` real ausführen ist ein bewusster, expliziter Schritt und sollte gezielt vom Product Owner freigegeben/begleitet werden.
- Piper-Sprachmodell herunterladen und `tts_enabled: true` für einen Live-TTS-Test setzen.
- `.git_broken_5/` (Reste eines frühen, abgebrochenen git-init-Versuchs) liegt noch im Arbeitsordner, per `.gitignore` ausgeschlossen - bewusst nicht gelöscht (keine destruktive Aktion ohne Rückfrage).

### Feature-TODOs (nächste Roadmap-Bausteine, NICHT jetzt umsetzen)
- Jarvis-Eigenstart (Windows-Autostart) aufbauend auf `jarvis_runtime.py` - siehe Abschnitt "Jarvis-Runtime v1 implementiert" oben. Kein Code, keine Umsetzung.
- Weitere Runtime-Kanäle (UI, Tray, Wake-Word, Telegram-Integration) und ein abstraktes Channel-Interface - erst bei Bedarf (YAGNI), kein Code, keine Umsetzung.

Vollständige, aktuelle Liste jetzt im Handbook (Kap. 13 Roadmap, Kap. 29 Backlog) - hier nur technische Detail-Notizen, die (noch) keinen eigenen Handbook-Backlog-Eintrag brauchen:
- Dritter KI-Verwender: falls ein weiteres Modul KI-Zugriff braucht, `configure()`-Duplizierung (`reports.py`/`monitor.py`) zu einer gemeinsamen Abstraktion zusammenführen prüfen (Wolfgangs Entscheidung bei ADR-020).
- Den `preview()`-Hook (ADR-023) für weitere schreibende PC-Admin-Commands (Dienste, Treiber) nutzen, sobald diese umgesetzt werden.
- Alias-Liste für Standort-/Ist-Wert-Spalten (ADR-016) erweitern, sobald sich an echten Reports zeigt, dass andere Spaltennamen gebraucht werden.
- Eigene `AIEngine.summarize_report()`-Methode - nur prüfen, falls die Wiederverwendung von `answer()` sich als inhaltlich unzureichend erweist (ADR-015).
- Verknüpfungsziele im Startup-Ordner auflösen (bräuchte `pywin32`) - bewusst nicht in Phase 1, nur Dateinamen (ADR-020).

Im Code wurden keine `TODO`-/`FIXME`-Marker gefunden.

## Latest ADR
`ADR-025 - Jarvis-Runtime v1 - minimales Gerüst (Queue, Worker-Thread, Konsolen-Dummy-Kanal)`

## Latest Architecture Change
Neue Datei `jarvis_runtime.py` (dritter, koordinierender Einstiegspunkt, koexistiert mit `main.py`/`telegram_main.py`, keine davon geändert): `JarvisRuntime` verdrahtet den bekannten Core-Stack einmalig und verarbeitet Nachrichten über `queue.Queue` + einen einzelnen Worker-Thread (kein `asyncio`) seriell; `_RuntimeSpeech` ist ein fail-closed Speech-Adapter (Sicherheitsstufe 2/3 bleiben sicher abgelehnt, gleiches Prinzip wie `TelegramSpeech`); `ConsoleDummyChannel` ist der einzige, minimale Kanal in v1. Details: ADR-025 (Umsetzung), ADR-024 (Architekturrichtung).

## Known Limitations
- Langzeitgedächtnis funktioniert nur auf Zuruf; keine automatische Fakten-Extraktion.
- Mikrofon/Wake-Word weiterhin nicht umgesetzt.
- Kokoro TTS unterstützt aktuell kein Deutsch.
- `system_status`/`analyze_pc`: keine Temperatur (psutil-Limitierung unter Windows).
- `read_excel`/`analyze_report`/`calculate_kpi`: nur `.xlsx`/`.xlsm`, nur Werte, 500 Zeilen/Blatt.
- `telegram_main.py`: nur vier Intents erreichbar, kein gleichzeitiger Betrieb mit der Konsole, `TelegramSpeech.listen()` fail-closed (ADR-018).
- `analyze_pc`/`analyze_event_log`/`disable_/enable_autostart_entry`/`analyze_/clean_temp_files`: alle Windows-exklusiv, jeweiliger Scope siehe Handbook Kap. 17 (Umsetzungsstand-Annotationen).
- `jarvis_runtime.py` (v1, ADR-025): rein internes Gerüst - nur `ConsoleDummyChannel`, kein UI/Tray/Wake-Word/Telegram, kein Windows-Autostart, kein abstraktes Channel-Interface.

## Git
Initial-Commit getaggt als `v0.4`. Danach Handbook v3.3/ADR-013, Excel-Lesen (ADR-014), Tabellen-Auswertung (ADR-015), Power-BI-Scope-Entscheidung, KPI (ADR-016), v0.5-Abschluss, getaggt als `v0.5`. Danach Handbook v3.4/ADR-017, Telegram-Fernzugriff (ADR-018), getaggt als `v0.6`, danach Handbook v3.5/ADR-019 inkl. Kap.-2-Konsistenzkorrektur. Danach `48f0f83` (PC-Analyse, ADR-020), `5f330fb` (Ereignisprotokoll-Analyse, ADR-021), `efe067f` (PROJECT_STATE-Korrektur), `b108c06` (Autostart-Verwaltung, ADR-022), `a765c9d` (Temp-Bereinigung, ADR-023), `920e32c` (v0.7-Abschlussdokumentation), `a7eb86d` (Handbook v3.6, Entwicklungsprozess-Konsolidierung) - getaggt als `v0.7`. Frühere Versionen (v0.1-v0.3) existieren nur als Text in `docs/CHANGELOG.md`/`docs/logbook.md`.
