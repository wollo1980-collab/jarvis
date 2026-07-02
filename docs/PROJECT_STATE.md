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

Tests: `264 / 264` grün (225 aus v0.7 + 11 aus Jarvis-Runtime v1, ADR-025 + 13 aus Single-Instance-Schutz, ADR-026 + 15 aus Runtime v2/TelegramChannel, ADR-027).

Aus v0.6/v0.5/v0.4 weiterhin gültig: Telegram-Fernzugriff (ADR-018), Excel-Lesen/Tabellen-Auswertung/KPI (ADR-014/015/016), Kurz-/Langzeitgedächtnis (ADR-009), PC-Grundsteuerung (ADR-011/012) - siehe Handbook Kap. 13/27 für den vollständigen Roadmap-Stand.

## Next Planned Version
`v0.7` ist vollständig abgeschlossen (Handbook v3.6, Tag `v0.7`). `v0.8 "Multi-KI"` (Handbook Kap. 13: "Claude + GPT + Copilot orchestrieren") ist der nächste geplante Baustein - noch nicht begonnen, kein technischer Vorschlag erstellt. Vor v0.8 steht architektonisch der Jarvis-Eigenstart-Baustein: nach dem Single-Instance-Schutz (ADR-026) ist jetzt auch Runtime v2 (Telegram-Kanal, ADR-027) umgesetzt - die Runtime hat damit erstmals einen Kanal, der ohne angehängte Konsole nutzbar ist. Jarvis-Eigenstart selbst (Windows-Autostart, HKCU Run-Key) bleibt trotzdem ein eigener, noch nicht begonnener Schritt - keine Implementierung, kein technischer Vorschlag bisher.

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

## Single-Instance-Schutz implementiert (ADR-026, wartet auf künftige Konsolidierung)
Nach Freigabe von Runtime v1 hat Wolfgang eine Bewertung angefordert, ob der Infrastruktur-/Runtime-Baustein bereits für Jarvis-Eigenstart ausreicht. Ergebnis: Runtime v1 beweist nur das Gerüst, `ConsoleDummyChannel` ist für unbeaufsichtigten Autostart ungeeignet (blockiert auf `input()`) - zusätzlich besteht unabhängig von jedem Kanal weiterhin das in ADR-025 benannte Risiko, dass mehrere Jarvis-Prozesse gleichzeitig gegen dasselbe `memory_dir` laufen könnten (`JsonMemoryStore` hat kein Locking). Wolfgang entschied: Runtime v2 (Telegram-Kanal, Channel-Interface, Autostart) bleibt vertagt - **zuerst** dieses Risiko beheben, unabhängig von Kanälen/UI/Autostart.

**Umgesetzt (ADR-026):**
- Neue Datei **`core/single_instance.py`**: `SingleInstanceLock` - Schutz **pro `memory_dir`**, nicht global pro Projekt.
- Lock-Datei `jarvis.lock` innerhalb von `memory_dir`, Inhalt: PID, Einstiegspunkt-Name, Zeitstempel (JSON). Atomar erzeugt (`os.open(O_CREAT|O_EXCL)`) - Betriebssystem-Garantie gegen Race Conditions.
- Zusätzliche Härtung (Product-Owner-Entscheidung): Datei-Handle bleibt für die Laufzeit offen, zusätzlich per `msvcrt.locking()` gesperrt - Windows gibt Handle und Sperre bei einem Absturz automatisch frei.
- Verwaiste-Lock-Erkennung vor jedem Erwerb: `psutil.pid_exists()` + exakter Dateiname-Abgleich der tatsächlichen Prozess-Cmdline (schützt gegen PID-Wiederverwendung durch Windows) - verwaiste Lock-Dateien werden automatisch entfernt (Selbstheilung).
- **`main.py`, `telegram_main.py`, `jarvis_runtime.py`** erwerben den Lock als allererste Aktion in `main()`, geben ihn per `try`/`finally` beim Beenden frei. Bei aktivem Lock: sofortiger, kontrollierter Abbruch mit Fehlermeldung (PID/Einstiegspunkt/Zeitstempel), kein Command wird ausgeführt.
- Während der Implementierung ein sicherheitsrelevanter Bug gefunden und behoben: `msvcrt.locking()` verweigert das Lesen der Lock-Datei über ein frisches Handle (`PermissionError`), auch innerhalb desselben Prozesses - eine frühere Fassung hätte diesen Lesefehler fälschlich als "verwaist" interpretiert und eine aktive Lock-Datei gelöscht. Durch einen dedizierten Regressionstest abgesichert.
- `core/config.py`, `core/ai.py`, `core/planner.py`, `core/speech.py`, `core/tool_manager.py`, `core/models.py`, `commands/*`, `executor/*`, `memory/*` unverändert (per `git diff --stat` verifiziert).

