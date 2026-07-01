# Changelog

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
