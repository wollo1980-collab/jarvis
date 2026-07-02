# Changelog

## Jarvis-Eigenstart (ADR-028, 02.07.2026)

Windows-Autostart für Jarvis - registriert/entfernt `jarvis_runtime.py`
als HKCU-Run-Key-Eintrag. Reine Command-Erweiterung, keine
Runtime-Architekturänderung.

### Neu
- `commands/monitor.py`: `EnableJarvisAutostartCommand`
  (`enable_jarvis_autostart`) / `DisableJarvisAutostartCommand`
  (`disable_jarvis_autostart`), Sicherheitsstufe 2. Fester
  HKCU-Run-Key-Eintragsname `"Jarvis"` - erscheint dadurch auch in
  `analyze_pc`/`system_status`s Autostart-Übersicht. Kein Bezug zu
  `disable_/enable_autostart_entry` (ADR-022) - jene verwalten fremde,
  bereits existierende Einträge; hier wird ein eigener Eintrag erzeugt/
  gelöscht.
- Ziel ist `pythonw.exe` (kein Konsolenfenster), mit Fallback auf
  `sys.executable`, falls `pythonw.exe` nicht gefunden wird (Antwort
  weist explizit darauf hin). Grund: ein versehentlich geschlossenes
  Konsolenfenster würde sonst den gesamten Runtime-Prozess inkl.
  Telegram-Kanal beenden.
- `enable_jarvis_autostart` ist idempotent (aktualisiert einen
  bestehenden Eintrag, z. B. nach einem Projekt-Umzug);
  `disable_jarvis_autostart` löscht ohne Pfad-Abgleich.
- `jarvis_runtime.py`: `setup_logging()`/`main()` prüfen einmal zentral,
  ob ein Konsolenfenster vorhanden ist (`sys.stdin`/`sys.stderr is None`
  - dokumentiertes Verhalten bei `pythonw.exe`-Start): fehlt es, wird
  `ConsoleDummyChannel` gar nicht erst gestartet (Prozess bleibt über
  den laufenden Worker-Thread am Leben) und der Konsolen-`StreamHandler`
  im Logging übersprungen (`FileHandler` bleibt aktiv). `ConsoleDummyChannel`
  selbst bleibt unverändert.
- 16 neue Tests (14 in `tests/test_commands_monitor.py`, 2 in
  `tests/test_jarvis_runtime.py` für die `setup_logging()`-Weiche) - 280
  Tests gesamt, alle grün.

### Bewusst nicht enthalten
Tray-Icon/Benachrichtigung beim Start, eigenes UI, Wake-Word,
Deinstallations-/Update-Handling, automatische Erkennung/Reparatur
veralteter Registry-Pfade, HKLM/systemweiter Autostart, Windows-Dienst-
Variante, Windows-Aufgabenplanung, Channel-Interface, Runtime v3.

### Siehe auch
`docs/adr/ADR-028.md`.

## Runtime v2 - TelegramChannel (ADR-027, 02.07.2026)

Zweiter, echter Runtime-Kanal neben `ConsoleDummyChannel` - Telegram
über die Runtime, ohne `main.py`/`telegram_main.py` zu verändern. Löst
die in der Runtime-v1-Bewertung festgestellte Lücke (einziger Kanal
blockierte auf `input()`, für unbeaufsichtigten Betrieb ungeeignet).

### Neu
- `telegram_channel.py`: `TelegramChannel` - einzige Stelle im
  Runtime-Umfeld mit `python-telegram-bot`/Asyncio-Code, vollständig von
  `jarvis_runtime.py` getrennt.
- Sicherheitslogik wiederverwendet statt dupliziert: `ALLOWED_INTENTS`,
  `filter_plan`, `rejection_reason`, `is_authorized` werden unverändert
  aus `telegram_main.py` importiert - derselbe Sicherheitsstand wie
  Telegram Phase 1 (ADR-018).
- `JarvisRuntime.submit()`/`_process()` bekommen einen optionalen
  `plan_filter`-Parameter (Default `None`, vollständig rückwärtskompatibel) -
  `JarvisRuntime` selbst bleibt telegram-unwissend, nur eine generische
  Erweiterungsstelle ist neu. Bei Ablehnung: kein Executor-Aufruf, keine
  History-Schreibung (exakte Parität zu `JarvisBridge.handle_message`).
- Asyncio-Brücke (`asyncio.get_running_loop()` +
  `asyncio.run_coroutine_threadsafe()`) zwischen dem synchronen
  Runtime-Worker-Thread und `python-telegram-bot`s eigenem Event-Loop -
  explizit dokumentiert (ADR-027), einzige Stelle im Projekt mit dieser
  Brücke.
- `jarvis_runtime.py::main()` startet `TelegramChannel` automatisch in
  einem eigenen Thread, sobald `JARVIS_TELEGRAM_BOT_TOKEN`/
  `JARVIS_TELEGRAM_ALLOWED_CHAT_ID` gesetzt sind (verzögerter Import -
  `python-telegram-bot` bleibt optional, `ConsoleDummyChannel` läuft
  weiterhin ohne PTB-Installation).
- 15 neue Tests (`tests/test_jarvis_runtime.py`: 4 neue für `plan_filter`,
  1 bestehender Test angepasst; `tests/test_telegram_channel.py`: 11 neu,
  u. a. echter Cross-Thread-Asyncio-Bridge-Test, Sicherheitsstufe-
  Rejection-Test, `stop_signals=None`-Regressionstest gegen einen
  bekannten PTB-Absturz außerhalb des Hauptthreads, Identitätstest gegen
  künftiges versehentliches Duplizieren der Sicherheitslogik) - 264
  Tests gesamt, alle grün.

### Bewusst nicht enthalten
Windows-Autostart (Jarvis-Eigenstart bleibt eigener, späterer Schritt),
Tray, eigenes UI, Wake-Word, abstraktes Channel-Interface (kein
Verhaltenswert bei zwei strukturell verschiedenen Kanälen), Runtime v3.

### Siehe auch
`docs/adr/ADR-027.md`.

## Single-Instance-Schutz (ADR-026, 02.07.2026)

Eigenständiger Infrastruktur-Baustein, unabhängig von Kanälen/UI/
Autostart: verhindert, dass mehrere Jarvis-Prozesse gleichzeitig
dasselbe `memory_dir` verwenden (`JsonMemoryStore` hat kein Locking) -
Voraussetzung für einen künftigen Runtime-Ausbau, in ADR-025 als
ungelöstes Risiko benannt.

### Neu
- `core/single_instance.py`: `SingleInstanceLock` - Schutz **pro
  `memory_dir`**, nicht global pro Projekt. Lock-Datei `jarvis.lock`
  innerhalb von `memory_dir` mit PID, Einstiegspunkt-Name und
  Zeitstempel (JSON).
- Atomare Erzeugung über `os.open(O_CREAT|O_EXCL)` als eigentliche
  Exklusivitäts-Garantie (Betriebssystem-Ebene, race-sicher).
- Zusätzliche Härtung (Product-Owner-Entscheidung): das Datei-Handle
  bleibt für die gesamte Laufzeit offen und wird per `msvcrt.locking()`
  gesperrt - Windows gibt Handle und Sperre bei einem Absturz
  automatisch frei, ohne eigenen Aufräum-Code.