**Weiterhin vertagt:** Telegram-Kanal in der Runtime, abstraktes Channel-Interface, Windows-Autostart, UI, Tray, Wake-Word, Runtime v2 allgemein - eigene, spätere Entscheidungen.

Details, Begründung und Alternativen: `docs/adr/ADR-026.md`.

## Runtime v2 implementiert: TelegramChannel (ADR-027, wartet auf künftige Konsolidierung)
Nach dem Single-Instance-Schutz wurde ein Architekturvorschlag für "Jarvis-Eigenstart / Runtime v2" erarbeitet, als Richtung freigegeben, in ADR-027 dokumentiert und anschließend nach einem Product-Owner-geprüften Implementierungsplan umgesetzt: Telegram ist jetzt der erste echte Runtime-Kanal neben `ConsoleDummyChannel`.

**Wichtige Zwischenentscheidung:** Geprüft und verworfen wurde, `jarvis_runtime.py` komplett unverändert zu lassen und `TelegramChannel` `filter_plan()` selbst anwenden zu lassen (dann unverändertes `submit(text, reply_callback)`) - das hätte eine TOCTOU-Sicherheitslücke geschaffen: `_process()` plant intern ohnehin erneut, und dieser zweite Plan (nicht der geprüfte erste) würde tatsächlich ausgeführt - bei KI-Nichtdeterminismus oder echter Nebenläufigkeit (History ändert sich zwischen Vorab-Check und Verarbeitung) könnte eine nicht erlaubte Anfrage so ungeprüft durchrutschen.

**Umgesetzt (ADR-027):**
- **`telegram_channel.py`** (neu) - `TelegramChannel`, einzige Stelle im Runtime-Umfeld mit `python-telegram-bot`/Asyncio-Code, vollständig von `jarvis_runtime.py` getrennt.
- Sicherheitslogik wiederverwendet statt dupliziert: `ALLOWED_INTENTS`/`filter_plan`/`rejection_reason`/`is_authorized` unverändert aus `telegram_main.py` importiert.
- `JarvisRuntime.submit()`/`_process()` um optionalen `plan_filter`-Parameter erweitert (Default `None`, vollständig rückwärtskompatibel zu `ConsoleDummyChannel`/Runtime v1) - `JarvisRuntime` bleibt telegram-unwissend. Bei Ablehnung: kein Executor-Aufruf, keine History-Schreibung.
- Asyncio-Brücke (`asyncio.get_running_loop()` + `asyncio.run_coroutine_threadsafe()`) zwischen dem synchronen Runtime-Worker-Thread und PTBs eigenem Event-Loop - einzige Stelle im Projekt mit dieser Brücke, explizit begründet (ADR-027).
- `jarvis_runtime.py::main()` startet `TelegramChannel` automatisch in einem eigenen Thread, sobald `JARVIS_TELEGRAM_BOT_TOKEN`/`JARVIS_TELEGRAM_ALLOWED_CHAT_ID` gesetzt sind - verzögerter Import, `python-telegram-bot` bleibt optional.
- `_RuntimeSpeech` (fail-closed, ADR-025) gilt automatisch auch für Telegram-Nachrichten - kein eigener Speech-Adapter in `telegram_channel.py` nötig.
- `core/*`, `commands/*`, `executor/*`, `memory/*`, `telegram_main.py`, `main.py`, `requirements.txt` unverändert (per `git diff --stat` verifiziert).

