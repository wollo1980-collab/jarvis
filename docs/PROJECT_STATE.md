---
version: "v0.8 P1+2 (Multi-KI) abgeschlossen; Nutzwert-Phase gestartet"
active_increment: governance-rebuild
tests: 346
latest_adr: 31
stand: 2026-07-03
---

# PROJECT STATE

Quelle: `README.md`, `docs/handbook/HANDBOOK.md`, `docs/logbook.md`, `docs/CHANGELOG.md`, `docs/adr/*.md`
Der maschinenlesbare Kopf (oben) ist die Single Source der Kern-Kennzahlen; das Konsistenz-Gate prüft ihn gegen die Realität (siehe CONTRIBUTING §7).

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

Die Nutzwert-Phase läuft als **benannter Block ohne eigene Versionsnummer** (Präzedenz: Runtime-Baustein; Versionsnummer ggf. später), **getrennt von v0.8**. **Baustein 1 umgesetzt: Mail-Briefing „Was liegt an?"** (ADR-031) - erster externer Connector, lokal-lesend, gelernte Absenderregeln. Nächster Schritt: weiter Dogfooding-Reibungen sammeln.

Umgesetzt in der Nutzwert-Phase (Details: `docs/CHANGELOG.md`, ADR-031):
- **Mail-Briefing** - `commands/mail.py` (check_mail / show_mail_advertising / mail_hide_sender / mail_keep_sender, alle Sicherheitsstufe 0), `core/mail_reader.py` (imaplib/email stdlib, **read-only** via `select(readonly=True)`+`BODY.PEEK`, nur Kopfzeilen), `memory/mail_rules.py` (lokale, korrigierbare Absenderregeln - Regel schlägt Heuristik). `mail_accounts` in Config (Secrets per Env). Rein lokal, kein Mailinhalt an eine KI. `core/ai.py` unverändert.

## Tests
Volle Suite grün. Autoritative Zahl (`tests`) und Datum (`stand`) stehen im Kopf.

Hinweis zum Testlauf: venv-Interpreter; für die volle Suite ist ein beschreibbares `--basetemp` nötig, da die Sandbox sonst den System-Temp der `tmp_path`-Fixture blockiert - kein Testdefekt.

### Known Failure
Keiner aktuell.

## Offene Aufgaben

### Technische TODOs (Definition of Done / Betrieb, kein neuer Scope)
- **Live-Test Mail-Briefing (ADR-031)** auf dem echten Windows-Rechner: `mail_accounts` in `config.json` eintragen, Gmail-**App-Passwort** (2FA) als Env-Variable setzen, „was liegt an?" real testen - bisher nur gemockt. **Hotmail-Auth verifizieren** (Microsoft baut Basis-Auth/App-Passwörter ab; ggf. OAuth statt IMAP-Passwort).
- **Live-Test Claude-Provider** mit echtem `ANTHROPIC_API_KEY` auf dem echten Windows-Rechner - bewusst verschobener manueller Verifikationsschritt (kein offener Implementierungsfehler). Pfad ist offline bis zur SDK-Grenze verifiziert; nur der bezahlte End-zu-End-Call steht aus.
- Manueller Live-Test der übrigen Kernfunktionen mit echtem API-Key auf dem echten Windows-Rechner (Definition of Done, Handbook Kap. 28) - bisher nur automatisiert/gemockt. `install_program` real ausführen ist ein bewusster, expliziter Schritt und sollte gezielt vom Product Owner freigegeben/begleitet werden.
- Manueller Smoke-Test der Jarvis-Runtime mit echtem Bot-Token (TelegramChannel) sowie ein realer Jarvis-Eigenstart-Test nach Windows-Anmeldung - bisher nur automatisiert/gemockt (Definition of Done, Handbook Kap. 28).
- Piper-Sprachmodell herunterladen und `tts_enabled: true` für einen Live-TTS-Test setzen.
- `anthropic` ist im `.venv` installiert (0.116.0); `requirements.txt` führt es bewusst optional/auskommentiert (lazy Import, ADR-029).
- `.git_broken_5/` (Reste eines frühen, abgebrochenen git-init-Versuchs) liegt noch im Arbeitsordner, per `.gitignore` ausgeschlossen - bewusst nicht gelöscht (keine destruktive Aktion ohne Rückfrage).

