# PROJECT STATE

Stand: 2026-07-03
Quelle: `README.md`, `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_8.docx`, `docs/logbook.md`, `docs/CHANGELOG.md`, `docs/adr/*.md`

**Hinweis (ab v3.6, siehe Handbook Kap. 19):** Dieses Dokument ist ein temporärer Arbeitsbereich zwischen zwei Handbook-Versionen, keine dauerhafte Wissensquelle. Nach jedem Konsolidierungsprozess wird es auf den aktuellen Projektstatus zurückgebaut - dauerhaft gültige Entscheidungen (Roadmap, Backlog, Governance-Regeln, Leitbild) leben im Handbook, nicht hier.

## Current Version
`v0.8 "Multi-KI"` - **Phase 1 + Phase 2 umgesetzt, getestet und committet** (noch kein `v0.8`-Git-Tag: v0.8 ist als Version nicht abgeschlossen, da bewusst kein weiterer Phasenausbau jetzt erfolgt - siehe „Next Planned Version").

Davor abgeschlossen und getaggt: `v0.7` "PC-Admin" (`v0.7` → `a7eb86d`); der **Infrastruktur-/Runtime-Baustein** (ADR-024 bis ADR-028, ohne eigene Versionsnummer/Tag), konsolidiert in Handbook v3.7. `v0.4`/`v0.5`/`v0.6`/`v0.7` sind alle abgeschlossen und getaggt.

Handbook: **v3.8** aktuell (Leitbild/DNA, EBENE 1). v3.7 = Infrastruktur-/Runtime-Baustein.

## Status

Umgesetzt in **v0.8 "Multi-KI"** (Details: `docs/CHANGELOG.md`, ADR-029/030):
- **Phase 1 - Provider-Abstraktion (ADR-029):** `LLMProvider`-Protokoll + `OpenAIProvider` + `ClaudeProvider` in `core/providers.py`; `AIEngine` delegiert den rohen Modellaufruf, `get_plan`/`answer` unverändert. Auswahl per `ai_provider` ("openai"|"claude"), Claude-Default `claude-sonnet-5`. `anthropic` lazy/optional; `ANTHROPIC_API_KEY` nur per Env. `confirmed`-Strip/JSON-Parsing bleiben zentral in `AIEngine`.
- **Phase 2 - deterministischer Provider-Router (ADR-030):** `TaskType` (PLANNING/GENERATION) + `ProviderRouter` in `core/providers.py`, verdrahtet in `core/ai.py` (`get_plan`→PLANNING, `answer`→GENERATION). Neue Config-Felder `planning_provider`/`answer_provider` mit Rückfall auf `ai_provider` (rückwärtskompatibel). Standardprovider eager als Anker, Nicht-Default lazy; Fallback nur um den `chat()`-Aufruf (WARNING). Kein Auto-Routing, keine Laufzeit-Umschaltung.

Sicherheitsfixes (diese Session, ohne eigene Version):
- **`confirmed`-Strip** in `AIEngine.get_plan` (Trust Boundary - ein vom Modell geliefertes `confirmed` kann die Stufe-2/3-Bestätigung nicht mehr umgehen).
- **Bot-Token-Schutz**: `httpx`/`httpcore`-Logger auf WARNING gedämpft (Token nicht mehr im Klartext-Log).
- **TelegramChannel-Shutdown** thread-/eventloop-konform (`stop()` ohne `RuntimeError`).

Handbook-Konsolidierungen seit v0.7:
- **v3.7**: Infrastruktur-/Runtime-Baustein (ADR-024 bis ADR-028).
- **v3.8**: **Leitbild / DNA** (Produktidentität, EBENE 1) - Kap. 0 Leitbild „Wofür Jarvis existiert" (Identität als Haltung) + 9 Produkt-Leitplanken; Angleichungen in Kap. 1/7/26/32; Mission unverändert. Bewusste, dokumentierte Governance-Ausnahme (reine EBENE-1-Konsolidierung mitten in v0.8, ohne Auswirkung auf die technische Code-Basis).

Weiterhin gültig aus v0.7 und davor (Details im Handbook Kap. 13/17/27): PC-Admin (ADR-020-023), Infrastruktur-/Runtime-Baustein (ADR-024-028), Telegram-Fernzugriff (ADR-018), Excel/Tabellen-Auswertung/KPI (ADR-014/015/016), Kurz-/Langzeitgedächtnis (ADR-009), PC-Grundsteuerung (ADR-011/012).

## Next Planned Version
**Nutzwert-Phase „Mit Jarvis leben"** (PO-Entscheidung 03.07.2026). Bewusst **kein** weiterer v0.8-Phasenausbau (z. B. Routing-Intelligenz/Orchestrator) jetzt - stattdessen beweisen, dass das gelegte Fundament einem Menschen *täglich* Last abnimmt. Methode: **Dogfooding-Protokoll** sammeln („Warum muss ich dafür noch eine App öffnen?"), dann gemeinsam die größte Alltagsreibung **end-to-end** bauen, bis echte tägliche Verlässlichkeit. Erfolgsmarke: der erste echte „Ohne Jarvis würde mir das täglich 30 Minuten kosten"-Moment (Handbook Kap. 26). Prozess bewusst **leichter** (keine neue Philosophie/Governance-Zeremonie).