**Weiterhin nicht enthalten:** Jarvis-Eigenstart (Windows-Autostart) selbst, Tray, eigenes UI, Wake-Word, abstraktes Channel-Interface (kein Verhaltenswert bei zwei strukturell verschiedenen Kanälen), Runtime v3.

Details, Begründung und Alternativen: `docs/adr/ADR-027.md`.

## Tests
Letzter Check am 2026-07-02: `pytest tests -v` mit zusätzlichem `PYTHONPATH`.

### Test Status
`264 / 264` bestanden

### Known Failure
Keiner aktuell.

## Offene Aufgaben

### Technische TODOs (Definition of Done / Betrieb, kein neuer Scope)
- Manueller Live-Test der übrigen Kernfunktionen mit echtem API-Key auf dem echten Windows-Rechner (Definition of Done, Handbook Kap. 28) - bisher nur automatisiert/gemockt getestet. `install_program` real ausführen ist ein bewusster, expliziter Schritt und sollte gezielt vom Product Owner freigegeben/begleitet werden.
- Piper-Sprachmodell herunterladen und `tts_enabled: true` für einen Live-TTS-Test setzen.
- `.git_broken_5/` (Reste eines frühen, abgebrochenen git-init-Versuchs) liegt noch im Arbeitsordner, per `.gitignore` ausgeschlossen - bewusst nicht gelöscht (keine destruktive Aktion ohne Rückfrage).

### Feature-TODOs (nächste Roadmap-Bausteine, NICHT jetzt umsetzen)
- Jarvis-Eigenstart (Windows-Autostart, HKCU Run-Key, `enable_/disable_jarvis_autostart`-Intents) aufbauend auf `jarvis_runtime.py` + `telegram_channel.py` - siehe Abschnitt "Runtime v2 implementiert" oben. Kein Code, keine Umsetzung.
- Abstraktes Channel-Interface - weiterhin zurückgestellt (kein Verhaltenswert bei zwei strukturell verschiedenen Kanälen), erst bei einem dritten echten Kanal erneut prüfen.
- UI, Tray, Wake-Word - erst bei Bedarf (YAGNI), kein Code, keine Umsetzung.

Vollständige, aktuelle Liste jetzt im Handbook (Kap. 13 Roadmap, Kap. 29 Backlog) - hier nur technische Detail-Notizen, die (noch) keinen eigenen Handbook-Backlog-Eintrag brauchen:
- Dritter KI-Verwender: falls ein weiteres Modul KI-Zugriff braucht, `configure()`-Duplizierung (`reports.py`/`monitor.py`) zu einer gemeinsamen Abstraktion zusammenführen prüfen (Wolfgangs Entscheidung bei ADR-020).
- Den `preview()`-Hook (ADR-023) für weitere schreibende PC-Admin-Commands (Dienste, Treiber) nutzen, sobald diese umgesetzt werden.
- Alias-Liste für Standort-/Ist-Wert-Spalten (ADR-016) erweitern, sobald sich an echten Reports zeigt, dass andere Spaltennamen gebraucht werden.
- Eigene `AIEngine.summarize_report()`-Methode - nur prüfen, falls die Wiederverwendung von `answer()` sich als inhaltlich unzureichend erweist (ADR-015).
- Verknüpfungsziele im Startup-Ordner auflösen (bräuchte `pywin32`) - bewusst nicht in Phase 1, nur Dateinamen (ADR-020).

Im Code wurden keine `TODO`-/`FIXME`-Marker gefunden.

## Latest ADR
`ADR-027 - Runtime v2 - TelegramChannel als erster echter Runtime-Kanal`

## Latest Architecture Change
Neue Datei `telegram_channel.py`: `TelegramChannel` bindet Telegram als ersten echten Runtime-Kanal ein, läuft gleichzeitig mit `ConsoleDummyChannel` in einem eigenen Thread. Importiert die bestehende Telegram-Sicherheitslogik (`ALLOWED_INTENTS`/`filter_plan`/`rejection_reason`/`is_authorized`) unverändert aus `telegram_main.py` statt sie zu duplizieren. `JarvisRuntime.submit()`/`_process()` (`jarvis_runtime.py`) haben dafür einen optionalen, generischen `plan_filter`-Parameter bekommen (Default `None`, rückwärtskompatibel) - `JarvisRuntime` bleibt dadurch telegram-unwissend. Eine Asyncio-Brücke (`asyncio.run_coroutine_threadsafe()`) verbindet den synchronen Runtime-Worker-Thread mit `python-telegram-bot`s eigenem Event-Loop - einzige Stelle im Projekt mit dieser Brücke. Details: ADR-027.

