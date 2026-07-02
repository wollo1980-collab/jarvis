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

Tests: `249 / 249` grün (225 aus v0.7 + 11 aus Jarvis-Runtime v1, ADR-025 + 13 aus Single-Instance-Schutz, ADR-026).

Aus v0.6/v0.5/v0.4 weiterhin gültig: Telegram-Fernzugriff (ADR-018), Excel-Lesen/Tabellen-Auswertung/KPI (ADR-014/015/016), Kurz-/Langzeitgedächtnis (ADR-009), PC-Grundsteuerung (ADR-011/012) - siehe Handbook Kap. 13/27 für den vollständigen Roadmap-Stand.

## Next Planned Version
`v0.7` ist vollständig abgeschlossen (Handbook v3.6, Tag `v0.7`). `v0.8 "Multi-KI"` (Handbook Kap. 13: "Claude + GPT + Copilot orchestrieren") ist der nächste geplante Baustein - noch nicht begonnen, kein technischer Vorschlag erstellt. Vor v0.8 steht architektonisch der Jarvis-Eigenstart-Baustein: eine Bewertung ergab, dass Runtime v1 dafür allein nicht ausreicht (einziger Kanal `ConsoleDummyChannel` blockiert auf `input()`, für unbeaufsichtigten Autostart ungeeignet) - ein Runtime-v2-Ausbau (Telegram-Kanal, Channel-Interface, Autostart) wurde jedoch von Wolfgang bewusst vertagt. Stattdessen zuerst der davon unabhängige Single-Instance-Schutz (ADR-026, siehe unten) - Voraussetzung für jeden künftigen Runtime-Ausbau. Jarvis-Eigenstart selbst bleibt weiterhin verschoben.

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

## Tests
Letzter Check am 2026-07-02: `pytest tests -v` mit zusätzlichem `PYTHONPATH`.

### Test Status
`249 / 249` bestanden

### Known Failure
Keiner aktuell.

## Offene Aufgaben

### Technische TODOs (Definition of Done / Betrieb, kein neuer Scope)
- Manueller Live-Test der übrigen Kernfunktionen mit echtem API-Key auf dem echten Windows-Rechner (Definition of Done, Handbook Kap. 28) - bisher nur automatisiert/gemockt getestet. `install_program` real ausführen ist ein bewusster, expliziter Schritt und sollte gezielt vom Product Owner freigegeben/begleitet werden.
- Piper-Sprachmodell herunterladen und `tts_enabled: true` für einen Live-TTS-Test setzen.
- `.git_broken_5/` (Reste eines frühen, abgebrochenen git-init-Versuchs) liegt noch im Arbeitsordner, per `.gitignore` ausgeschlossen - bewusst nicht gelöscht (keine destruktive Aktion ohne Rückfrage).

### Feature-TODOs (nächste Roadmap-Bausteine, NICHT jetzt umsetzen)
- Runtime v2 (Telegram-Kanal, abstraktes Channel-Interface) - bewusst vertagt, siehe Abschnitt "Single-Instance-Schutz implementiert" oben. Kein Code, keine Umsetzung.
- Jarvis-Eigenstart (Windows-Autostart) aufbauend auf `jarvis_runtime.py` - wartet weiterhin auf Runtime v2. Kein Code, keine Umsetzung.
- UI, Tray, Wake-Word - erst bei Bedarf (YAGNI), kein Code, keine Umsetzung.

Vollständige, aktuelle Liste jetzt im Handbook (Kap. 13 Roadmap, Kap. 29 Backlog) - hier nur technische Detail-Notizen, die (noch) keinen eigenen Handbook-Backlog-Eintrag brauchen:
- Dritter KI-Verwender: falls ein weiteres Modul KI-Zugriff braucht, `configure()`-Duplizierung (`reports.py`/`monitor.py`) zu einer gemeinsamen Abstraktion zusammenführen prüfen (Wolfgangs Entscheidung bei ADR-020).
- Den `preview()`-Hook (ADR-023) für weitere schreibende PC-Admin-Commands (Dienste, Treiber) nutzen, sobald diese umgesetzt werden.
- Alias-Liste für Standort-/Ist-Wert-Spalten (ADR-016) erweitern, sobald sich an echten Reports zeigt, dass andere Spaltennamen gebraucht werden.
- Eigene `AIEngine.summarize_report()`-Methode - nur prüfen, falls die Wiederverwendung von `answer()` sich als inhaltlich unzureichend erweist (ADR-015).
- Verknüpfungsziele im Startup-Ordner auflösen (bräuchte `pywin32`) - bewusst nicht in Phase 1, nur Dateinamen (ADR-020).

