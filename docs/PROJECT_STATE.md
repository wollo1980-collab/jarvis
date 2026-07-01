# PROJECT STATE

Stand: 2026-07-01
Quelle: `README.md`, `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_4.docx`, `docs/logbook.md`, `docs/CHANGELOG.md`, `docs/adr/*.md`

## Current Version
`v0.6.0` (erster Baustein: Telegram-Fernzugriff, Phase 1) - `v0.6` als Gesamtversion ist NOCH NICHT getaggt (Phase 2 offen). `v0.4`/`v0.5` bleiben abgeschlossen und getaggt.

## Status
`v0.3`, `v0.4` und `v0.5` sind abgeschlossen und getaggt (`v0.4`, `v0.5`).
`v0.6 "Handy"` hat begonnen. Umgesetzt:
- **Telegram-Fernzugriff, Phase 1** (`telegram_main.py`, ADR-018): separater Einstiegspunkt (Long-Polling über `python-telegram-bot`, kein Webhook/FastAPI/ngrok). Nur `chat`/`remember_fact`/`forget_fact`/`system_status` erreichbar (Sicherheitsstufe 0 + ausgewählte Stufe-1-Speicher-Interaktionen); Stufe 2/3/4 über zwei unabhängige Mechanismen gesperrt (Intent-Whitelist + `requires_confirmation`-Check). Mehrschritt-Pläne mit einem nicht erlaubten Schritt werden komplett abgelehnt. Autorisierung/Secrets ausschließlich über `JARVIS_TELEGRAM_BOT_TOKEN`/`JARVIS_TELEGRAM_ALLOWED_CHAT_ID` (Env-Var). Kein gleichzeitiger Betrieb von Konsole und Telegram. **Keine Änderung an `core/ai.py`, `core/planner.py`, `core/tool_manager.py`, `executor/executor.py`, `main.py` oder `commands/*.py`** (per `git diff --stat` verifiziert).
- Tests: `152 / 152` grün.

Aus v0.5 weiterhin gültig:
- **Excel-Lesen, Phase 1** (`commands/excel.py::ReadExcelCommand`, ADR-014), **Tabellen-Auswertung** (`commands/reports.py::AnalyzeReportCommand`, ADR-015), **KPI** (`commands/reports.py::CalculateKpiCommand`, ADR-016). Power BI weiterhin nicht enthalten (Handbook Kap. 29 Backlog, v3.4).

Aus v0.4 weiterhin gültig:
- **Kurz-/Langzeitgedaechtnis** (Handbook Kap. 9/13/27): Kurzzeit-Anteil (`memory/store.py::JsonMemoryStore`) persistiert Gespraechsverlauf tagesuebergreifend; Langzeit-Anteil (`memory/long_term.py::LongTermMemory`, ADR-009), nur auf ausdruecklichen Zuruf.
- **PC-Grundsteuerung** (Kap. 17/27): oeffnen (`open_program`), ueberwachen (`system_status`, ADR-011), installieren (`install_program`, ADR-012).

## Current Development Phase
`v0.6 "Handy"` laut Handbook Kap. 13 - Phase 1 (Telegram-Fernzugriff, eingeschränkter Befehlsumfang) umgesetzt. Phase 2 (Erweiterung des Befehlsumfangs/Sicherheitsstufen) ist NICHT begonnen - naechster Schritt ist eine Product-Owner-Entscheidung.

## Next Planned Version
Weiterhin `v0.6` - noch NICHT abgeschlossen/getaggt. Offene Entscheidung: v0.6 Phase 2 (mehr Intents/Sicherheitsstufen per Telegram) angehen, oder v0.6 mit dem aktuellen eingeschränkten Umfang als abgeschlossen betrachten und taggen. Kein technischer Vorschlag fuer Phase 2 bisher erstellt, kein Code geschrieben.

