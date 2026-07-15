# Installation & Betrieb

## Schnellstart (Windows)

```powershell
git clone <repo-url> jarvis && cd jarvis
powershell -ExecutionPolicy Bypass -File setup.ps1   # venv + Pakete (gepinnt) + config
setx OPENAI_API_KEY "sk-..."                         # Key NUR als Env-Variable
.venv\Scripts\pythonw.exe jarvis_ui.pyw              # Runtime + UI-Fenster
```

Ohne Key startet alles außer LLM/Transkription; Telegram, Sprachausgabe und
Wake-Word sind optionale Zusatzschritte (unten).

## Setup im Detail

```bash
pip install -r requirements.txt      # nur die Kern-Deps (Konsole, minimal)
cp config.example.json config.json
export OPENAI_API_KEY="sk-..."       # überschreibt config.json
python main.py
```

Für den **vollständigen Laufzeit-Betrieb** (Telegram-Runtime, Word-Export,
Claude-Provider, TTS): `pip install -r requirements-runtime.txt -c requirements.lock`
— installiert die real genutzten Pakete, **gepinnt auf die erprobten
Versionen** (`requirements.lock` als Constraints; `setup.ps1` macht genau das).
Entwicklungsumgebung (Suite/Gate): `pip install -r requirements-dev.txt -c requirements.lock`.

## KI-Provider wählen: OpenAI oder Claude (ADR-029/030)

Gesteuert über `ai_provider` in `config.json`:

- `"openai"` (Standard): nutzt `openai_api_key` (aus `OPENAI_API_KEY`) und
  `model` (Standard `gpt-4o-mini`).
- `"claude"`: nutzt Anthropic mit `claude_model` (Standard `claude-sonnet-5`).

Für Claude zusätzlich:

```bash
pip install anthropic
export ANTHROPIC_API_KEY="sk-ant-..."   # nur per Env, nie in config.json/Git
```

```json
{ "ai_provider": "claude", "claude_model": "claude-sonnet-5" }
```

Reine OpenAI-Setups brauchen weder das Paket `anthropic` noch den Key (lazy
Import). Fehlt bei `ai_provider="claude"` Paket oder Key, bricht Jarvis mit
klarer Fehlermeldung ab. Es gibt **kein** Auto-Routing zur Laufzeit — die
Auswahl ist bewusst rein konfigurativ; zusätzlich lassen sich Planung und
Antwort-Formulierung getrennt besetzen (`planning_provider`/`answer_provider`,
ADR-030). Für den Autostart gilt: Keys dauerhaft per `setx` setzen (unten).

## Telegram einrichten

```bash
pip install python-telegram-bot
export JARVIS_TELEGRAM_BOT_TOKEN="..."           # vom @BotFather
export JARVIS_TELEGRAM_ALLOWED_CHAT_ID="..."     # deine eigene Telegram-Chat-ID
python jarvis_runtime.py                          # Runtime-Kanal (empfohlen)
```

Beide Variablen sind Pflicht (nie in `config.json`/Git); Nachrichten anderer
Chat-IDs werden ignoriert. **Dauerhaft** (und zwingend für den Autostart) als
Benutzer-Umgebungsvariablen setzen:

```powershell
setx JARVIS_TELEGRAM_BOT_TOKEN "..."
setx JARVIS_TELEGRAM_ALLOWED_CHAT_ID "..."
```

`setx` wirkt erst in **neu geöffneten** Terminals/Prozessen. Der beim
Windows-Login per `pythonw.exe` gestartete Autostart-Prozess sieht **nur**
per `setx` gesetzte Variablen — Terminal-`$env:`/`export` reicht dort nicht
(gilt genauso für `OPENAI_API_KEY`). Hinweis: `telegram_main.py` (älterer
Standalone-Bot) und die Runtime dürfen **nicht gleichzeitig** mit demselben
Bot-Token laufen (Telegram erlaubt nur eine Long-Polling-Verbindung).

## Sprachausgabe: Piper TTS einrichten (optional, nur Windows)

Ohne diesen Schritt läuft Jarvis normal, nur ohne Sprachausgabe. Einmalig:

```bash
pip install piper-tts
mkdir voices
```

