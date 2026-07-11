"""
Zentrale Konfiguration für Jarvis.
Keine Magic Values im Code – alles Konfigurierbare gehört hierher.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"


def _resolve_repo_path(value: str | Path) -> Path:
    """Bindet relative Config-Pfade an das Repo statt ans Prozess-cwd."""
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


@dataclass
class Config:
    # API
    openai_api_key: str = ""
    model: str = "gpt-4o-mini"

    # Sprach-Eingabe (STT, ADR-038): Transkriptionsmodell fuer Telegram-
    # Sprachnachrichten. Nutzt denselben openai_api_key wie oben.
    transcription_model: str = "whisper-1"

    # Push-to-talk am PC (ADR-041): globaler Hotkey -> Mikrofon -> Whisper ->
    # gesprochene Antwort. Startet nur, wenn sounddevice/pynput/Mikrofon/
    # OpenAI-Key vorhanden sind; hier laesst er sich hart abschalten.
    ptt_enabled: bool = True

    # Wake-Word (ADR-044): "Hey Jarvis" per dauerhaft lauschendem Mikrofon,
    # lokal bewertet (openwakeword). Privacy-by-default AUS - bewusst per
    # Config einschalten.
    wake_word_enabled: bool = False
    # Gesprochene Wake-Bestaetigung (beim Start synthetisiert und gecacht).
    # Mehrere Varianten mit "|" trennen ("Ja, Sir?|Sir?|Ich höre.") - pro
    # Zuruf wird zufaellig gewaehlt (Lebendigkeit). Leer = Piepton.
    wake_acknowledgement: str = "Ja, Sir?"

    # News-Briefing (ADR-042): RSS-Feeds fuer "was gibt's Neues?". Read-only,
    # kein Key. Default: tagesschau; beliebig erweiterbar in config.json.
    news_feeds: list = field(
        default_factory=lambda: ["https://www.tagesschau.de/index~rss2.xml"]
    )

    # Wetter (ADR-043, Open-Meteo, keyless): Standard-Ort, wenn der Nutzer
    # keinen nennt ("wie wird das Wetter morgen?"). Leer = Rueckfrage.
    weather_default_location: str = ""

    # Command Center (ADR-046): Port des lokalen Dashboards (dashboard.py,
    # bindet ausschliesslich an 127.0.0.1).
    dashboard_port: int = 8765

    # Browser-Kanal / Jarvis-UI (ADR-047): lokale Runtime-API (Chat +
    # Event-Strom fuer den Orb). Neue Kontroll-Flaeche -> Default AUS,
    # bewusst einschalten (gleiches Prinzip wie wake_word_enabled).
    ui_enabled: bool = False
    ui_port: int = 8766
    # Fenster-Modus des UI-App-Fensters (jarvis_ui.pyw, PO-Wunsch 10.07.2026
    # "Vollbild, aber als Einstellung"): "normal" | "maximized" | "fullscreen".
    # Vollbild verlaesst man mit F11; in allen Modi bleibt es ein normales,
    # verschiebbares Browser-App-Fenster.
    ui_window: str = "normal"
    # Merk-Angebot (ADR-051): Jarvis bietet an, nebenbei erwaehnte dauerhafte
    # Fakten zu speichern (fragt IMMER, speichert nie automatisch). Neues
    # Verhalten -> Default AUS, bewusst einschalten (wie wake_word_enabled).
    memory_offers_enabled: bool = False
    # Impuls-Kreislauf (Endsystem-Kampagne, ADR-054): Jarvis legt proaktiv
    # stille Hinweis-Karten ab (Unwetter u. a.). Anders als das Merk-Angebot
    # standardmaessig AN - der PO hat das proaktive Endsystem ausdruecklich
    # beauftragt (11.07.2026). Ein Impuls handelt nie, er legt nur eine Karte.
    impulses_enabled: bool = True
    # Anzeigename fuer die UI-Begruessung ("Guten Morgen, ..."). Bewusst
    # Config statt Code (kein Personenname im Repo, Release-Hygiene 4.1);
    # leer -> neutrales "Sir".
    owner_name: str = ""

    # Multi-KI Provider-Auswahl (v0.8 Phase 1, ADR-029): "openai" | "claude".
    # Explizite Auswahl per Config, kein Auto-Routing. Claude nutzt einen
    # eigenen Key (ANTHROPIC_API_KEY, ausschliesslich ueber Env, nie in
    # config.json/Git) und ein eigenes Modell.
    ai_provider: str = "openai"
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5"

    # Provider-Router (v0.8 Phase 2, ADR-030): aufgabenabhaengige Auswahl,
    # deterministisch. Leer -> Rueckfall auf ai_provider (rueckwaertskompatibel:
    # ohne diese Felder verhaelt sich alles wie in Phase 1).
    planning_provider: str = ""   # get_plan() / TaskType.PLANNING
    answer_provider: str = ""     # answer()   / TaskType.GENERATION

    # Mail-Briefing (Nutzwert-Phase, ADR-031): Liste privater Postfächer für
    # „Was liegt an?". Nur nicht-geheime Felder hier (label/imap_host/
    # imap_port/username/password_env); das Passwort/App-Passwort steht
    # AUSSCHLIESSLICH in der genannten Umgebungsvariable (ADR-018), nie hier.
    mail_accounts: list = field(default_factory=list)

    # Agenten-Delegation (ADR-034, Umsetzungs-Scheibe 1): Repo-Allowlist fuer
    # die read-only Repo-Analyse. Config-getrieben wie mail_accounts, leerer
    # Default (fail-closed: ohne Eintrag ist kein Repo delegierbar). Jeder
    # Eintrag {"alias": "...", "path": "..."}; nicht gelistete/nicht
    # existierende Pfade werden abgelehnt. Kein Secret hier.
    agent_repos: list = field(default_factory=list)
    # Harter Wall-Clock-Timeout eines Agentenlaufs in Sekunden (Kill-Switch,
    # ADR-034 Guardrails) - bewusst getrennt vom kurzen LLM-`timeout` oben,
    # da eine Repo-Analyse Minuten dauern darf.
    agent_timeout: float = 300.0
    # Schreib-Kaefig (ADR-050): Repos, in denen ein Agent SCHREIBEN darf -
    # bewusst getrennt von agent_repos (lesen heisst nicht schreiben).
    # Fail-closed: leer = keine schreibende Delegation.
    agent_write_repos: list = field(default_factory=list)
    # Warnschwelle je Agentenlauf in USD - GEGENWERT laut CLI (der Agent
    # laeuft ueber das MAX-Abo, Grenzkosten 0; PO-Hinweis 2026-07-10).
    # Zweck: Ausreisser-Wecker fuer ungewoehnlich grosse Laeufe, die das
    # Session-Kontingent fressen. Kein Vorab-Deckel in der CLI verfuegbar.
    agent_cost_warn_usd: float = 2.0

    # Projektstart auf Zuruf (ADR-049): Wurzel, UNTER der start_project neue
    # Zielprojekt-Repos anlegt, und der Pfad des AI-Project-Framework-Repos
    # (READ-ONLY-Quelle fuer Herkunfts-Hash/charter_version/ADR-Template).
    # Beide leer = Faehigkeit aus (fail-closed).
    projects_root: str = ""
    framework_repo: str = ""

    # Sprache / Stimme
    voice: str = "default"
    volume: float = 0.8
    hotword: str = "jarvis"

    # TTS (v0.3) - deaktiviert per Default, da Modell separat
    # heruntergeladen werden muss (siehe README "Piper TTS einrichten").
    tts_enabled: bool = False
    tts_model_path: str = "voices/de_DE-thorsten-medium.onnx"

    # TTS-Backend-Auswahl (v0.3.6, siehe ADR-008): "piper" (Standard,
    # offline) | "openai" | "elevenlabs" | "kokoro". Piper bleibt der
    # Standard - nur wer aktiv umstellt, braucht die Felder darunter.
    tts_backend: str = "piper"

    # OpenAI-TTS (Cloud) - nutzt denselben openai_api_key wie oben.
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "onyx"
    openai_tts_speed: float = 1.0  # 0.25-4.0; PO nutzt 1.3 (config.json)
    # Stil-Anweisung fuer gpt-4o-mini-tts ("Stimme & Hirn" 2026-07-10) -
    # steuert Charakter/Betonung der Stimme. Leer = keine Anweisung
    # (noetig fuer tts-1/tts-1-hd, die keine instructions kennen).
    openai_tts_instructions: str = ""
    # TTS-Streaming (ADR-048, Latenz-Fahrplan Stufe 3): Wiedergabe beginnt
    # mit dem ersten PCM-Chunk statt nach der kompletten Synthese (gemessen
    # 2-5 s Wartezeit). Greift nur bei Backends mit stream_pcm (openai);
    # false = bewaehrter Datei-Weg als Kill-Switch.
    tts_streaming: bool = True

    # ElevenLabs-TTS (Cloud) - eigener API-Key noetig, siehe README.
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_multilingual_v2"

    # Kokoro-TTS (offline wie Piper, aber aktuell KEIN Deutsch -
    # siehe core/tts/kokoro_backend.py).
    kokoro_model_path: str = "voices/kokoro-v1.0.onnx"
    kokoro_voices_path: str = "voices/voices-v1.0.bin"
    kokoro_voice: str = "am_onyx"
    kokoro_lang: str = "en-us"

    # Pfade
    memory_dir: Path = BASE_DIR / "memory_data"
    log_dir: Path = BASE_DIR / "logs"

    # Gesprächsgedächtnis
    max_history_entries: int = 200

    # Chat-Antworten auf ein staerkeres OpenAI-Modell heben ("Stimme & Hirn"
    # 2026-07-10), waehrend der Planner beim schnellen `model` bleibt.
    # Leer = kein Override (alles wie bisher). Gilt nur fuer OpenAI.
    answer_model: str = ""
    # Eigenes Token-Budget fuer Chat-ANTWORTEN (Nutzungslauf-Befund
    # 2026-07-10: laengere Antworten brachen am globalen max_tokens=300
    # mitten im Satz ab). 0 = wie max_tokens; Planner-JSON bleibt bei
    # max_tokens (klein = schnell).
    answer_max_tokens: int = 700

    # AI-Aufruf (v0.2.1: keine Magic Values mehr in ai.py)
    temperature: float = 0.0
    timeout: float = 15.0
    max_tokens: int = 300

    # Debug
    debug: bool = False

    @classmethod
    def load(cls, path: Path = CONFIG_FILE) -> "Config":
        data: dict = {}
        if path.exists():
            # utf-8-sig: toleriert ein UTF-8-BOM (schreiben z. B. PowerShell/
            # Editoren gern) - ein BOM darf Jarvis nie am Start hindern
            # (Live-Befund 10.07.2026); ohne BOM identisch zu utf-8.
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

        # Env-Variablen überschreiben Datei (API-Keys gehören nicht in config.json)
        api_key = os.environ.get("OPENAI_API_KEY", data.get("openai_api_key", ""))
        anthropic_key = os.environ.get(
            "ANTHROPIC_API_KEY", data.get("anthropic_api_key", "")
        )
        elevenlabs_key = os.environ.get(
            "ELEVENLABS_API_KEY", data.get("elevenlabs_api_key", "")
        )

        cfg = cls(
            openai_api_key=api_key,
            model=data.get("model", cls.model),
            transcription_model=data.get("transcription_model", cls.transcription_model),
            ptt_enabled=data.get("ptt_enabled", cls.ptt_enabled),
            wake_word_enabled=data.get("wake_word_enabled", cls.wake_word_enabled),
            wake_acknowledgement=data.get("wake_acknowledgement", cls.wake_acknowledgement),
            news_feeds=data.get("news_feeds") or ["https://www.tagesschau.de/index~rss2.xml"],
            weather_default_location=data.get("weather_default_location", cls.weather_default_location),
            dashboard_port=int(data.get("dashboard_port", cls.dashboard_port)),
            ui_enabled=bool(data.get("ui_enabled", cls.ui_enabled)),
            ui_port=int(data.get("ui_port", cls.ui_port)),
            ui_window=str(data.get("ui_window", cls.ui_window)),
            memory_offers_enabled=bool(data.get("memory_offers_enabled", cls.memory_offers_enabled)),
            impulses_enabled=bool(data.get("impulses_enabled", cls.impulses_enabled)),
            owner_name=str(data.get("owner_name", cls.owner_name)),
            ai_provider=data.get("ai_provider", cls.ai_provider),
            anthropic_api_key=anthropic_key,
            claude_model=data.get("claude_model", cls.claude_model),
            planning_provider=data.get("planning_provider", cls.planning_provider),
            answer_provider=data.get("answer_provider", cls.answer_provider),
            mail_accounts=data.get("mail_accounts", []),
            agent_repos=data.get("agent_repos", []),
            agent_timeout=data.get("agent_timeout", cls.agent_timeout),
            agent_write_repos=data.get("agent_write_repos", []),
            agent_cost_warn_usd=float(data.get("agent_cost_warn_usd", cls.agent_cost_warn_usd)),
            projects_root=str(data.get("projects_root", cls.projects_root)),
            framework_repo=str(data.get("framework_repo", cls.framework_repo)),
            voice=data.get("voice", cls.voice),
            volume=data.get("volume", cls.volume),
            hotword=data.get("hotword", cls.hotword),
            tts_enabled=data.get("tts_enabled", cls.tts_enabled),
            tts_model_path=data.get("tts_model_path", cls.tts_model_path),
            tts_backend=data.get("tts_backend", cls.tts_backend),
            openai_tts_model=data.get("openai_tts_model", cls.openai_tts_model),
            openai_tts_voice=data.get("openai_tts_voice", cls.openai_tts_voice),
            openai_tts_speed=float(data.get("openai_tts_speed", cls.openai_tts_speed)),
            openai_tts_instructions=str(data.get("openai_tts_instructions", cls.openai_tts_instructions)),
            tts_streaming=bool(data.get("tts_streaming", cls.tts_streaming)),
            answer_model=str(data.get("answer_model", cls.answer_model)),
            answer_max_tokens=int(data.get("answer_max_tokens", cls.answer_max_tokens)),
            elevenlabs_api_key=elevenlabs_key,
            elevenlabs_voice_id=data.get("elevenlabs_voice_id", cls.elevenlabs_voice_id),
            elevenlabs_model=data.get("elevenlabs_model", cls.elevenlabs_model),
            kokoro_model_path=data.get("kokoro_model_path", cls.kokoro_model_path),
            kokoro_voices_path=data.get("kokoro_voices_path", cls.kokoro_voices_path),
            kokoro_voice=data.get("kokoro_voice", cls.kokoro_voice),
            kokoro_lang=data.get("kokoro_lang", cls.kokoro_lang),
            memory_dir=_resolve_repo_path(data.get("memory_dir", cls.memory_dir)),
            log_dir=_resolve_repo_path(data.get("log_dir", cls.log_dir)),
            max_history_entries=data.get("max_history_entries", cls.max_history_entries),
            temperature=data.get("temperature", cls.temperature),
            timeout=data.get("timeout", cls.timeout),
            max_tokens=data.get("max_tokens", cls.max_tokens),
            debug=data.get("debug", cls.debug),
        )
        cfg.memory_dir.mkdir(parents=True, exist_ok=True)
        cfg.log_dir.mkdir(parents=True, exist_ok=True)
        return cfg


def persist_config_value(key: str, value: object, path: Path | None = None) -> None:
    """Aktualisiert EINEN Schluessel in config.json und laesst alle anderen
    Werte und ihre Reihenfolge unberuehrt (liest die Datei, setzt den Wert,
    schreibt sie atomar zurueck). Bewusst schmal: aktuell nur fuer owner_name
    (ADR-057, "nenn mich X" -> Anzeigename). Kein Freibrief fuer beliebige
    Config-Mutation - der aufrufende Command bindet den Schluessel fest.

    Atomar (tmp + os.replace), damit ein Absturz mitten im Schreiben die
    Konfiguration nie zertruemmert - dasselbe Prinzip wie LongTermMemory.

    path=None loest CONFIG_FILE erst zur AUFRUFZEIT auf (nicht als Default-
    Argument beim Import gebunden), damit Tests core.config.CONFIG_FILE
    umlenken koennen, ohne den echten config.json zu beruehren."""
    if path is None:
        path = CONFIG_FILE
    data: dict = {}
    if path.exists():
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    data[key] = value
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