## Next Goal According To Handbook
`v0.5` ist inhaltlich vollstaendig und im Handbook (v3.4) selbst als abgeschlossen markiert. `v0.6 "Handy"` (Kap. 13: Telegram-Bot, Fernzugriff) hat mit Phase 1 begonnen (ADR-018). Handbook Kap. 16 nennt neben Telegram-Bot noch "Web-Interface (FastAPI+ngrok)" als Alternative und "WireGuard VPN" als sicherere Alternative sowie "Eigene App" als Langzeitziel - keiner dieser drei ist Teil von Phase 1.
Vor jedem weiteren Baustein (inkl. v0.6 Phase 2) gilt weiterhin: Handbook-Pruefung (Scope/DoD/Architektur/Sicherheitsmodell) + technischer Vorschlag zur Freigabe durch den Product Owner, bevor Code geschrieben wird (Muster aus ADR-013 bis ADR-018).

## Product-Owner-Hinweis fuer kuenftige Handbook-Version (v3.5, noch nicht umgesetzt)
**Hinweis (01.07.2026):** Die bisherigen Post-spezifischen Arbeitsmodule sollen kuenftig staerker verallgemeinert werden. Statt dauerhaft "Tabellen-Auswertung" als domaenenspezifischen Sonderfall zu fuehren, soll Jarvis perspektivisch eine **allgemeine Excel-/Report-Analyse** koennen:
- Excel-/Reportdateien lesen.
- Datenstrukturen erkennen (statt fester Spalten-Alias-Listen wie aktuell bei `calculate_kpi`, ADR-016).
- Auffaelligkeiten zusammenfassen (KI-gestuetzt, wie bereits bei `analyze_report`, ADR-015).
- KPI aus tabellarischen Daten berechnen (deterministisch, wie bereits bei `calculate_kpi`, ADR-016 - aber generisch statt "Kennzahl je Standort" hart zu erwarten).
- Domaenenspezifische Begriffe (z. B. "Auswertung", "Standort", "Ort") werden nur noch als **optionaler Kontext** verwendet, nicht als Voraussetzung.

**Status:** Reine Absichtserklaerung/Richtungsentscheidung fuer die naechste Handbook-Version (v3.5, analog zum v3.3->v3.4-Nachzug nach Abschluss einer Version, Kap. 2). **Keine Architekturentscheidung, keine ADR** - noch keine Umsetzung, keine Freigabe, kein technischer Vorschlag.
**Ausdruecklich NICHT betroffen:** Die bestehenden v0.5-Commands (`read_excel`, `analyze_report`, `calculate_kpi`) bleiben unveraendert. **Kein Refactoring waehrend v0.6.**
**Wann wieder aufgreifen:** Bei der naechsten geplanten Handbook-Aktualisierung (nach Abschluss von v0.6, vor Beginn der Version, die diese Generalisierung umsetzen soll) - dann mit vollem Handbook-Pruefungs-/technischer-Vorschlag-Prozess wie bei den bisherigen Bausteinen.

## Tests
Letzter Check am 2026-07-01: `pytest tests -v` mit zusaetzlichem `PYTHONPATH`.

### Test Status
`152 / 152` bestanden

### Known Failure
Keiner aktuell. `tests/test_integration.py::test_end_to_end_tool_execution` (vormals bekannter, Windows-spezifischer Fehlschlag wegen `os.startfile` vs. gemocktem POSIX-Pfad) lief in den letzten Durchlaeufen gruen durch. Falls der Fehlschlag erneut auftritt, siehe `docs/logbook.md` (Eintraege 2026-07-01) fuer die dokumentierte Ursache.

## Offene Aufgaben

