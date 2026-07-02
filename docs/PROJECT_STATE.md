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

Tests: `225 / 225` grün.

Aus v0.6/v0.5/v0.4 weiterhin gültig: Telegram-Fernzugriff (ADR-018), Excel-Lesen/Tabellen-Auswertung/KPI (ADR-014/015/016), Kurz-/Langzeitgedächtnis (ADR-009), PC-Grundsteuerung (ADR-011/012) - siehe Handbook Kap. 13/27 für den vollständigen Roadmap-Stand.

## Next Planned Version
`v0.7` ist vollständig abgeschlossen (Handbook v3.6, Tag `v0.7`). `v0.8 "Multi-KI"` (Handbook Kap. 13: "Claude + GPT + Copilot orchestrieren") ist der nächste geplante Baustein - noch nicht begonnen, kein technischer Vorschlag erstellt. Vor v0.8 steht architektonisch der Jarvis-Eigenstart-Baustein, dessen Implementierung jedoch auf die Runtime-Architektur wartet (siehe unten) - noch kein Code, keine Umsetzung.

## Architekturrichtung: Jarvis-Runtime (Kap. 19 - wartet auf künftige Konsolidierung)
Product-Owner-Entscheidung 2026-07-02 (rein architektonisch, kein Code, keine ADR, keine Handbook-Änderung jetzt): Da das Handbook laut Kap. 2 nur zwischen zwei Hauptversionen geändert wird und v3.6 gerade erst konsolidiert wurde, wird diese Entscheidung hier vollständig festgehalten (ab sofort maßgeblich, Kap. 19) und erst bei der nächsten Konsolidierung (nach Abschluss des Runtime-Bausteins oder spätestens v0.8) formal ins Handbook übernommen.

**Auslöser:** Wolfgang möchte langfristig ein eigenes UI im Stil von Film-Jarvis (UI, Tray, Wake Word, Telegram, Core sollen koordiniert zusammenspielen). Der Windows-Autostart soll deshalb nicht fest auf `main.py` (Konsolenmodus) gebaut werden, da das die spätere UI-Architektur vorwegnehmen würde.

**Entscheidung:**
- Neuer, künftiger Runtime-Einstiegspunkt **`jarvis_runtime.py`** (Name festgelegt, noch nicht implementiert) - koordiniert später mehrere gleichzeitige Kanäle (UI, Tray, Wake-Word, Telegram) über einen einmalig instanziierten Core-Stack (Config/AIEngine/Planner/ToolManager/Executor/Memory). Kein Ersatz der bestehenden Kern-Architektur (Handbook Kap. 7) - reine Koordinationsschicht darüber.
- **Koexistenz statt Ablösung:** `main.py` bleibt dauerhaft der lokale Konsolen-/Entwicklungsmodus. `telegram_main.py` bleibt dauerhaft ein eigenständiger, einfacher Telegram-Einstiegspunkt - wird **nicht** entfernt oder als obsolet markiert. Die künftige Runtime kann Telegram später zusätzlich als einen ihrer Kanäle einbinden (Koexistenz mit `telegram_main.py`, keine Ablösung).
- **Jarvis-Eigenstart-Implementierung verschoben:** Die im vorherigen technischen Vorschlag ausgearbeitete Mechanik (HKCU Run-Key, Sicherheitsstufe 2, zwei symmetrische Intents `enable_jarvis_autostart`/`disable_jarvis_autostart`, `sys.executable`+`BASE_DIR`-Pfadermittlung, Pfad-Quoting) bleibt inhaltlich gültig, zielt aber künftig auf `jarvis_runtime.py` statt `main.py`. Implementierung wartet auf die Existenz der Runtime - kein Autostart jetzt.
- **Größtes offenes Architekturrisiko für die künftige Runtime-Umsetzung:** `memory_data/`-Dateien haben kein Locking - ADR-018 umgeht das nur durch "ein Kanal zur Zeit" (kein gleichzeitiger Betrieb Konsole/Telegram). Mehrere gleichzeitige Kanäle unter der Runtime brauchen eine Lösung dafür - empfohlen (nicht entschieden): einfache serialisierte Warteschlange statt echter Nebenläufigkeits-Sicherheit in Memory/Executor.
- **`telegram_main.py`/Runtime-Verhältnis:** offen, ob die Runtime Telegram über den bestehenden `TelegramSpeech`-Adapter wiederverwendet oder eigenständig neu anbindet - Entscheidung erst bei tatsächlicher Runtime-Umsetzung.

**ADR-Bedarf:** Keine ADR jetzt (reine Architekturrichtung, kein Code). Bei tatsächlicher Umsetzung vermutlich zwei ADRs: eine für die Runtime selbst, eine für den Jarvis-Eigenstart-Command mit Ziel Runtime.

## Tests
Letzter Check am 2026-07-02: `pytest tests -v` mit zusätzlichem `PYTHONPATH`.

### Test Status
`225 / 225` bestanden

### Known Failure
Keiner aktuell.

## Offene Aufgaben