Im Code wurden keine `TODO`-/`FIXME`-Marker gefunden.

## Latest ADR
`ADR-026 - Single-Instance-Schutz für memory_data/ (Lock-Datei, PID/Entry-Point/Zeitstempel, offenes Datei-Handle)`

## Latest Architecture Change
Neue Datei `core/single_instance.py`: `SingleInstanceLock` schützt ein `memory_dir` vor gleichzeitigem Zugriff mehrerer Jarvis-Prozesse - Lock-Datei `jarvis.lock` mit PID/Einstiegspunkt/Zeitstempel, atomar erzeugt (`os.open(O_CREAT|O_EXCL)`), zusätzlich per `msvcrt.locking()` auf einem offen gehaltenen Datei-Handle gesperrt (Windows gibt es beim Absturz automatisch frei). Verwaiste Lock-Dateien werden vor jedem Erwerb automatisch erkannt (PID-Lebendigkeit + Cmdline-Abgleich gegen PID-Wiederverwendung) und entfernt. `main.py`, `telegram_main.py`, `jarvis_runtime.py` erwerben den Lock jetzt als allererste Aktion in `main()` - die ersten Änderungen an `main.py`/`telegram_main.py` seit deren jeweiliger Einführung. Details: ADR-026.

## Known Limitations
- Langzeitgedächtnis funktioniert nur auf Zuruf; keine automatische Fakten-Extraktion.
- Mikrofon/Wake-Word weiterhin nicht umgesetzt.
- Kokoro TTS unterstützt aktuell kein Deutsch.
- `system_status`/`analyze_pc`: keine Temperatur (psutil-Limitierung unter Windows).
- `read_excel`/`analyze_report`/`calculate_kpi`: nur `.xlsx`/`.xlsm`, nur Werte, 500 Zeilen/Blatt.
- `telegram_main.py`: nur vier Intents erreichbar, kein gleichzeitiger Betrieb mit der Konsole, `TelegramSpeech.listen()` fail-closed (ADR-018).
- `analyze_pc`/`analyze_event_log`/`disable_/enable_autostart_entry`/`analyze_/clean_temp_files`: alle Windows-exklusiv, jeweiliger Scope siehe Handbook Kap. 17 (Umsetzungsstand-Annotationen).
- `jarvis_runtime.py` (v1, ADR-025): rein internes Gerüst - nur `ConsoleDummyChannel`, kein UI/Tray/Wake-Word/Telegram, kein Windows-Autostart, kein abstraktes Channel-Interface. Für unbeaufsichtigten Autostart in dieser Form ungeeignet (`ConsoleDummyChannel` blockiert auf `input()`).
- Single-Instance-Schutz (ADR-026) schützt nur vor gleichzeitigem *Prozessstart* gegen dasselbe `memory_dir` - kein Schutz gegen externes Löschen der Lock-Datei durch Dritte (Virenscanner, manuelles Löschen), während eine Instanz noch läuft (bekanntes, akzeptiertes Restrisiko).

## Git
Initial-Commit getaggt als `v0.4`. Danach Handbook v3.3/ADR-013, Excel-Lesen (ADR-014), Tabellen-Auswertung (ADR-015), Power-BI-Scope-Entscheidung, KPI (ADR-016), v0.5-Abschluss, getaggt als `v0.5`. Danach Handbook v3.4/ADR-017, Telegram-Fernzugriff (ADR-018), getaggt als `v0.6`, danach Handbook v3.5/ADR-019 inkl. Kap.-2-Konsistenzkorrektur. Danach `48f0f83` (PC-Analyse, ADR-020), `5f330fb` (Ereignisprotokoll-Analyse, ADR-021), `efe067f` (PROJECT_STATE-Korrektur), `b108c06` (Autostart-Verwaltung, ADR-022), `a765c9d` (Temp-Bereinigung, ADR-023), `920e32c` (v0.7-Abschlussdokumentation), `a7eb86d` (Handbook v3.6, Entwicklungsprozess-Konsolidierung) - getaggt als `v0.7`. Danach `95e5af9` (Jarvis-Runtime v1, ADR-025) - noch ungetaggt (kein eigener Versionsblock). Single-Instance-Schutz (ADR-026) noch nicht committed. Frühere Versionen (v0.1-v0.3) existieren nur als Text in `docs/CHANGELOG.md`/`docs/logbook.md`.