### Technische TODOs (Definition of Done / Betrieb, kein neuer Scope)
- Manueller Live-Test aller Kernfunktionen mit echtem API-Key auf dem echten Windows-Rechner (Definition of Done, Kap. 28) - bisher nur automatisiert/gemockt getestet: `system_status`, `install_program`, `remember_fact`/`forget_fact`, `read_excel`, `analyze_report`, `calculate_kpi`. Insbesondere `install_program` real ausfuehren ist ein bewusster, expliziter Schritt (installiert wirklich Software) und sollte gezielt vom Product Owner freigegeben/begleitet werden.
- Telegram-Bot real mit einem echten Bot-Token/Chat testen (Smoke Test laut Definition of Done) - bisher nur mit gemocktem `python-telegram-bot` getestet, kein echter Long-Polling-Lauf.
- Piper-Sprachmodell herunterladen und `tts_enabled: true` fuer einen Live-TTS-Test setzen.
- Zwei bis drei Piper-Stimmen pruefen und danach `offline vs. Cloud-TTS` entscheiden.
- `.git_broken_5/` (Reste eines fruehen, abgebrochenen git-init-Versuchs) liegt noch im Arbeitsordner, ist per `.gitignore` von der Versionierung ausgeschlossen. Kann bei Gelegenheit manuell aufgeraeumt werden, wurde bewusst nicht geloescht (keine destruktive Aktion ohne Rueckfrage).

### Feature-TODOs (naechste Roadmap-Bausteine, NICHT jetzt umsetzen)
- Generalisierung "Tabellen-Auswertung" -> allgemeine Excel-/Report-Analyse - Product-Owner-Hinweis fuer Handbook v3.5 (siehe Abschnitt oben), NICHT waehrend v0.6 umsetzen, kein Refactoring der bestehenden v0.5-Commands.
- `v0.6 Phase 2`: Erweiterung des Telegram-Befehlsumfangs (z. B. Excel/Reports/KPI, evtl. Sicherheitsstufe-2-Aktionen mit einer echten `TelegramSpeech.listen()`-Implementierung statt fail-closed) - noch keine Priorisierung/Freigabe.
- Web-Interface (FastAPI+ngrok) und WireGuard VPN (Handbook Kap. 16) - als Alternativen genannt, nicht Teil von Phase 1, keine eigene Priorisierung.
- Eigene App (Handbook Kap. 16) - explizit als Langzeitziel markiert.
- Alias-Liste fuer Standort-/Ist-Wert-Spalten (ADR-016) erweitern, sobald sich an echten Reports zeigt, dass andere Spaltennamen gebraucht werden.
- Power BI - im Handbook selbst (Kap. 29 Backlog, v3.4) als optionale Unternehmensintegration/spaeterer Baustein dokumentiert.
- Eigene `AIEngine.summarize_report()`-Methode - nur pruefen, falls die Wiederverwendung von `answer()` bei `analyze_report` sich als inhaltlich unzureichend erweist (ADR-015).
- Excel Phase 2 (Schreiben, Formatieren, Power Query, Makros) - explizit nicht Teil von Phase 1 (ADR-013/ADR-014), keine Priorisierung dafuer.
- `.xls` (Legacy-Format) - von `openpyxl` nicht unterstuetzt, keine eigene Priorisierung bisher.
- Outlook-Integration - explizit aus v0.5 ausgeklammert (Handbook, Kap. 27), eigene, spaetere Priorisierung noetig.
- `Deinstallieren` (winget) - im Handbook (Kap. 17) genannt, aber nicht Teil der v0.4-Priorisierung (Kap. 27, siehe ADR-012); braucht eigene Priorisierung und vermutlich eigene Sicherheitsstufen-Bewertung.
- Festplatten-Ueberwachung/-Bereinigung - separater Handbook-Punkt (Kap. 17), nicht in v0.4 enthalten (siehe ADR-011).
- Temperatur-Monitoring - unter Windows von `psutil` nicht unterstuetzt (Plattform-Limitierung, kein Priorisierungsthema).

Im Code wurden keine `TODO`-/`FIXME`-Marker gefunden.

## Latest ADR
`ADR-018 - Telegram-Fernzugriff (v0.6 Phase 1) - eingeschraenkte Whitelist, separater Einstiegspunkt`