### Technische TODOs (Definition of Done / Betrieb, kein neuer Scope)
- Manueller Live-Test der übrigen Kernfunktionen mit echtem API-Key auf dem echten Windows-Rechner (Definition of Done, Handbook Kap. 28) - bisher nur automatisiert/gemockt getestet. `install_program` real ausführen ist ein bewusster, expliziter Schritt und sollte gezielt vom Product Owner freigegeben/begleitet werden.
- Piper-Sprachmodell herunterladen und `tts_enabled: true` für einen Live-TTS-Test setzen.
- `.git_broken_5/` (Reste eines frühen, abgebrochenen git-init-Versuchs) liegt noch im Arbeitsordner, per `.gitignore` ausgeschlossen - bewusst nicht gelöscht (keine destruktive Aktion ohne Rückfrage).

### Feature-TODOs (nächste Roadmap-Bausteine, NICHT jetzt umsetzen)
- Jarvis-Runtime (`jarvis_runtime.py`) und darauf aufbauender Jarvis-Eigenstart - siehe Abschnitt "Architekturrichtung: Jarvis-Runtime" oben. Kein Code, keine Umsetzung.

Vollständige, aktuelle Liste jetzt im Handbook (Kap. 13 Roadmap, Kap. 29 Backlog) - hier nur technische Detail-Notizen, die (noch) keinen eigenen Handbook-Backlog-Eintrag brauchen:
- Dritter KI-Verwender: falls ein weiteres Modul KI-Zugriff braucht, `configure()`-Duplizierung (`reports.py`/`monitor.py`) zu einer gemeinsamen Abstraktion zusammenführen prüfen (Wolfgangs Entscheidung bei ADR-020).
- Den `preview()`-Hook (ADR-023) für weitere schreibende PC-Admin-Commands (Dienste, Treiber) nutzen, sobald diese umgesetzt werden.
- Alias-Liste für Standort-/Ist-Wert-Spalten (ADR-016) erweitern, sobald sich an echten Reports zeigt, dass andere Spaltennamen gebraucht werden.
- Eigene `AIEngine.summarize_report()`-Methode - nur prüfen, falls die Wiederverwendung von `answer()` sich als inhaltlich unzureichend erweist (ADR-015).
- Verknüpfungsziele im Startup-Ordner auflösen (bräuchte `pywin32`) - bewusst nicht in Phase 1, nur Dateinamen (ADR-020).

Im Code wurden keine `TODO`-/`FIXME`-Marker gefunden.

## Latest ADR
`ADR-023 - Temp-/Festplatten-Bereinigung (v0.7 Phase 4) - optionaler preview()-Hook im Executor, immer frischer Scan`

## Latest Architecture Change
`executor/executor.py` bekommt einen optionalen `preview(plan) -> Optional[str]`-Hook - die erste Änderung an dieser Datei in der gesamten v0.7-Entwicklung. Commands ohne `preview()` verhalten sich exakt wie zuvor (rückwärtskompatibel, per Regressionstests verifiziert). `CleanTempFilesCommand` nutzt den Hook, verlässt sich aber nie auf das Vorschau-Ergebnis - `execute()` scannt beim tatsächlichen Löschen immer erneut. Details: ADR-023.

## Known Limitations
- Langzeitgedächtnis funktioniert nur auf Zuruf; keine automatische Fakten-Extraktion.
- Mikrofon/Wake-Word weiterhin nicht umgesetzt.
- Kokoro TTS unterstützt aktuell kein Deutsch.
- `system_status`/`analyze_pc`: keine Temperatur (psutil-Limitierung unter Windows).
- `read_excel`/`analyze_report`/`calculate_kpi`: nur `.xlsx`/`.xlsm`, nur Werte, 500 Zeilen/Blatt.
- `telegram_main.py`: nur vier Intents erreichbar, kein gleichzeitiger Betrieb mit der Konsole, `TelegramSpeech.listen()` fail-closed (ADR-018).
- `analyze_pc`/`analyze_event_log`/`disable_/enable_autostart_entry`/`analyze_/clean_temp_files`: alle Windows-exklusiv, jeweiliger Scope siehe Handbook Kap. 17 (Umsetzungsstand-Annotationen).

## Git
Initial-Commit getaggt als `v0.4`. Danach Handbook v3.3/ADR-013, Excel-Lesen (ADR-014), Tabellen-Auswertung (ADR-015), Power-BI-Scope-Entscheidung, KPI (ADR-016), v0.5-Abschluss, getaggt als `v0.5`. Danach Handbook v3.4/ADR-017, Telegram-Fernzugriff (ADR-018), getaggt als `v0.6`, danach Handbook v3.5/ADR-019 inkl. Kap.-2-Konsistenzkorrektur. Danach `48f0f83` (PC-Analyse, ADR-020), `5f330fb` (Ereignisprotokoll-Analyse, ADR-021), `efe067f` (PROJECT_STATE-Korrektur), `b108c06` (Autostart-Verwaltung, ADR-022), `a765c9d` (Temp-Bereinigung, ADR-023), `920e32c` (v0.7-Abschlussdokumentation), `a7eb86d` (Handbook v3.6, Entwicklungsprozess-Konsolidierung) - getaggt als `v0.7`. Frühere Versionen (v0.1-v0.3) existieren nur als Text in `docs/CHANGELOG.md`/`docs/logbook.md`.
