# Historie — wie Jarvis gewachsen ist

Jarvis ist **dokumentationsgetrieben in kleinen, testgesicherten Scheiben**
entstanden; jede Architektur-Entscheidung liegt als ADR unter `docs/adr/`
(chronologisch — die ADR-Reihe IST die Detailhistorie). Diese Datei hält nur
die grobe Versionslinie fest.

## Versionslinie

- **v0.1–v0.3** — Konsolen-Grundgerüst: Pipeline (Planner → Tool-Manager →
  Executor), Sicherheitsstufen mit Bestätigung, erste Commands, TTS-Grundlage.
  Existieren nur als Text-Historie, nicht als Tags.
- **v0.4** — Langzeitgedächtnis (ADR-009), PC-Grundsteuerung: Systemüberwachung
  (ADR-011) und Programme installieren (ADR-012).
- **v0.5** — Arbeitsmodule: Excel-Lesen (ADR-014).
- **v0.6** — Telegram-Fernzugriff (ADR-018/019).
- **v0.7** — PC-Admin: PC-Analyse, Ereignisprotokoll, Autostart-Verwaltung,
  Temp-Bereinigung (ADR-020–023); danach der Infrastruktur-/Runtime-Baustein
  (ADR-024–028: Runtime, Kanäle, Single-Instance, Eigenstart).
- **v0.8 „Multi-KI"** — Provider-Abstraktion + deterministischer
  Provider-Router (ADR-029/030). Bewusst nie getaggt — in v1.0 aufgegangen.
- **v1.0 „Alltagsassistent"** (getaggt 10.07.2026) — Einträge/Erinnerungen
  end-to-end inkl. Scheduler-Push, alle drei Sprach-Zugänge (Telegram-Voice,
  Push-to-talk, Wake-Word), News/Wetter, Auto-Redaction; freigegeben nach
  einem dokumentierten realen Nutzungslauf ohne kritischen Befund.
- **v1.1-dev** (aktuell) — der LLM-Reasoning-Kern führt einen wachsenden Teil
  der Intents (Strangler-Migration, ADR-060/064/073), der Agenten-Arm baut
  eigene Projekte im Käfig (ADR-050/056/059/069/071), Kalender lesen+schreiben
  (ADR-062), Antwort-Composer (ADR-065), Bestätigungs-Diät nach dem Prinzip
  „Undo statt Rückfrage" (ADR-068). Nächster Meilenstein: der Auftrags-Loop
  (ADR-072) — Jarvis führt einen begrenzten Auftrag selbstständig bis zum
  überprüften Ergebnis.

## Zeitkapsel: „Bewusst NICHT in v0.3"

Als Beispiel dafür, wie bewusste Nicht-Ziele später zu gebauten Fähigkeiten
wurden (oder bewusst Nicht-Ziele blieben):

- Mikrofon/Spracheingabe (Wake-Word) — *inzwischen gebaut* (ADR-041/044).
- Echte Multi-Step-Planung — *inzwischen gebaut* (LLM-Kern wählt mehrere
  Werkzeuge, ADR-064).
- Async/Nebenläufigkeit — *inzwischen gebaut* (Hintergrund-Worker, ADR-035).
- Vektor-Memory — *teilweise*: semantischer Abruf + Dedupe existieren; die
  flache Faktenliste ist geblieben, bis sie wehtut.
- Pydantic-Validierung des Plan-Schemas — *bewusst weiter nicht* (stdlib-Kurs).
