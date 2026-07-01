# Jarvis v0.4 - Langzeitgedächtnis

Refactor + Gesprächsgedächtnis + Planner/Executor + echte
Chat-Antworten (v0.3), jetzt plus dauerhaftes Langzeitgedächtnis
(v0.4). Siehe docs/CHANGELOG.md für die volle Historie.

**Maßgebliches Prozess-/Architekturdokument:** `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_3.docx`.
Alle Entscheidungen in diesem Projekt (ADRs, Now/Next/Later-Priorisierung,
Definition of Done, Sicherheitsstufen) richten sich nach diesem Dokument -
"Immer nach Handbuch". `v3_2.docx` bleibt als Archiv erhalten (Grundlage für
v0.4). Ältere Handbook-Versionen liegen ggf. noch lose in Downloads
(nicht im Projekt), sind aber NICHT maßgeblich.

## AI / Agent Onboarding

Neue KI-Agenten müssen zuerst `docs/AI_START.md` lesen.
Der aktuelle Projektstand steht in `docs/PROJECT_STATE.md`.
Das Master-Handbook `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_3.docx`
bleibt die verbindliche Quelle.

## Struktur

```
jarvis/
├── core/
│   ├── config.py        # zentrale Config (API-Keys, Modell, Pfade, ...)
│   ├── models.py         # Plan, Result, Status, Message
│   ├── ai.py             # AI Layer - Intent-Erkennung (get_plan) + Chat-Antworten (answer)
│   ├── planner.py        # zerlegt Eingabe in 1..n Schritte
│   ├── tool_manager.py    # löst Intent -> Command auf
│   └── speech.py           # Speech-Schnittstelle (Konsole + optional Piper TTS)
├── commands/
│   ├── __init__.py         # Registry + minimaler Dispatch
│   ├── system.py             # open_program, shutdown_pc
│   ├── memory.py               # remember_fact, forget_fact
│   ├── monitor.py               # system_status (CPU/RAM, ADR-011)
│   ├── installer.py               # install_program (winget, ADR-012)
│   ├── excel.py                     # read_excel (openpyxl, ADR-014)
│   └── reports.py                     # analyze_report (ADR-015), calculate_kpi (ADR-016)
├── executor/
│   └── executor.py             # führt Schritte aus, Bestätigung, ✓/✗/?-Report
├── memory/
│   └── store.py                  # JsonMemoryStore (preferences/history/context)
├── memory_data/                     # preferences.json, history.json, context.json
├── logs/                               # YYYY-MM-DD.log
├── tests/                               # pytest, alles gemockt, kein echter API-Key nötig
├── docs/
│   ├── AI_START.md
│   ├── CHANGELOG.md
│   ├── PROJECT_STATE.md
│   ├── logbook.md
│   ├── handbook/
│   └── adr/
├── config.example.json
├── requirements.txt
├── CHANGELOG.md                        # Verweis auf docs/CHANGELOG.md
└── main.py                                 # verdrahtet die Pipeline
```

## Setup

```bash
pip install -r requirements.txt
cp config.example.json config.json
export OPENAI_API_KEY="sk-..."   # überschreibt config.json
python main.py
```

## Tests ausführen

```bash
pip install -r requirements.txt
PYTHONPATH=. pytest tests/ -v
```

Alle Tests laufen ohne echten API-Key (OpenAI-Client wird gemockt).

## Piper TTS einrichten (optional, nur Windows)

Ohne diesen Schritt läuft Jarvis normal weiter, nur ohne Sprachausgabe
(reine Konsole). Einmalig einzurichten:

```bash
pip install piper-tts
mkdir voices
```

Modell + Config-Datei herunterladen (ca. 60 MB, deutsche Stimme
"Thorsten", mittlere Qualität) von Hugging Face und in `voices/`
ablegen:

- https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx
- https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json

Beide Dateien nach `voices/de_DE-thorsten-medium.onnx` bzw.
`voices/de_DE-thorsten-medium.onnx.json` speichern (Dateiname muss
exakt übereinstimmen - Piper erwartet die `.json`-Config direkt neben
dem Modell). Danach in `config.json`:

```json
"tts_enabled": true
```

Andere Stimmen: komplette Liste unter
https://huggingface.co/rhasspy/piper-voices/tree/main/de/de_DE
(z. B. `de_DE-kerstin-low` ist kleiner/schneller, aber weniger
natürlich als `thorsten-medium`).

## TTS-Backend wechseln (ADR-008)

Piper ist der Standard (offline, kostenlos). Wer die Stimme näher an
Film-Jarvis bringen will, kann in `config.json` `tts_backend`
umstellen - core/speech.py muss dafür NICHT angefasst werden:

```json
"tts_backend": "openai"
```

Verfügbare Werte und was sie zusätzlich brauchen:

- `"piper"` (Standard) - siehe oben, komplett offline.
- `"openai"` - nutzt denselben `openai_api_key` wie der Chat, kein
  zusätzliches Setup. Felder `openai_tts_model` (Standard
  `gpt-4o-mini-tts`) und `openai_tts_voice` (Standard `onyx`) in
  config.json überschreibbar. Kostet pro Anfrage, braucht Internet.
- `"elevenlabs"` - `pip install elevenlabs`, eigenen API-Key als
  Umgebungsvariable `ELEVENLABS_API_KEY` setzen (nicht in
  config.json!), dazu `elevenlabs_voice_id` (aus der ElevenLabs-
  Stimmenbibliothek) in config.json eintragen. Kostet pro Anfrage,
  braucht Internet.
- `"kokoro"` - `pip install kokoro-onnx numpy`, Modelldateien
  `kokoro-v1.0.onnx` + `voices-v1.0.bin` von
  https://github.com/thewh1teagle/kokoro-onnx nach `voices/` legen.
  **Achtung:** Kokoro v1.0 spricht aktuell KEIN Deutsch (nur
  Englisch/Spanisch/Französisch/Hindi/Italienisch/brasil.
  Portugiesisch/Japanisch/Chinesisch) - für Wolfgangs deutsche
  Gespräche aktuell nicht geeignet, siehe core/tts/kokoro_backend.py.

Schlägt ein Backend fehl (Paket fehlt, Key fehlt, Modell fehlt),
fällt Jarvis automatisch auf reine Konsolenausgabe zurück statt zu
crashen - genau wie bisher bei Piper ohne Modell.

## Langzeitgedächtnis (v0.4, ADR-009)

Getrennt vom normalen Gesprächsverlauf (der nur die letzten 20
Nachrichten kennt): Jarvis merkt sich Dinge dauerhaft, aber NUR wenn
man es ausdrücklich sagt - keine automatische Erkennung.

```
Du: Merk dir, dass ich montags immer Reports mache
Jarvis: Gemerkt: ich mache montags Reports

Du: Vergiss, dass ich montags Reports mache
Jarvis: Vergessen: montags Reports
```

Gemerkte Fakten fließen automatisch in normale Chat-Antworten ein
(z. B. auf "was weißt du über mich?"). Gespeichert wird in
`memory_data/long_term.json`, kategorisiert als `projekt`,
`gewohnheit`, `praeferenz` oder `allgemein`.

## PC-Grundsteuerung: Systemüberwachung (v0.4, ADR-011)

Erster Baustein von "PC-Grundsteuerung" (Handbook Kap. 27) neben dem
bereits vorhandenen `open_program`: Jarvis liest auf Zuruf CPU- und
RAM-Auslastung aus (`psutil`, Sicherheitsstufe 0 - reine Leseaktion,
keine Bestätigung nötig).

```
Du: Wie ist die aktuelle Auslastung?
Jarvis: CPU-Auslastung: 12 %. RAM: 43 % belegt (6.9 GB von 16.0 GB).
```

Temperatur wird bewusst nicht ausgelesen - `psutil` unterstützt das
unter Windows nicht (siehe ADR-011). Festplatten-Überwachung/-
Bereinigung ist ein separater, noch nicht priorisierter Punkt.

## PC-Grundsteuerung: Programme installieren (v0.4, ADR-012)

Zweiter und letzter für v0.4 vorgesehener Baustein von
"PC-Grundsteuerung" (Handbook Kap. 27): Jarvis installiert Programme
über `winget` (Sicherheitsstufe 2 - Systemänderung, braucht
Bestätigung, aber anders als `shutdown_pc` KEINE exakte
Bestätigungsphrase).

```
Du: Installier VLC
Jarvis: Ich würde jetzt ausführen: 'Installier VLC'. Bestätigen?
Du: Ja
Jarvis: vlc wurde installiert.
```