### Feature-TODOs & Backlog (nächste Bausteine, NICHT jetzt umsetzen)
Roadmap und Backlog leben **hier** in PROJECT_STATE — die Verfassung (`HANDBOOK`) trägt keine Roadmap/Status; abgeschlossene Versionen stehen in `CHANGELOG`. Technische Detail-Notizen:
- Spätere v0.8-Phasen (nach der Nutzwert-Phase, falls fortgesetzt): aufgabenabhängiges Routing/Orchestrierung, ggf. `ANALYSIS`-Trennung (optionaler `task`-Parameter an `answer()`), lokale Modelle (Ollama). Bewusst NICHT jetzt (siehe ADR-030 „Bewusst NICHT Bestandteil von Phase 2").
- Dritter KI-Verwender: `configure()`-Duplizierung (`reports.py`/`monitor.py`) zu einer gemeinsamen Abstraktion zusammenführen prüfen (Wolfgangs Entscheidung bei ADR-020).
- Den `preview()`-Hook (ADR-023) für weitere schreibende PC-Admin-Commands nutzen, sobald umgesetzt.

**Backlog (zurückgestellte Ideen, kein aktueller Scope — Grund je Zeile):**
- **Spotify-/Medien-Steuerung** — kein echtes Arbeitsproblem.
- **Wake-Word** (z. B. Porcupine) — aktuell reicht „jarvis" im Text; nach der Nutzwert-Phase erneut prüfen. (Lokale Modelle/Ollama siehe oben „Spätere v0.8-Phasen".)
- **Power-BI-Integration** — liegt im Firmenumfeld/auf dem Firmenrechner; im privaten Jarvis-Rahmen aktuell nicht praktikabel.
- **Generalisierung der Post-Arbeitsmodule** → allgemeine Excel-/Report-Analyse — die bestehenden Commands bleiben bewusst spezifisch, bis mehrere Report-Typen es rechtfertigen (Regel 6).
- **Fernzugriff-Ausbau** (Web-Interface, VPN) — Alternativen/Ergänzungen zu Telegram, aktuell nicht nötig.

Im Code wurden keine `TODO`-/`FIXME`-Marker gefunden.

## Latest Architecture Change
**Erster externer Connector (ADR-031, Nutzwert-Phase):** neuer `commands/mail.py` mit read-only IMAP-Zugriff (`core/mail_reader.py`, stdlib) und einem lokalen, korrigierbaren Präferenzspeicher (`memory/mail_rules.py`). Bewusst noch KEINE generische Connector-Abstraktion (YAGNI - erst beim zweiten Dienst); der Command darf konkret sein. `core/ai.py`/Executor-Kern unverändert.

Davor - v0.8 „Multi-KI", Phase 1+2 (ADR-029/030): Die KI-Anbindung ist nicht mehr fest an OpenAI gebunden. `AIEngine` delegiert den rohen Modellaufruf an einen austauschbaren `LLMProvider` (`core/providers.py`, OpenAI/Claude), gewählt über `config.ai_provider`. Ein deterministischer `ProviderRouter` erlaubt pro Aufgabentyp (`get_plan`=PLANNING, `answer`=GENERATION) einen eigenen Provider (`planning_provider`/`answer_provider`, Rückfall auf `ai_provider`), mit Fallback auf den Standardprovider. Öffentliche `AIEngine`-Schnittstelle und alle Aufrufer unverändert; `confirmed`-Strip zentral. Details: ADR-029, ADR-030.

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