## Tests
Letzter Check am 2026-07-03: volle Suite grün.

### Test Status
`306 / 306` bestanden (venv-Interpreter; für die volle Suite ist ein beschreibbares `--basetemp` nötig, da die Sandbox sonst den System-Temp der `tmp_path`-Fixture blockiert - kein Testdefekt).

### Known Failure
Keiner aktuell.

## Offene Aufgaben

### Technische TODOs (Definition of Done / Betrieb, kein neuer Scope)
- **Live-Test Claude-Provider** mit echtem `ANTHROPIC_API_KEY` auf dem echten Windows-Rechner - bewusst verschobener manueller Verifikationsschritt (kein offener Implementierungsfehler). Pfad ist offline bis zur SDK-Grenze verifiziert; nur der bezahlte End-zu-End-Call steht aus.
- Manueller Live-Test der übrigen Kernfunktionen mit echtem API-Key auf dem echten Windows-Rechner (Definition of Done, Handbook Kap. 28) - bisher nur automatisiert/gemockt. `install_program` real ausführen ist ein bewusster, expliziter Schritt und sollte gezielt vom Product Owner freigegeben/begleitet werden.
- Manueller Smoke-Test der Jarvis-Runtime mit echtem Bot-Token (TelegramChannel) sowie ein realer Jarvis-Eigenstart-Test nach Windows-Anmeldung - bisher nur automatisiert/gemockt (Definition of Done, Handbook Kap. 28).
- Piper-Sprachmodell herunterladen und `tts_enabled: true` für einen Live-TTS-Test setzen.
- `anthropic` ist im `.venv` installiert (0.116.0); `requirements.txt` führt es bewusst optional/auskommentiert (lazy Import, ADR-029).
- `.git_broken_5/` (Reste eines frühen, abgebrochenen git-init-Versuchs) liegt noch im Arbeitsordner, per `.gitignore` ausgeschlossen - bewusst nicht gelöscht (keine destruktive Aktion ohne Rückfrage).

### Feature-TODOs (nächste Roadmap-Bausteine, NICHT jetzt umsetzen)
Roadmap/Backlog leben vollständig im Handbook (Kap. 13 Roadmap, Kap. 29 Backlog). Hier nur technische Detail-Notizen ohne eigenen Backlog-Eintrag:
- Spätere v0.8-Phasen (nach der Nutzwert-Phase, falls fortgesetzt): aufgabenabhängiges Routing/Orchestrierung, ggf. `ANALYSIS`-Trennung (optionaler `task`-Parameter an `answer()`), lokale Modelle (Ollama). Bewusst NICHT jetzt (siehe ADR-030 „Bewusst NICHT Bestandteil von Phase 2").
- Dritter KI-Verwender: `configure()`-Duplizierung (`reports.py`/`monitor.py`) zu einer gemeinsamen Abstraktion zusammenführen prüfen (Wolfgangs Entscheidung bei ADR-020).
- **EBENE-2-Ist-Stand-Audit (bekannte Schuld, bewusst aufgeschoben - NICHT in der Nutzwert-Phase):** Mehrere „lebendige" Handbook-Kapitel hängen auf altem Stand, während EBENE 1 frisch gepflegt wurde (Zwei-Review-Befund 03.07.2026). Konkret: Kap. 12 „Projektstruktur" zeigt eine „Zielstruktur (ab v0.5+)" (`brain/`/`voice/`/`tools/`/`utils/`), die es im echten Code nie gab (real: `core/`/`commands/`/`memory/`/`executor/`), Überschrift noch „v0.2 – Aktuell"; Kap. 13 Roadmap = kaputte Tabellen-Seitenumbrüche + inkonsistente Fertig-Marker (✅ nur bei v0.1) + „v0.8 noch nicht begonnen" (überholt); Kap. 22 Academy (nur Level 1 markiert); Kap. 23 Portfolio („v0.2 in Arbeit"); Kap. 20 listet nur ADR-000..003 inline (vermutlich beabsichtigt, aber ohne erklärenden Satz). Nachziehen als EIN bewusster Schritt bei der nächsten echten Konsolidierung. (Der interne Widerspruch Kap. 7 ↔ Kap. 13 wurde am 03.07.2026 an der Wurzel behoben: Kap. 7 trägt keine Status-Aussage mehr.)
- `.docx`-Handbook als binäre, nicht diffbare SSoT: Umstieg auf ein diffbares Format (z. B. Markdown) erwägen - bewusst aufgeschoben (Ablenkung von der Nutzwert-Phase), aber als technische Schuld notiert. Dieselbe Wurzel wie die beiden Drift-Funde: unsichtbare, manuell gepflegte binäre SSoT.
- Veralteter Fußzeilen-Vermerk „v3.5 - ab jetzt eingefroren" am Handbook-Ende bei nächster Gelegenheit bereinigen.
- Den `preview()`-Hook (ADR-023) für weitere schreibende PC-Admin-Commands nutzen, sobald umgesetzt.