Bekannte Namen (`vlc`, `7zip`, `firefox`, `chrome`, `notepad++`)
werden auf exakte winget-Package-IDs abgebildet
(`commands/installer.py::KNOWN_PACKAGES`), unbekannte Programme gehen
als Freitext-Suchbegriff an winget. Voraussetzung: `winget` muss
installiert sein (Windows 10/11 meist vorhanden über den "App
Installer" aus dem Microsoft Store) - fehlt es, meldet Jarvis das
klar statt stillschweigend zu scheitern.

## Excel-Lesen (v0.5 Phase 1, ADR-014)

Erster Arbeitsmodule-Baustein (Handbook Kap. 13/27, v3.3): Jarvis liest
`.xlsx`/`.xlsm`-Dateien über `openpyxl` (Sicherheitsstufe 0 - reine
Leseaktion, keine Bestätigung nötig).

```
Du: Lies C:\Reports\beispiel.xlsx
Jarvis: beispiel.xlsx: 2 Arbeitsblatt(e) - Tabelle1 (120 Zeile(n) x 5 Spalte(n)), Tabelle2 (40 Zeile(n) x 3 Spalte(n))
```

Optional ein bestimmtes Arbeitsblatt angeben (`parameters.sheet`), sonst
werden alle Blätter gelesen. Gelesene Zelldaten stehen intern in
`Result.data["sheets"]` bereit (pro Blatt auf 500 Zeilen begrenzt) -
für spätere Bausteine wie Tabellen-Auswertung, die darauf aufbauen.

**Bewusst nicht enthalten (Phase 1):** Schreiben, Formatieren, Power
Query, Makros, `.xls` (Legacy-Format), eine KI-Zusammenfassung im
Command selbst. Siehe ADR-013/ADR-014.

## Tabellen-Auswertung: Datenauswertung (v0.5, ADR-015)

Zweiter v0.5-Baustein: Jarvis liest einen Datentabelle
(`.xlsx`/`.xlsm`, über dieselbe Lesefunktion wie `read_excel`) und
lässt die KI die Daten analysieren (Sicherheitsstufe 0 - reines Lesen
+ Analyse, keine Bestätigung nötig).

```
Du: Analysiere den Datentabelle C:\Reports\beispiel.xlsx
Jarvis: Standort Musterstadt liegt mit einer Fehlerquote von 15 % deutlich
über dem Durchschnitt der übrigen Standorte ...

Analyse auf Basis der gelieferten Daten. Bitte vor Entscheidungen prüfen.
```

`analyze_report` ist der erste Command, der direkt die KI
aufruft (`AIEngine.answer()`, per `configure()` injiziert wie beim
Langzeitgedächtnis, ADR-009) - der Executor bleibt dafür unverändert.
Jede Analyse endet mit einem Pflicht-Hinweis: Jarvis behauptet keine
geschäftskritische Wahrheit, sondern liefert einen Assistenzhinweis,
der vor Entscheidungen geprüft werden sollte.

## KPI: Kennzahl (v0.5, ADR-016)

Dritter und aktuell letzter aktiver v0.5-Baustein: Jarvis berechnet die
Kennzahl je Standort - **deterministisch in Python**, die
KI wird nur zur Interpretation der bereits berechneten Zahlen genutzt
(Sicherheitsstufe 0).

```
Du: Berechne die Kennzahl für C:\Reports\beispiel.xlsx, Ziel 95%
Jarvis: Musterstadt liegt mit 94,3 % knapp unter dem Zielwert von 95 % ...

Analyse auf Basis der gelieferten Daten. Bitte vor Entscheidungen prüfen.
```

Die Kopfzeile der Tabelle wird automatisch erkannt (case-insensitive,
ohne Leerzeichen): Standort-Spalte über `Standort`/`Ort`/`Ort`/
`Standort`, Ist-Wert-Spalte über `Ist`/`Istwert`/`Wert`/`Quote`/
`Kennzahl`/`Kennzahl`. Wird keine oder werden
mehrere passende Spalten gefunden, fragt Jarvis nach statt zu raten.
`parameters.zielwert` ist Pflicht (ohne Zielwert: Rückfrage).

Ergebnis (`Result.data["kpi"]`) enthält die berechnete Tabelle selbst
(Ist, Zielwert, Abweichung, Status je Standort) - nachprüfbar
unabhängig vom KI-Text.

**Power BI ist bewusst NICHT enthalten** - per Product-Owner-
Entscheidung aus dem aktiven v0.5-Scope genommen (liegt auf dem
Firmenrechner/im Firmenumfeld), siehe `docs/PROJECT_STATE.md`.

## Pipeline

Eingabe (Konsole) -> Planner zerlegt in 1..n Schritte -> pro Schritt:
Tool Manager löst Intent -> Command auf -> Executor führt aus (mit
Bestätigung bei kritischen Aktionen) oder holt bei chat-Intent eine
echte Antwort über `AIEngine.answer()` -> Report mit ✓/✗/? pro
Schritt -> Antwort ausgeben -> Memory speichern (History-Limit greift
automatisch).

## Neuen Command hinzufügen

1. Klasse mit `name`, `requires_confirmation` und
   `execute(plan) -> Result` in einem Modul unter `commands/`
   (z. B. `commands/media.py`, erst anlegen wenn wirklich ein
   Media-Befehl existiert).
2. Instanz in die `COMMANDS`-Liste des Moduls eintragen.
3. Modul in `commands/__init__.py::_register_all()` ergänzen.

Kein Anfassen von `main.py`, `planner.py`, `tool_manager.py`,
`executor.py` oder anderen Commands nötig.

## Bewusst NICHT in v0.3

- Mikrofon/Spracheingabe (Wake-Word) - `listen()` bleibt Konsole,
  eigenes Feature unter Kap. 27 "Next"
- Echte Multi-Step-Planung mit Abhängigkeiten zwischen Schritten
  (Planner trennt nur naiv an Konnektoren, siehe ADR-004)
- Async / Nebenläufigkeit ("Jarvis, stopp" während einer Aktion)
- Vektor-Memory / echtes Langzeitgedächtnis
- Pydantic-Validierung des Plan-Schemas

Diese Punkte sind für v0.4+ vorgesehen (siehe Handbook Kap. 27).