Modell + Config (ca. 60 MB, deutsche Stimme „Thorsten", mittlere Qualität)
von Hugging Face nach `voices/` legen:

- https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx
- https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json

Dateinamen exakt beibehalten (Piper erwartet die `.json` direkt neben dem
Modell). Danach in `config.json`: `"tts_enabled": true`. Andere Stimmen:
https://huggingface.co/rhasspy/piper-voices/tree/main/de/de_DE

## TTS-Backend wechseln (ADR-008)

Piper ist der Standard (offline, kostenlos). In `config.json` umstellbar —
`core/speech.py` muss dafür nicht angefasst werden:

- `"piper"` (Standard) — komplett offline.
- `"openai"` — derselbe `openai_api_key`, kein Zusatz-Setup; Felder
  `openai_tts_model` (Standard `gpt-4o-mini-tts`) und `openai_tts_voice`
  (Standard `onyx`). Kostet pro Anfrage, braucht Internet.
- `"elevenlabs"` — `pip install elevenlabs`, Key als Env-Variable
  `ELEVENLABS_API_KEY` (nie in config.json), `elevenlabs_voice_id` in
  config.json. Im Free-Tarif funktionieren nur aktuelle Default-Stimmen
  per API; Kontingent ~10 000 Zeichen/Monat.
- `"kokoro"` — `pip install kokoro-onnx numpy` + Modelldateien nach `voices/`.
  **Achtung:** spricht aktuell KEIN Deutsch.

Schlägt ein Backend fehl (Paket/Key/Modell fehlt), fällt Jarvis auf reine
Konsolenausgabe zurück statt zu crashen.

## Tests ausführen

```bash
pip install -r requirements-dev.txt -c requirements.lock
.\.venv\Scripts\python.exe -m pytest -q
```

Alle Tests laufen ohne echten API-Key (SDK-Clients gemockt; `anthropic` wird
über `sys.modules` simuliert). `conftest.py` wählt je Lauf einen eindeutigen
Basetemp — `tmp_path` scheitert damit auch in Sandbox-Umgebungen nicht.

## Git-Hooks aktivieren

```bash
git config core.hooksPath .githooks
```

Danach laufen vor jedem Commit automatisch das Konsistenz-Gate und die
Vollsuite. In Sandbox-Umgebungen kann das Temp-Verzeichnis per
`JARVIS_PYTEST_BASETEMP` umgelenkt werden; `--no-verify` bleibt tabu.

## Autostart: Jarvis-Eigenstart (ADR-028)

`enable_jarvis_autostart`/`disable_jarvis_autostart` (Sicherheitsstufe 2)
registrieren/entfernen `jarvis_runtime.py` als Windows-Autostart-Eintrag —
**nur lokal** auslösbar, remote gesperrt. Details:

- Fester HKCU-Run-Key-Eintrag `"Jarvis"`; Ziel ist `pythonw.exe` (kein
  Konsolenfenster — ein versehentlich geschlossenes Fenster würde sonst die
  Runtime samt Telegram-Kanal beenden), Fallback `sys.executable`.
- Idempotent: erneutes Ausführen aktualisiert den Eintrag (z. B. nach einem
  Projekt-Umzug).
- Ohne Konsole startet die Runtime keinen Konsolen-Kanal und loggt nur in die
  Datei; der Prozess lebt über den Worker-Thread.
- Der Autostart-Prozess sieht **nur** per `setx` gesetzte Env-Variablen
  (Telegram-Token, `OPENAI_API_KEY` — siehe oben).

## Runtime starten (Kanal-Übersicht)

- `pythonw jarvis_ui.pyw` — bequemster Weg: Runtime + UI-Fenster
  (Browser-App-Modus, ohne Tabs/Adressleiste).
- `python jarvis_runtime.py` — Runtime pur (Telegram-Kanal startet
  automatisch, wenn die Env-Variablen gesetzt sind; Browser-API per
  `"ui_enabled": true`).
- `python dashboard.py` — nur das UI/Command-Center (read-only, wenn die
  Runtime nicht läuft).
- `python main.py` — klassische Konsole; `python telegram_main.py` — älterer
  Standalone-Bot (eng begrenzte Whitelist, siehe SICHERHEIT.md).