Im Code wurden keine `TODO`-/`FIXME`-Marker gefunden.

## Latest ADR
`ADR-030 - Minimaler deterministischer Provider-Router in AIEngine (v0.8 Multi-KI, Phase 2)`

## Latest Architecture Change
v0.8 „Multi-KI", Phase 1+2 (ADR-029/030): Die KI-Anbindung ist nicht mehr fest an OpenAI gebunden. `AIEngine` delegiert den rohen Modellaufruf an einen austauschbaren `LLMProvider` (`core/providers.py`, OpenAI/Claude), gewählt über `config.ai_provider`. Ein deterministischer `ProviderRouter` erlaubt pro Aufgabentyp (`get_plan`=PLANNING, `answer`=GENERATION) einen eigenen Provider (`planning_provider`/`answer_provider`, Rückfall auf `ai_provider`), mit Fallback auf den Standardprovider. Öffentliche `AIEngine`-Schnittstelle und alle Aufrufer unverändert; `confirmed`-Strip zentral. Details: ADR-029, ADR-030.

## Known Limitations
- Claude-Provider im Prompt-JSON-Modus (Phase 1, ADR-029): keine strukturierte Ausgabe/Tool-Use; ungültiges JSON fällt über das vorhandene `json.loads`-Fallback auf einen `chat`-Plan zurück (akzeptiertes Restrisiko).
- Langzeitgedächtnis funktioniert nur auf Zuruf; keine automatische Fakten-Extraktion.
- Mikrofon/Wake-Word weiterhin nicht umgesetzt.
- Kokoro TTS unterstützt aktuell kein Deutsch.
- `system_status`/`analyze_pc`: keine Temperatur (psutil-Limitierung unter Windows).
- `read_excel`/`analyze_report`/`calculate_kpi`: nur `.xlsx`/`.xlsm`, nur Werte, 500 Zeilen/Blatt.
- `telegram_main.py`: nur vier Intents erreichbar, kein gleichzeitiger Betrieb mit der Konsole, `TelegramSpeech.listen()` fail-closed (ADR-018).
- `analyze_pc`/`analyze_event_log`/`disable_/enable_autostart_entry`/`analyze_/clean_temp_files`: alle Windows-exklusiv, jeweiliger Scope siehe Handbook Kap. 17.
- `jarvis_runtime.py`: kein UI/Tray/Wake-Word, kein abstraktes Channel-Interface. `ConsoleDummyChannel` bleibt für unbeaufsichtigten Betrieb ungeeignet (blockiert auf `input()`) - wird beim Jarvis-Eigenstart (`pythonw.exe`) deshalb gar nicht erst gestartet; Telegram übernimmt die Erreichbarkeit.
- Single-Instance-Schutz (ADR-026) schützt nur vor gleichzeitigem *Prozessstart* gegen dasselbe `memory_dir` - kein Schutz gegen externes Löschen der Lock-Datei, während eine Instanz läuft (bekanntes, akzeptiertes Restrisiko).
- `telegram_main.py` (eigenständig) und `TelegramChannel` (über die Runtime) dürfen nicht gleichzeitig mit demselben Bot-Token laufen - Telegram erlaubt pro Bot nur eine aktive Long-Polling-Verbindung.
- Jarvis-Eigenstart (ADR-028): fester HKCU-Run-Key-Eintragsname `"Jarvis"` setzt eine einzige Installation pro Windows-Benutzerkonto voraus; veraltete Registry-Pfade nach Projekt-/Interpreter-Umzug werden nicht automatisch repariert (Selbstbedienung per erneutem `enable_jarvis_autostart`).

## Git
Frühere Historie bis `v0.7` (getaggt, `a7eb86d`) und der Infrastruktur-/Runtime-Baustein (ADR-024-028) siehe Handbook / frühere PROJECT_STATE-Stände. Seither (alle auf `main`, ungetaggt):
- `86c5918` - Konsolidierung Handbook v3.7 (Infrastruktur-/Runtime-Baustein)
- `b5fea6e` - Doku: dauerhafte Windows-Env-Vars (`setx`) für Telegram/Autostart
- `af83614` - Fix: TelegramChannel thread-sicher stoppen (kein `RuntimeError`)
- `428b9c6` - Fix: Bot-Token nicht mehr über httpx-INFO loggen
- `6d0c738` - Fix: vom Modell geliefertes `confirmed` am Trust Boundary entfernen
- `5291cd3` - Doku: ADR-029 (Provider-Abstraktion + Claude, v0.8 Phase 1)
- `0373358` - v0.8 Phase 1: Provider-Abstraktion + Claude (ADR-029)
- `65f707c` - Doku: v0.8 Phase 1 technisch abgeschlossen (Logbook)
- `f35f0f7` - Doku: ADR-030 (deterministischer Provider-Router, v0.8 Phase 2)
- `4b3b44d` - v0.8 Phase 2: Provider-Router (ADR-030)
- `ae233fc` - Handbook v3.8: Leitbild/DNA verankert (Produktidentität, EBENE 1)

Frühere Versionen (v0.1-v0.3) existieren nur als Text in `docs/CHANGELOG.md`/`docs/logbook.md`.