- Verwaiste-Lock-Erkennung vor jedem Erwerb: `psutil.pid_exists()` plus
  Abgleich des tatsächlich laufenden Prozesses (`cmdline()`) gegen den
  gespeicherten Einstiegspunkt-Dateinamen (exakter Dateiname, kein
  Substring - schützt gegen PID-Wiederverwendung durch Windows).
  Verwaiste Lock-Dateien werden automatisch entfernt (Selbstheilung,
  kein manuelles Eingreifen nötig).
- `main.py`, `telegram_main.py`, `jarvis_runtime.py` erwerben den Lock
  als allererste Aktion in `main()`, vor jeglicher Core-Stack-
  Instanziierung; bei aktivem Lock bricht der Start sofort mit klarer
  Fehlermeldung (PID/Einstiegspunkt/Zeitstempel) ab, kein Command wird
  ausgeführt. Sauberes Beenden gibt den Lock über `try`/`finally`
  explizit frei.
- 13 neue Tests (`tests/test_single_instance.py`) - 249 Tests gesamt,
  alle grün. Darunter ein Regressionstest für einen während der
  Implementierung gefundenen Bug: `msvcrt.locking()` verweigert das
  Lesen der Lock-Datei über ein frisches Handle (`PermissionError`),
  auch innerhalb desselben Prozesses - eine frühere Fassung
  interpretierte diesen Lesefehler fälschlich als "verwaist" und hätte
  eine aktive Lock-Datei gelöscht.

### Bewusst nicht enthalten
Telegram-Kanal in der Runtime, abstraktes Channel-Interface, Windows-
Autostart, UI, Tray, Wake-Word, Runtime v2 allgemein - eigene, spätere
Entscheidungen (siehe ADR-024/025).

### Siehe auch
`docs/adr/ADR-026.md`.

## Jarvis-Runtime v1 (ADR-025, 02.07.2026)

Eigenständiger Infrastruktur-/Runtime-Baustein zwischen v0.7 und v0.8
(kein v0.X-Release) - Umsetzung der in ADR-024 festgelegten Architektur-
richtung als kleinstmöglicher, funktionierender Baustein.

### Neu
- `jarvis_runtime.py`: dritter, koordinierender Einstiegspunkt neben
  `main.py`/`telegram_main.py` - **Koexistenz, keine Ablösung**, beide
  bleiben unverändert.
- `JarvisRuntime`: instanziiert den Core-Stack (Config/AIEngine/Planner/
  Executor/Memory) einmalig, wie `main.py`. Kanäle kommunizieren
  ausschließlich über `submit(text, reply_callback)`.
- `queue.Queue` + ein einzelner Worker-Thread: serialisierte
  Verarbeitung eingehender Nachrichten - bewusst kein `asyncio` (KISS,
  Product-Owner-Entscheidung). Löst das Nebenläufigkeits-/Locking-
  Problem bei `memory_data/` (ADR-018), ohne `JsonMemoryStore`/
  `Executor` anzufassen. Worker fängt Fehler pro Nachricht ab und läuft
  weiter, statt still zu sterben (explizite Vorgabe).
- `_RuntimeSpeech`: fail-closed Speech-Adapter für den geteilten
  Executor - Sicherheitsstufe-2/3-Commands werden sicher abgelehnt
  statt eine Bestätigung zu erfinden (gleiches Prinzip wie
  `TelegramSpeech`, ADR-018, bewusst dupliziert statt importiert - keine
  `python-telegram-bot`-Abhängigkeit in der Runtime).
- `ConsoleDummyChannel`: einziger Kanal in v1 - liest interaktiv von der
  Konsole, beweist nur, dass das Runtime-Gerüst funktioniert, kein
  Produktivkanal.
- 11 neue Tests (`tests/test_jarvis_runtime.py`) - 236 Tests gesamt,
  alle grün.

### Bewusst nicht enthalten (v1)
- UI, Tray, Wake-Word, Telegram-Integration in die Runtime,
  Windows-Autostart.
- Abstraktes Channel-Interface (erst beim zweiten echten Kanal, YAGNI).
- `asyncio`, echte Nebenläufigkeits-Absicherung in `JsonMemoryStore`/
  `Executor`.
- Keine Änderung an `main.py`, `telegram_main.py`, `core/*`,
  `commands/*`, `executor/*`.

### Siehe auch
- ADR-024 (Architekturrichtung), ADR-025 (Umsetzung Runtime v1)

## v0.7 - PC-Admin (abgeschlossen, getaggt, 02.07.2026)

Handbook auf v3.6 aktualisiert (siehe eigener Abschnitt unten) - Kap. 13
markiert v0.7 als abgeschlossen, Kap. 29 enthält die sechs descopten
Bausteine (Treiber, Dienste, HKLM-Autostart, Papierkorb, `C:\Windows\Temp`,
Browser-Cache/-Profile) im Backlog. Definition of Done (Kap. 28,
"v0.7 - spezifisch") erfüllt: alle vier Phasen implementiert (ADR-020 bis
ADR-023), 225/225 Tests grün, Logbook/Changelog aktuell, Handbook-Version
erstellt. Tag `v0.7` gesetzt (zeigt auf `a7eb86d`). `v0.7` ist damit als
Gesamtversion abgeschlossen.

## Handbook v3.6 - v0.7-Abschluss, Entwicklungsprozess-Weiterentwicklung (02.07.2026)