## Latest Architecture Change
`telegram_main.py` (neuer, vollstaendig additiver Einstiegspunkt) verdrahtet dieselbe Pipeline wie `main.py` mit Telegram statt Konsole als Kanal. Zwei unabhaengige Sicherheitsmechanismen (Intent-Whitelist + `requires_confirmation`-Check) leben ausschliesslich dort - keine Aenderung an `core/ai.py`, `core/planner.py`, `core/tool_manager.py`, `executor/executor.py`, `main.py` oder `commands/*.py` (per `git diff --stat` verifiziert leer). `TelegramSpeech` erfuellt die `SpeechEngine`-Schnittstelle fail-closed, damit `Executor` unveraendert wiederverwendet werden kann.

## Known Limitations
- Langzeitgedaechtnis funktioniert nur auf Zuruf; es gibt keine automatische Fakten-Extraktion.
- `listen()` (Konsole) bleibt Konsole; Mikrofon/Wake-Word ist weiterhin nicht umgesetzt.
- Kokoro TTS unterstuetzt aktuell kein Deutsch.
- Fehlt ein TTS-Modell oder Backend, faellt Jarvis auf reine Konsolenausgabe zurueck.
- Systemueberwachung liest keine Temperatur aus (`psutil` unterstuetzt das unter Windows nicht) und keine Festplattenbelegung (separater, noch nicht priorisierter Handbook-Punkt).
- `install_program` deckt kein "Deinstallieren" ab (bewusst nicht in v0.4-Scope, siehe ADR-012) und braucht `winget` (App Installer aus dem Microsoft Store) auf dem Zielsystem.
- `read_excel`/`analyze_report`/`calculate_kpi` lesen nur `.xlsx`/`.xlsm` (kein `.xls`), nur Werte (keine Formeln/Formatierung/Makros), pro Arbeitsblatt auf 500 Zeilen begrenzt.
- `analyze_report` liefert eine KI-generierte Analyse, die falsch liegen kann - deshalb Pflicht-Disclaimer in jeder Antwort (ADR-015).
- `calculate_kpi` erkennt Standort-/Ist-Wert-Spalten nur ueber eine feste Alias-Liste (ADR-016).
- `telegram_main.py` (Phase 1): nur vier Intents erreichbar, kein gleichzeitiger Betrieb mit der Konsole, kein automatischer Neustart bei Absturz des Long-Polling-Prozesses, `TelegramSpeech.listen()` ist bewusst nicht funktionsfaehig implementiert (fail-closed) - eine echte Bestaetigungsabfrage per Telegram existiert noch nicht (ADR-018).

## Git
Ein einzelner, ehrlicher Initial-Commit aus dem aktuellen Arbeitsstand (kein rekonstruierter Verlauf aus alten ZIP-Staenden), getaggt als `v0.4`. Danach je ein Commit fuer Handbook v3.3/ADR-013, Excel-Lesen (ADR-014), Tabellen-Auswertung (ADR-015), die Power-BI-Scope-Entscheidung, KPI (ADR-016) und die v0.5-Abschlusspruefung, getaggt als `v0.5`. Danach ein Commit fuer Handbook v3.4/ADR-017. Fruehere Versionen (v0.1-v0.3) existieren nur als Text in `docs/CHANGELOG.md`/`docs/logbook.md`, nicht als eigene Git-Commits/Tags - das im Handbook (Kap. 21) urspruenglich vorgesehene inkrementelle Nachziehen der Commit-Historie wurde bewusst nicht gemacht (keine kuenstliche Fake-Historie). Der Telegram-Baustein (dieser Stand) ist noch nicht committed. Kein neuer Tag - `v0.6` wird erst bei Abschluss aller vorgesehenen v0.6-Bausteine getaggt.

## Product Owner Rules
- Product Owner entscheidet Prioritaeten.
- KI darf Umsetzung vorschlagen, aber keine Roadmap aendern.
- Bei Konflikt gewinnt das Master-Handbook.