## Known Limitations
- Langzeitgedächtnis funktioniert nur auf Zuruf; keine automatische Fakten-Extraktion.
- Mikrofon/Wake-Word weiterhin nicht umgesetzt.
- Kokoro TTS unterstützt aktuell kein Deutsch.
- `system_status`/`analyze_pc`: keine Temperatur (psutil-Limitierung unter Windows).
- `read_excel`/`analyze_report`/`calculate_kpi`: nur `.xlsx`/`.xlsm`, nur Werte, 500 Zeilen/Blatt.
- `telegram_main.py`: nur vier Intents erreichbar, kein gleichzeitiger Betrieb mit der Konsole, `TelegramSpeech.listen()` fail-closed (ADR-018).
- `analyze_pc`/`analyze_event_log`/`disable_/enable_autostart_entry`/`analyze_/clean_temp_files`: alle Windows-exklusiv, jeweiliger Scope siehe Handbook Kap. 17 (Umsetzungsstand-Annotationen).
- `jarvis_runtime.py` (ADR-024/025/026/027): kein UI/Tray/Wake-Word, kein Windows-Autostart, kein abstraktes Channel-Interface. `ConsoleDummyChannel` bleibt für unbeaufsichtigten Betrieb ungeeignet (blockiert auf `input()`) - Telegram (`telegram_channel.py`) ist der erste Kanal ohne diese Einschränkung.
- Single-Instance-Schutz (ADR-026) schützt nur vor gleichzeitigem *Prozessstart* gegen dasselbe `memory_dir` - kein Schutz gegen externes Löschen der Lock-Datei durch Dritte (Virenscanner, manuelles Löschen), während eine Instanz noch läuft (bekanntes, akzeptiertes Restrisiko).
- `telegram_main.py` (eigenständig) und `TelegramChannel` (über die Runtime) dürfen nicht gleichzeitig mit demselben Bot-Token laufen - Telegram erlaubt pro Bot nur eine aktive Long-Polling-Verbindung. Der Single-Instance-Schutz verhindert das im Normalfall bereits indirekt (gleiches `memory_dir`), ist aber kein expliziter Schutz für dieses Szenario.

## Git
Initial-Commit getaggt als `v0.4`. Danach Handbook v3.3/ADR-013, Excel-Lesen (ADR-014), Tabellen-Auswertung (ADR-015), Power-BI-Scope-Entscheidung, KPI (ADR-016), v0.5-Abschluss, getaggt als `v0.5`. Danach Handbook v3.4/ADR-017, Telegram-Fernzugriff (ADR-018), getaggt als `v0.6`, danach Handbook v3.5/ADR-019 inkl. Kap.-2-Konsistenzkorrektur. Danach `48f0f83` (PC-Analyse, ADR-020), `5f330fb` (Ereignisprotokoll-Analyse, ADR-021), `efe067f` (PROJECT_STATE-Korrektur), `b108c06` (Autostart-Verwaltung, ADR-022), `a765c9d` (Temp-Bereinigung, ADR-023), `920e32c` (v0.7-Abschlussdokumentation), `a7eb86d` (Handbook v3.6, Entwicklungsprozess-Konsolidierung) - getaggt als `v0.7`. Danach `95e5af9` (Jarvis-Runtime v1, ADR-025), `987ed0b` (Single-Instance-Schutz, ADR-026), `3b05a95` (ADR-027-Dokumentation) - alle noch ungetaggt (kein eigener Versionsblock). Runtime v2/TelegramChannel-Implementierung (ADR-027) noch nicht committed. Frühere Versionen (v0.1-v0.3) existieren nur als Text in `docs/CHANGELOG.md`/`docs/logbook.md`.