Kein Code-Release - reine Dokumentations-/Governance-Aktualisierung nach
Abschluss von v0.7 (inhaltlich fertig, Tag noch ausstehend), gemäß der in
Kap. 2 festgelegten Regel ("Handbook wird nur zwischen zwei Versionen
geändert") - ab v3.6 ist dieses Update nach jeder abgeschlossenen
Hauptversion Pflicht, nicht mehr nur erlaubt.

### Geändert
- `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_6.docx` neu (v3.2-v3.5 bleiben
  als Archiv erhalten): Kap. 13 (Roadmap) - v0.7 als abgeschlossen markiert,
  neuer Eintrag "Jarvis-Eigenstart" zwischen v0.7 und v0.8 (Zweck/Scope/
  Nicht-Scope). Kap. 17 (PC-Steuerung) - alle Fähigkeiten mit
  Umsetzungsstand annotiert, System-Analyst-Vision um Hinweis auf den
  Jarvis-Eigenstart ergänzt. Kap. 19 (Governance) grundlegend erweitert:
  PROJECT_STATE.md explizit als temporärer Arbeitsbereich definiert, neuer
  Abschnitt "Konsolidierungsprozess" (verpflichtend nach jeder
  Hauptversion), "Product-Owner-Rules" dauerhaft aus PROJECT_STATE.md
  übernommen, neue Regel zu Scope-Erweiterung/Descoping. Kap. 2
  (Handbook-Versionierung) verschärft - Update nach jeder Hauptversion ist
  jetzt Pflicht, ohne festes Nummerierungsschema. Kap. 27 um "Präzisierung
  v3.6: v0.7 Abschluss" ergänzt. Kap. 28 (Definition of Done) um Abschnitt
  "v0.7 - spezifisch (PC-Admin)" sowie ein neues allgemeines Kriterium
  ("neue Handbook-Version erstellt") ergänzt. Kap. 29 (Backlog) um sechs
  Punkte aus dem v0.7-Abschluss ergänzt (Treiber, Dienste, HKLM-Autostart,
  Papierkorb, `C:\Windows\Temp`, Browser-Cache/-Profile).
- `docs/AI_START.md`: sechste Pflichtfrage zum Konsolidierungsstatus
  ergänzt, verweist jetzt auf `JARVIS_MASTER_HANDBOOK_v3_6.docx`.
- `README.md`, `docs/PROJECT_STATE.md` verweisen jetzt auf
  `JARVIS_MASTER_HANDBOOK_v3_6.docx`.
- `docs/PROJECT_STATE.md` konsolidiert und auf den aktuellen Projektstatus
  zurückgebaut: Abschnitte "Backlog", "Ausstehende Handbook-Aktualisierung"
  und "Product Owner Rules" entfernt (Inhalte vollständig ins Handbook
  übernommen, Kap. 19/29). Rollierende Abschnitte (Status, Tests, Latest
  ADR) bleiben bestehen.
- Vollständiger Text-Diff zwischen v3.5 und v3.6 geprüft - ausschließlich
  die oben genannten, beabsichtigten Änderungen, keine Kollateralschäden
  in unveränderten Kapiteln.

### Hintergrund
- Product-Owner-Entscheidung zur Weiterentwicklung des Entwicklungs-
  prozesses (02.07.2026): das Handbook soll dauerhaft die einzige Single
  Source of Truth bleiben, ohne dass `PROJECT_STATE.md`/`docs/logbook.md`
  über mehrere Versionen unbegrenzt wachsen. Sechs Kernregeln freigegeben
  (Handbook-Update-Pflicht ohne festes Nummernschema, PROJECT_STATE.md als
  temporärer Arbeitsbereich, konsolidierte Kap.-19-Governance-Regel,
  Roadmap-Scope-Regeln, Backlog-Zuordnungsprinzip, Product-Owner-Rules
  dauerhaft im Handbook, AI_START.md-Ergänzung). `docs/logbook.md` und
  `docs/CHANGELOG.md` bleiben bewusst NICHT Teil der Bereinigung - beide
  bleiben permanente, anwachsende historische Aufzeichnungen.

### Siehe auch
- `docs/PROJECT_STATE.md` (konsolidierter, aktueller Stand)

## v0.7 - PC-Admin: System-Analyse, Autostart-Verwaltung, Temp-Bereinigung (Scope abgeschlossen, Tag ausstehend, 02.07.2026)

Product-Owner-Entscheidung (02.07.2026): v0.7 wird mit dem aktuellen Umfang
abgeschlossen. Vier Bausteine umgesetzt: PC-Analyse (Phase 1, ADR-020),
Ereignisprotokoll-Analyse (Phase 2, ADR-021), Autostart-Verwaltung (Phase 3,
ADR-022), Temp-Bereinigung (Phase 4, ADR-023). 225/225 Tests grün.

**Begründung:** System-Analyse ist vollständig abgedeckt (Kap. 13). Autostart-
Verwaltung ist im Benutzer-Scope umgesetzt (HKCU Run-Key, Benutzer-Startup-
Ordner). Temp-Bereinigung ist im sicheren Benutzer-Scope umgesetzt (`%TEMP%`,
Sicherheitsstufe 3, `preview()`-Hook). Treiber prüfen/aktualisieren und
Dienste starten/stoppen bleiben bewusst offen - die beiden riskantesten und
komplexesten Kap.-17-Bausteine (Treiber ist Handbooks eigenes Stufe-3-
Beispiel) werden explizit ins Backlog verschoben statt überstürzt in v0.7
mitgenommen zu werden.

**Ins Backlog verschoben** (Details: `docs/PROJECT_STATE.md`, Abschnitt
"Backlog"):
- Treiber prüfen/aktualisieren.
- Dienste starten/stoppen.
- Autostart-Verwaltung auf HKLM/Alle-Benutzer erweitern (Administratorrechte).
- Temp-Bereinigung um Papierkorb erweitern.
- Temp-Bereinigung um `C:\Windows\Temp` erweitern (Administratorrechte).
- Browser-Cache-/Profil-Bereinigung.

**Noch offen bis zum vollständigen Abschluss:** Handbook-Aktualisierung auf
v3.6 (Kap. 13 als abgeschlossen markieren, Kap. 29 Backlog-Ergänzung, Kap. 28
DoD-Abschnitt, Jarvis-Eigenstart-Kapitel) und danach `git tag v0.7` - beides
noch NICHT durchgeführt. Siehe `docs/PROJECT_STATE.md` für die vollständige,
laufend aktuelle Statuszusammenfassung.

## v0.7.0 - Temp-/Festplatten-Bereinigung, Phase 4 (ADR-023, 02.07.2026)

Vierter v0.7-Baustein ("PC-Admin", Handbook Kap. 13/17) - erster
löschender PC-Admin-Command.

### Neu
- Optionaler `preview(plan) -> Optional[str]`-Hook in
  `executor/executor.py` (erste Änderung an dieser Datei in der
  gesamten v0.7-Entwicklung): Commands können vor der Bestätigung
  einen frisch berechneten Vorschau-Text anzeigen lassen. Commands
  ohne `preview()` (alle bisherigen) verhalten sich exakt wie zuvor -
  vollständig rückwärtskompatibel, verifiziert durch neue
  Regressionstests. Kein Zugriff für Commands auf `SpeechEngine`.
- `commands/monitor.py::AnalyzeTempFilesCommand` (Intent
  `analyze_temp_files`, Sicherheitsstufe 0): zeigt Anzahl und
  Gesamtgröße der Temp-Dateien (älter als 24h) im Benutzer-Temp-Ordner.
- `commands/monitor.py::CleanTempFilesCommand` (Intent
  `clean_temp_files`, Sicherheitsstufe 3, Bestätigungsphrase
  `BEREINIGEN`): löscht diese Dateien unwiderruflich. Nutzt den neuen
  `preview()`-Hook für eine exakte Vorschau vor der Bestätigung -
  `execute()` scannt unabhängig davon erneut, verlässt sich nie auf
  das Vorschau-Ergebnis.
- Beschränkt auf `%TEMP%` (kein `C:\Windows\Temp`, keine
  Administratorrechte), nur Dateien älter als 24h, nur Dateien
  (nie Ordner). Pfad-Eindämmung gegen Ziele außerhalb von `%TEMP%`.
  Gesperrte/bereits verschwundene Dateien werden einzeln
  übersprungen, kein Totalausfall.
- Beide neuen Commands bleiben in `commands/monitor.py` (kein neues
  Modul, KISS/YAGNI, Product-Owner-Entscheidung).
- 23 neue Tests (`tests/test_commands_monitor.py`,
  `tests/test_executor.py`) - 225 Tests gesamt, alle grün.

### Bewusst nicht enthalten (Phase 4)
- Papierkorb leeren (explizit nicht Bestandteil von ADR-023).
- `C:\Windows\Temp`, Administratorrechte/Elevation.
- Browser-Cache/-Profile, Registry-Cleaner.
- Dienste-Verwaltung, Treiber-Aktualisierung (weiterhin offene
  Kap.-17-Bausteine).

## v0.7.0 - Autostart verwalten, Phase 3 (ADR-022, 02.07.2026)

Dritter v0.7-Baustein ("PC-Admin", Handbook Kap. 13/17) - erster
schreibender PC-Admin-Command.

### Neu
- `commands/monitor.py::DisableAutostartEntryCommand`/
  `EnableAutostartEntryCommand` (Intents `disable_autostart_entry`/
  `enable_autostart_entry`, Sicherheitsstufe 2, Ja/Nein-Bestätigung,
  kein `confirmation_phrase`): deaktivieren/aktivieren
  Autostart-Einträge anhand des Namens - beschränkt auf HKCU Run-Key
  und Startup-Ordner (Benutzer), kein HKLM, keine Administratorrechte.
- Deaktivieren entfernt Registry-Einträge aus dem echten Run-Key und
  sichert sie im Klartext in einem eigenen Jarvis-Registry-Zweig
  (`HKCU\Software\Jarvis\DisabledAutostart\Run`) - bewusst kein
  Nachbilden des internen `StartupApproved`-Binärformats. Startup-
  Ordner-Einträge werden per Datei-Verschieben in einen
  Jarvis-Unterordner (`_jarvis_disabled`) deaktiviert. Nie löschen.
- Namensbasierte Zielauflösung, `NEEDS_CLARIFICATION` bei
  Mehrdeutigkeit, präzise Fehlermeldung bei Treffern außerhalb des
  Scopes (HKLM/Alle-Benutzer), idempotentes Verhalten bei bereits
  deaktivierten/aktiven Einträgen. Kein Blacklist-Mechanismus, kein
  KI-Zugriff.
- `_collect_startup_folder_autostart()` (ADR-020) filtert jetzt auf
  Dateien (`is_file()`) - verhindert, dass der neue
  `_jarvis_disabled`-Unterordner in `analyze_pc`-Berichten auftaucht.
- Beide neuen Commands bleiben in `commands/monitor.py` (kein neues
  Modul, KISS/YAGNI, Product-Owner-Entscheidung).
- 22 neue Tests (`tests/test_commands_monitor.py`) - 202 Tests gesamt,
  alle grün.

### Bewusst nicht enthalten (Phase 3)
- HKLM-Schreibzugriff, Administratorrechte/Elevation.
- Startup-Ordner (Alle Benutzer) schreibend.
- `StartupApproved`-Binärformat, Blacklist/Ausnahmelisten.
- Löschen, neue Autostart-Einträge erstellen, Bearbeiten bestehender
  Befehle/Pfade, separates Rollback-/Undo-Log-System.
- Dienste-Verwaltung, Bereinigung, Treiber-Aktualisierung (weiterhin
  offene Kap.-17-Bausteine).

## v0.7.0 - Ereignisprotokoll-Analyse, Phase 2 (ADR-021, 02.07.2026)

Zweiter v0.7-Baustein ("PC-Admin", Handbook Kap. 13/17).

### Neu
- `commands/monitor.py::AnalyzeEventLogCommand` (Intent
  `analyze_event_log`, Sicherheitsstufe 0, keine Bestätigung nötig):
  liest die jüngsten Fehler/Warnungen aus dem Windows-Ereignisprotokoll
  (`System` und `Application`) über `wevtutil` (Windows-Bordmittel,
  `subprocess`, keine neue Abhängigkeit) - serverseitig gefiltert auf
  Level Error/Warning, begrenzt auf 20 Einträge je Log, kein
  kompletter Dump. Ausgabeformat `/f:RenderedXml` für sprachversions-
  unabhängiges Parsen. Python sammelt/strukturiert deterministisch,
  die KI formuliert nur den Bericht - gleicher Pflicht-Disclaimer wie
  `analyze_pc`/`calculate_kpi`.
- Jede der zwei Log-Quellen einzeln abgesichert (Teilergebnis statt
  Totalausfall, wie die vier Autostart-Quellen in ADR-020) - schlagen
  beide fehl, liefert der Command `Status.FAILED` ohne KI-Aufruf.
- Nutzt die bereits vorhandene `configure()`-Infrastruktur aus
  `commands/monitor.py` (ADR-020/ADR-015) - keine Änderung an
  `main.py` nötig.
- 16 neue Tests (`tests/test_commands_monitor.py`) - 180 Tests gesamt,
  alle grün.

### Bewusst nicht enthalten (Phase 2)
- Security-Log (sensibler, eigene spätere Diskussion).
- Löschen von Log-Einträgen, automatische Reparaturmaßnahmen.
- Dienste-Verwaltung, Autostart-Schreibzugriff, Bereinigung,
  Treiber-Aktualisierung (weiterhin offene Kap.-17-Bausteine).

## v0.7.0 - PC-Analyse, Phase 1 (ADR-020, 02.07.2026)

Erster v0.7-Baustein ("PC-Admin", Handbook Kap. 13/17).

### Neu
- `commands/monitor.py::AnalyzePcCommand` (Intent `analyze_pc`,
  Sicherheitsstufe 0, keine Bestätigung nötig): erstellt einen
  PC-Gesundheitsbericht aus Festplattenbelegung, Top-5-Prozessen nach
  CPU/RAM, mehrfach laufenden Prozessen und Autostart-Programmen
  (Registry Run-Keys HKCU+HKLM sowie Startup-Ordner). Python sammelt
  und strukturiert alle Daten deterministisch, die KI
  (`AIEngine.answer()`) formuliert nur den Bericht und interpretiert
  Auffälligkeiten - kein Nachrechnen. Pflicht-Disclaimer wie bei
  `analyze_report`/`calculate_kpi`.
- Eigenes, zu `commands/reports.py` bewusst dupliziertes
  `configure(ai_engine)`-Muster in `commands/monitor.py` (ADR-015) -
  keine gemeinsame Abstraktion, solange nur zwei Module KI-Zugriff
  brauchen. `main.py` verdrahtet zusätzlich `monitor_commands.configure(ai)`.
- `winreg`-Import mit `try/except ImportError` abgesichert - klare
  Fehlermeldung statt Absturz auf Nicht-Windows-Systemen.
- 12 neue Tests (`tests/test_commands_monitor.py`) - 164 Tests gesamt,
  alle grün.

### Bewusst nicht enthalten (Phase 1)
- Windows-Ereignisprotokoll (eigener Kap.-17-Punkt, separat zu
  priorisieren).
- Optimierung/Bereinigung, Registry-Änderungen, Dienste-Verwaltung,
  Treiber-Aktualisierung.
- Keine Änderung an `core/ai.py`, `core/planner.py`,
  `core/tool_manager.py`, `executor/executor.py` oder anderen
  `commands/*.py`-Dateien.

### Siehe auch
- ADR-020 (docs/adr/ADR-020.md)

## v0.6 - Handy: Telegram-Fernzugriff (abgeschlossen, getaggt, 02.07.2026)

Manueller Smoke-Test (Handbook Kap. 14/15/28) mit echtem Bot-Token/Chat
durchgeführt und vom Product Owner am 02.07.2026 ausdrücklich bestätigt:
Bot startet, Verbindung zu Telegram, `chat`/`remember_fact`/`forget_fact`/
`system_status` funktionieren, nicht erlaubte Befehle werden korrekt
abgelehnt, sauberer Shutdown, keine ERROR-Einträge im Log. Damit sind die
allgemeinen Definition-of-Done-Kriterien (Kap. 28) erfüllt. Tag `v0.6`
gesetzt. Handbook auf v3.5 aktualisiert (siehe eigener Abschnitt unten) -
v0.6 ist damit als Gesamtversion abgeschlossen.

## Handbook v3.5 - v0.6-Abschluss, Fernzugriff-Sicherheitsprinzip (ADR-019, 02.07.2026)

Kein Code-Release - reine Dokumentations-/Governance-Aktualisierung nach
Abschluss von v0.6 (Tag `v0.6` gesetzt), gemäß der in Kap. 2 festgelegten
Regel ("Handbook wird nur zwischen zwei Versionen geändert").

### Geändert
- `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_5.docx` neu (v3.2/v3.3/v3.4
  bleiben als Archiv erhalten): Kap. 13 (Roadmap) aktualisiert - v0.6 als
  abgeschlossen markiert, Lerninhalte-Spalte auf das tatsächlich Genutzte
  (python-telegram-bot/Long-Polling) korrigiert; Kap. 16 (Handy-Anbindung)
  präzisiert - Telegram-Bot als umgesetzte Lösung, Web-Interface/WireGuard
  VPN ausdrücklich als Alternativen ohne Pflichtcharakter, Eigene App
  Langzeitziel; Kap. 10 (Sicherheitsmodell) um ein dauerhaftes
  Fernzugriff-Sicherheitsprinzip ergänzt (gilt für alle künftigen
  Fernzugriffskanäle, nicht nur Telegram); Kap. 27 um "Präzisierung v3.5:
  v0.6 Abschluss" ergänzt; Kap. 28 (Definition of Done) um einen neuen
  Abschnitt "v0.6 - spezifisch (Telegram-Fernzugriff)" ergänzt (inkl.
  bestandenem manuellem Smoke-Test); Kap. 29 (Backlog) um die künftige
  Generalisierung der Post-Arbeitsmodule ergänzt (Product-Owner-Hinweis,
  keine Architekturänderung).
- `docs/AI_START.md`, `README.md`, `docs/PROJECT_STATE.md` verweisen
  jetzt auf `JARVIS_MASTER_HANDBOOK_v3_5.docx`.
- Vollständiger Text-Diff zwischen v3.4 und v3.5 geprüft - ausschließlich
  die oben genannten, beabsichtigten Änderungen, keine Kollateralschäden
  in unveränderten Kapiteln.

### Siehe auch
- ADR-019 (docs/adr/ADR-019.md)

## v0.6.0 - Telegram-Fernzugriff, Phase 1 (ADR-018, 01.07.2026)

Erster v0.6-Baustein ("Handy", Handbook Kap. 13/16). Separater
Einstiegspunkt, main.py/Konsole unverändert.

### Neu
- `telegram_main.py`: Long-Polling über `python-telegram-bot` (kein
  Webhook/FastAPI/ngrok). Verdrahtet dieselbe Pipeline wie `main.py`
  (`Config`/`AIEngine`/`Planner`/`Executor`/`JsonMemoryStore`/
  `LongTermMemory`) mit Telegram statt Konsole als Kanal.
- Sicherheitsbeschränkungen (Phase 1, ausschließlich in
  `telegram_main.py`, keine Änderung an `core/ai.py`/`Planner`/
  `Executor`/`ToolManager`/`commands/*.py`):
  - Intent-Whitelist `chat`/`remember_fact`/`forget_fact`/
    `system_status` - alles andere abgelehnt.
  - Zusätzlicher, unabhängiger Check auf `requires_confirmation`
    (Sicherheitsstufe 2/3 bleibt gesperrt, auch falls die Whitelist
    später erweitert würde).
  - Mehrschritt-Pläne mit mindestens einem nicht erlaubten Schritt
    werden komplett abgelehnt (keine Teilausführung).
  - Autorisierung über eine einzelne Chat-ID
    (`JARVIS_TELEGRAM_ALLOWED_CHAT_ID`), Bot-Token
    (`JARVIS_TELEGRAM_BOT_TOKEN`) - beide ausschließlich als
    Umgebungsvariable, nie in `config.json`/Git.
  - `TelegramSpeech`-Adapter (erfüllt `SpeechEngine`-Schnittstelle für
    `Executor`) ist fail-closed: `listen()` liefert `""`, `say()`
    loggt nur - beide sollten in Phase 1 nie aufgerufen werden.
- `requirements.txt`: `python-telegram-bot` als optionale Abhängigkeit
  (wie die TTS-Backends) - nur nötig für `telegram_main.py`.
- 18 neue Tests (`tests/test_telegram_main.py`) - 152 Tests gesamt,
  alle grün.

### Bewusst nicht enthalten (Phase 1)
- Kein gleichzeitiger Betrieb von Konsole und Telegram.
- Keine Excel-/Report-/KPI-Dateizugriffe, kein `install_program`, kein
  `shutdown_pc` über Telegram.
- Kein Neustart-Mechanismus bei Absturz des Long-Polling-Prozesses.

### Siehe auch
- ADR-018 (docs/adr/ADR-018.md)

## Handbook v3.4 - v0.5-Abschluss, Power-BI-Backlog, Governance-Regel (ADR-017, 01.07.2026)

Kein Code-Release - reine Dokumentations-/Governance-Aktualisierung nach
Abschluss von v0.5 (Tag `v0.5` gesetzt), gemäß der in Kap. 2 festgelegten
Regel ("Handbook wird nur zwischen zwei Versionen geändert").

### Geändert
- `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_4.docx` neu (v3.2/v3.3 bleiben
  als Archiv erhalten): Kap. 13 (Roadmap) aktualisiert - v0.5 als
  abgeschlossen markiert, Power BI aus aktivem Scope genommen; Kap. 27
  um "Präzisierung v3.4: v0.5 Abschluss" ergänzt; Kap. 28 (Definition of
  Done) um Abschnitte für Tabellen-Auswertung und KPI erweitert (inkl. der
  Vorgabe "deterministische Berechnung, KI nur zur Interpretation" bei
  KPI); Kap. 29 (Backlog) um "Power BI-Integration" ergänzt; Kap. 19
  (Governance) um eine generalisierte Regel ergänzt, wie mit
  Product-Owner-Entscheidungen zwischen zwei Handbook-Versionen
  umgegangen wird.
- `docs/AI_START.md`, `README.md`, `docs/PROJECT_STATE.md` verweisen
  jetzt auf `JARVIS_MASTER_HANDBOOK_v3_4.docx`.
- Vollständiger Text-Diff zwischen v3.3 und v3.4 geprüft - ausschließlich
  die oben genannten, beabsichtigten Änderungen, keine Kollateralschäden
  in unveränderten Kapiteln.

### Siehe auch
- ADR-017 (docs/adr/ADR-017.md)

## v0.5 - Arbeitsmodule: Excel lesen, Tabellen-Auswertung, KPI (aktiver Scope abgeschlossen, 01.07.2026)

Alle drei von Wolfgang priorisierten aktiven v0.5-Bausteine sind
umgesetzt: Excel lesen (v0.5.0, ADR-014), Tabellen-Auswertung/Auswertung-
Analyse (v0.5.1, ADR-015), KPI/Kennzahl (v0.5.2, ADR-016).
134/134 Tests grün. **Power BI ist bewusst NICHT enthalten** -
Product-Owner-Entscheidung (01.07.2026): liegt auf dem Firmenrechner/
im Firmenumfeld, keine praktische Implementierbarkeit im aktuellen
Rahmen. Behandelt als optionale Unternehmensintegration/späterer
Baustein, kein Codeverstoß gegen Handbook Kap. 13/27 - die Entscheidung
gilt bis zur nächsten Handbook-Version (Kap. 2) als verbindliche
Arbeitsgrundlage. Siehe `docs/PROJECT_STATE.md` für die finale
Statuszusammenfassung.

## v0.5.2 - KPI: Kennzahl (ADR-016, 01.07.2026)

Dritter Arbeitsmodule-Baustein - baut auf `read_workbook_sheets()` und
der `AIEngine`-Injection aus v0.5.1 auf. Damit sind alle drei aktiven
v0.5-Bausteine (Excel lesen, Tabellen-Auswertung, KPI) laut Wolfgangs
Reihenfolge umgesetzt. Power BI ist bewusst NICHT enthalten
(Product-Owner-Entscheidung, siehe `docs/PROJECT_STATE.md`).

### Neu
- `commands/reports.py::CalculateKpiCommand` (Intent `calculate_kpi`,
  Sicherheitsstufe 0, keine Bestätigung nötig): berechnet die
  Kennzahl je Standort **deterministisch in Python**
  (Ist-Wert, Abweichung, "unter Zielwert"). Die KI
  (`AIEngine.answer()`) interpretiert nur die bereits berechnete
  Tabelle - sie rechnet nichts nach. `Result.data["kpi"]` enthält die
  berechneten Zahlen selbst.
- Spalten-Erkennung über feste, case-insensitive Alias-Listen
  (Standort: `standort`/`ort`/`ort`/`standort`; Ist-Wert:
  `ist`/`istwert`/`wert`/`quote`/`kennzahl`/
  `kennzahl`). Keine oder mehrere Treffer → Rückfrage/
  Fehler statt Raten.
- `parameters.zielwert` als Pflichtparameter (`NEEDS_CLARIFICATION`
  wenn nicht genannt).
- 17 neue Tests (`tests/test_commands_reports.py`) - 134 Tests
  gesamt, alle grün.

### Bewusst nicht enthalten
- Keine KI-Arithmetik - explizite Korrektur durch Wolfgang gegenüber
  dem ersten technischen Vorschlag (KI hätte selbst rechnen sollen).
- Power BI - aus dem aktiven v0.5-Scope genommen.

### Siehe auch
- ADR-016 (docs/adr/ADR-016.md)

## v0.5.1 - Tabellen-Auswertung: Datenauswertung (ADR-015, 01.07.2026)

Zweiter Arbeitsmodule-Baustein - baut auf Excel-Lesen (v0.5.0) auf.

### Neu
- `commands/reports.py::AnalyzeReportCommand` (Intent
  `analyze_report`, Sicherheitsstufe 0, keine Bestätigung
  nötig): liest einen Datentabelle (`.xlsx`/`.xlsm`) und lässt
  `AIEngine.answer()` die Daten analysieren. Jede Antwort endet mit
  einem Pflicht-Disclaimer ("Analyse auf Basis der gelieferten Daten.
  Bitte vor Entscheidungen prüfen.").
- Erster Command mit direktem KI-Zugriff: `AIEngine` wird per
  `commands.reports.configure(ai)` injiziert (analog zum
  Memory-Muster, ADR-009), von `main.py` einmal beim Start aufgerufen.
  Der `Executor` bleibt dafür unverändert.
- 7 neue Tests (`tests/test_commands_reports.py`, `AIEngine` und
  Excel-Lesefunktion gemockt) - 117 Tests gesamt, alle grün.

### Geändert
- `commands/excel.py`: Lese-Logik aus `ReadExcelCommand.execute()` in
  eine wiederverwendbare Funktion `read_workbook_sheets()` (plus
  `ExcelReadError`) extrahiert - `ReadExcelCommand` verhält sich
  unverändert (bestehende Tests weiterhin grün), `analyze_report`
  nutzt dieselbe Funktion (DRY).
- `main.py`: `reports_commands.configure(ai)` zusätzlich verdrahtet.

### Bekannter Stolperstein (gefunden und behoben)
- Ein `from core.ai import AIEngine` auf Modulebene in
  `commands/reports.py` hätte je nach Importreihenfolge einen
  `ImportError` durch einen Zirkelimport mit `core/ai.py` ausgelöst
  (`core.ai` importiert `commands.REGISTRY`). Reproduziert und über
  einen `TYPE_CHECKING`-Import gelöst (kein Laufzeit-Import nötig).

### Bewusst nicht enthalten (Phase 1)
- Keine neue `ai.py`-Methode - `answer()` wiederverwendet, bis sich
  das als unzureichend erweist.

### Siehe auch
- ADR-015 (docs/adr/ADR-015.md)

## v0.5.0 - Excel-Lesen, Phase 1 (ADR-014, 01.07.2026)

Erster Arbeitsmodule-Baustein (Handbook Kap. 13/27, v3.3) - Wolfgang hat
Excel-Lesen vor Tabellen-Auswertung/KPI/Power BI priorisiert.

### Neu
- `commands/excel.py::ReadExcelCommand` (Intent `read_excel`,
  Sicherheitsstufe 0, keine Bestätigung nötig): liest `.xlsx`/`.xlsm`-
  Dateien über `openpyxl` (`read_only=True, data_only=True`).
  Arbeitsblätter + Dimensionen im Ergebnistext, Zelldaten (pro Blatt
  auf 500 Zeilen begrenzt) in `Result.data["sheets"]`. Optional
  `parameters.sheet` für ein bestimmtes Arbeitsblatt.
- `requirements.txt`: `openpyxl` als feste Abhängigkeit.
- 9 neue Tests (`tests/test_commands_excel.py`, `openpyxl` gemockt) -
  110 Tests gesamt, alle grün.

### Bewusst nicht enthalten (Phase 1)
- Schreiben, Formatieren, Power Query, Makros, `.xls` (Legacy-Format).
- Keine KI-Zusammenfassung im Command selbst - bleibt einem späteren
  Tabellen-Auswertung-Baustein überlassen.
- Kein Sonderfall in `core/ai.py` - die ausführliche `description` von
  `ReadExcelCommand` reicht über den bestehenden Registry-Mechanismus
  (ADR-007), verifiziert per direktem `build_system_prompt()`-Aufruf.

### Siehe auch
- ADR-014 (docs/adr/ADR-014.md)
- ADR-013 (docs/adr/ADR-013.md)

## Handbook v3.3 - Excel-Baustein (v0.5) Scope, Sicherheitsstufen, Governance (ADR-013, 01.07.2026)

Kein Code-Release (keine neue Jarvis-Version) - Governance-/Prozess-Update
vor Beginn von `v0.5`, ausgelöst durch eine Handbook-Prüfung und explizite
Product-Owner-Entscheidungen zum Excel-Baustein.

### Geändert
- `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_3.docx` neu (v3.2 bleibt als
  Archiv erhalten): Excel-Scope für v0.5 auf Phase 1/nur Lesen präzisiert
  (Schreiben, Formatieren, Power Query, Makros explizit NICHT enthalten),
  Sicherheitsstufen um Dateizugriffe ergänzt (Excel lesen = Stufe 0,
  Excel schreiben = Stufe 2, Datei löschen = Stufe 3), Outlook aus v0.5
  ausgeklammert, Architektur bleibt flach (keine Migration auf
  `tools/office/...` für v0.5), Definition of Done um v0.4-/v0.5-
  spezifische Kriterien ergänzt, Governance-Dokumente (`AI_START.md`,
  `PROJECT_STATE.md`, ADR-System) offiziell in Kap. 19 aufgenommen,
  neue Handbook-Versionierungsregel in Kap. 2 (Änderungen nur zwischen
  zwei Jarvis-Versionen).
- `docs/AI_START.md`, `docs/PROJECT_STATE.md`, `README.md` verweisen
  jetzt auf `JARVIS_MASTER_HANDBOOK_v3_3.docx`.
- `docs/PROJECT_STATE.md`: `Latest ADR` = ADR-013, `Next Planned Version`
  um den präzisierten Excel-Scope ergänzt.

### Nächster Schritt (noch NICHT umgesetzt)
- Technischer Vorschlag (Bibliothek, Commands, Registry-Integration)
  für den Excel-Lesen-Baustein - braucht explizite Freigabe durch den
  Product Owner, bevor Code geschrieben wird.

### Siehe auch
- ADR-013 (docs/adr/ADR-013.md)

## v0.4 - Kurz-/Langzeitgedächtnis + PC-Grundsteuerung (abgeschlossen, 01.07.2026)

`v0.4` ist laut Handbook Kap. 13/27 damit inhaltlich vollständig:
Kurz-/Langzeitgedächtnis (v0.4.0, `history.json` seit v0.2 bereits
persistent über Sitzungen hinweg) sowie PC-Grundsteuerung - öffnen
(seit v0.3), überwachen (v0.4.1, ADR-011) und installieren (v0.4.1,
ADR-012). 101/101 Tests grün. Siehe `docs/PROJECT_STATE.md` für die
finale Statuszusammenfassung.

## v0.4.1 - PC-Grundsteuerung: überwachen + installieren (ADR-011, ADR-012, 01.07.2026)

### Neu
- `commands/monitor.py::SystemStatusCommand` (Intent `system_status`,
  Sicherheitsstufe 0, keine Bestätigung nötig): liest CPU- und
  RAM-Auslastung über `psutil` aus. Erster Baustein von
  "PC-Grundsteuerung" (Handbook Kap. 27) neben dem bereits
  vorhandenen `open_program`. Temperatur bewusst nicht enthalten
  (unter Windows von `psutil` nicht unterstützt, siehe ADR-011).
- `commands/installer.py::InstallProgramCommand` (Intent
  `install_program`, Sicherheitsstufe 2, Bestätigung erforderlich):
  installiert Programme über `winget` (bekannte Namen wie `vlc` über
  exakte Package-ID, sonst Freitext-Suche). Zweiter und letzter für
  v0.4 vorgesehener Baustein von "PC-Grundsteuerung" (Handbook
  Kap. 27). "Deinstallieren" bewusst nicht enthalten (siehe ADR-012).
- `requirements.txt`: `psutil` von optional/auskommentiert zu einer
  festen Abhängigkeit.
- 11 neue Tests (`tests/test_commands_monitor.py`,
  `tests/test_commands_installer.py`) - 101 Tests gesamt, alle grün.

### Siehe auch
- ADR-012 (docs/adr/ADR-012.md)
- ADR-011 (docs/adr/ADR-011.md)

### Dokumentation / Governance
- `docs/AI_START.md` als verbindlichen Einstiegspunkt fuer kuenftige
  KI-Agenten eingefuehrt.
- `docs/PROJECT_STATE.md` als kompakten, aus Handbook, Logbook,
  Changelog und ADRs abgeleiteten Projektstatus eingefuehrt.
- `docs/AI_START.md` um eine Stop-Regel bei Abweichung zu
  `docs/PROJECT_STATE.md` erweitert.
- `docs/PROJECT_STATE.md` formatiert bekannte Testfehler jetzt
  explizit als `Known Failure` statt nur als Roh-Ergebnis.
- `README.md` um den Abschnitt `AI / Agent Onboarding` erweitert.
- `ADR-010` dokumentiert die dokumentationsgetriebene
  Projektuebergabe fuer KI-Agenten.

## v0.4.0 - Langzeitgedächtnis (ADR-009, 01.07.2026)

Erstes "Next"-Feature nach v0.3 (Handbook Kap. 27) - Wolfgang hat
Langzeitgedächtnis priorisiert, mit expliziter Merk-Logik statt
automatischer Erkennung.

### Neu
- `memory/long_term.py::LongTermMemory` - kategorisierte Fakten
  (`projekt`/`gewohnheit`/`praeferenz`/`allgemein`), persistiert in
  `memory_data/long_term.json`, getrennt vom Gesprächsverlauf.
- `commands/memory.py`: `remember_fact`- und `forget_fact`-Commands
  (Sicherheitsstufe 1, keine Bestätigung nötig). Registrierung über
  `commands.memory.configure(memory_dir)`, einmal von `main.py`
  beim Start aufgerufen.
- `core/ai.py`: Intent-Prompt erklärt target-/category-Extraktion für
  die neuen Commands; `build_chat_system_prompt(long_term_summary)`
  hängt gemerkte Fakten optional an den Chat-System-Prompt an.
- 23 neue/geänderte Tests (u. a. End-to-End: merken -> in
  Chat-Antwort wiederfinden) - 90 Tests gesamt, alle grün.

### Geändert
- `AIEngine.answer()` und `Executor.run()` nehmen jetzt zusätzlich
  `long_term_summary: str = ""` entgegen und reichen es durch.
- `main.py` verdrahtet `LongTermMemory` neben dem bestehenden
  `JsonMemoryStore` und baut die Zusammenfassung pro Gesprächsrunde
  neu (damit gerade gemerkte Fakten sofort sichtbar sind).

### Siehe auch
- ADR-009 (docs/adr/ADR-009.md)

## v0.3.7 - TTS-Backend-Abstraktion (ADR-008, 01.07.2026)

### Neu
- `core/tts/` Package: `TTSBackend`-Protokoll +
  `PiperBackend`/`OpenAITTSBackend`/`ElevenLabsBackend`/`KokoroBackend`
  + `factory.create_backend(config)`.
- `Config`: neue Felder `tts_backend`, `openai_tts_model`,
  `openai_tts_voice`, `elevenlabs_api_key` (Env `ELEVENLABS_API_KEY`),
  `elevenlabs_voice_id`, `elevenlabs_model`, `kokoro_model_path`,
  `kokoro_voices_path`, `kokoro_voice`, `kokoro_lang`.
- 18 neue Tests (tests/test_tts_factory.py, tests/test_tts_backends.py,
  tests/test_speech.py neu geschrieben) - 67 Tests gesamt, alle grün.

### Geändert (Breaking Change intern)
- `core/speech.py`: `SpeechEngine.__init__` nimmt jetzt die komplette
  `Config` entgegen (`SpeechEngine(config)`) statt einzelner
  Piper-Parameter. `main.py` entsprechend angepasst.
- Piper bleibt Standard-Backend (`tts_backend: "piper"`) - keine
  Verhaltensänderung ohne aktive Umstellung in config.json.

### Bekannte Einschränkung
- Kokoro v1.0 unterstützt aktuell kein Deutsch - Backend vorhanden,
  aber für Wolfgangs deutsche Gespräche nicht empfohlen (siehe
  core/tts/kokoro_backend.py, README.md).

### Siehe auch
- ADR-008 (docs/adr/ADR-008.md)

## v0.3.6 - Dezente Persönlichkeit für den Chat-Modus (01.07.2026)

### Geändert
- `core/ai.py`: `CHAT_SYSTEM_PROMPT` um eine Persönlichkeitsbeschreibung
  erweitert (dezenter, trockener Humor im Stil des Film-Jarvis,
  ausdrücklich ohne Dauerwitzeln oder Häme bei Fehlern).

### Neu
- tests/test_ai.py: `test_chat_prompt_has_dezente_persoenlichkeit`
  (49 Tests gesamt, alle grün).

### Offen (Next, nicht Now)
- Stimme näher an Film-Jarvis: Piper-Stimmoptionen recherchiert
  (thorsten-high, karlsson, pavoque), Entscheidung Offline vs.
  Cloud-TTS steht noch aus - siehe docs/logbook.md.

## v0.3.5 - Registry-basierter SYSTEM_PROMPT (Review-Fix, 01.07.2026)

### Geändert
- `core/ai.py`: SYSTEM_PROMPT wird nicht mehr hart codiert, sondern
  über `build_system_prompt()` bei jedem `get_plan()`-Aufruf aus
  `commands.REGISTRY` gebaut (`_known_intents_text()`). Entfernt
  Phantom-Intents (`search_google`, `weather`), für die es keine
  Commands gibt.
- `commands/system.py`: `OpenProgramCommand` und `ShutdownPcCommand`
  haben jetzt ein `description`-Attribut, das im Prompt erscheint.

### Neu
- tests/test_ai.py: `test_system_prompt_is_built_from_registry_not_hardcoded`,
  `test_system_prompt_includes_command_descriptions` (48 Tests
  gesamt, alle grün).

### Hintergrund
- Ausgelöst durch externes Code-Review (GPT, Kap. 2 Review-Prozess).
  Behebt einen echten Widerspruch: README versprach "neue Commands
  ohne ai.py-Änderung", was vorher nicht stimmte.

### Siehe auch
- ADR-007 (docs/adr/ADR-007.md)

## v0.3 - Planner, Tool Manager, Executor (01.07.2026)

### Neu
- `core/planner.py::Planner` - zerlegt Nutzereingaben an einfachen
  Konnektoren ("und", "und dann", "danach", ";") in mehrere Schritte.
- `core/tool_manager.py::ToolManager` - löst pro Schritt das passende
  Tool aus der bestehenden Command-Registry auf.
- `executor/executor.py::Executor` - führt Schritte der Reihe nach
  aus, holt vor kritischen Aktionen (`requires_confirmation`) eine
  Bestätigung ein (Trockenlauf-Prinzip), meldet ✓/✗/? pro Schritt und
  bricht bei Fehlern/offenen Rückfragen ab.
- `AIEngine.answer()` - echte Konversationsantwort für den chat-Intent
  (vorher: leere Antwort, main.py sagte nur "Alles klar.").
- `Command.requires_confirmation`-Flag auf `OpenProgramCommand`
  (False) und `ShutdownPcCommand` (True).
- Unit-Tests: test_ai.py, test_commands.py, test_memory.py,
  test_planner.py, test_executor.py, test_integration.py (End-to-End-
  Smoke-Test mit gefälschter AIEngine, kein echter API-Key nötig).

### Geändert
- `main.py` verdrahtet jetzt Planner -> Executor statt direkt
  `ai.get_plan()` + `commands.dispatch()`.

### Siehe auch
- ADR-004 (docs/adr/ADR-004.md)

## v0.2.1 - Stabilisierung (Patch, kein neuer Scope)

- `Plan.confidence: float = 1.0` - Grundlage für spätere Rückfrage-
  Logik bei unsicheren Intents.
- `Config`: `temperature`, `timeout`, `max_tokens` ergänzt, keine
  Magic Values mehr in `ai.py`.
- `AIEngine` nutzt Structured Outputs (`response_format=json_schema`)
  statt freiem JSON-Text.

## v0.2 - Refactoring (29.06.2026)

### Neu
- Modulare Struktur (speech.py, ai.py, commands.py, config.py)
- Gesprächsverlauf (letzte 20 Nachrichten)

### Geändert
- Hauptlogik in main.py deutlich reduziert

### Behoben
- pyttsx3.init() wird nicht mehr bei jedem Sprechen neu initialisiert

## v0.3.1 - Bugfix nach Live-Test (01.07.2026)

### Behoben
- `AIEngine.get_plan()`: `response_format` von strict `json_schema`
  auf `json_object` umgestellt - das strict Schema wurde von der
  OpenAI-API abgelehnt (400 Bad Request), weil das offene
  `parameters`-Objekt `additionalProperties: false` bräuchte, was
  seinem Zweck widerspricht. Siehe docs/logbook.md.

## v0.3.2 - Bugfix nach Live-Test (01.07.2026)

### Behoben
- `OpenProgramCommand`: unter Windows wird jetzt `os.startfile()`
  statt `shutil.which()` + `subprocess.Popen()` verwendet.
  `shutil.which()` prüft nur PATH und findet z. B. Excel nicht, obwohl
  installiert. Windows löst Programmnamen stattdessen über die
  "App Paths"-Registry auf (wie Startmenü/Ausführen-Dialog). Siehe
  docs/logbook.md.

## v0.3.3 - Piper TTS (01.07.2026)

### Neu
- `SpeechEngine.say()`: Sprachausgabe über Piper TTS (lokal/offline),
  wenn `tts_enabled: true`, Paket + Modell vorhanden und Windows.
  Automatischer, absturzfreier Fallback auf Konsolenausgabe sonst.
- `Config`: `tts_enabled` (Default `false`), `tts_model_path`.
- `tests/test_speech.py` (fehlte bisher komplett - jetzt 8 Tests).
- README: neuer Abschnitt "Piper TTS einrichten".

### Siehe auch
- ADR-005 (docs/adr/ADR-005.md)

Damit ist die v0.3 Definition of Done (Handbook Kap. 28) inhaltlich
vollständig - offen ist nur noch das Git-Tagging (siehe Logbook).

## v0.3.4 - Sicherheitsfix nach Live-Vorfall (01.07.2026)

### Behoben (Sicherheitskritisch)
- "Ende" (und andere Abschiedsworte) beenden Jarvis jetzt direkt,
  bevor sie überhaupt an die KI gehen - vorher konnte "Ende"
  fälschlich als `shutdown_pc` interpretiert werden.
- `AIEngine`-SYSTEM_PROMPT verbietet explizit, Abschiedsworte als
  `shutdown_pc` zu werten.
- Neues Command-Attribut `confirmation_phrase`: Sicherheitsstufe-3-
  Aktionen (aktuell: `shutdown_pc`) verlangen jetzt das exakte
  Eintippen einer Bestätigungsphrase ("HERUNTERFAHREN") statt eines
  einfachen "ja". Ein einzelnes "ja" führte zuvor versehentlich zu
  einem echten PC-Shutdown - siehe docs/adr/ADR-006.md.

### Tests
- 5 neue Tests (test_main.py, test_executor.py, test_commands.py) -
  46 Tests insgesamt, alle grün.
