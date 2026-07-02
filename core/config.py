"""
Zentrale Konfiguration für Jarvis.
Keine Magic Values im Code – alles Konfigurierbare gehört hierher.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"


@dataclass
class Config:
    # API
    openai_api_key: str = ""
    model: str = "gpt-4o-mini"

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
            with open(path, "r", encoding="utf-8") as f:
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
            ai_provider=data.get("ai_provider", cls.ai_provider),
            anthropic_api_key=anthropic_key,
            claude_model=data.get("claude_model", cls.claude_model),
            planning_provider=data.get("planning_provider", cls.planning_provider),
            answer_provider=data.get("answer_provider", cls.answer_provider),
            voice=data.get("voice", cls.voice),
            volume=data.get("volume", cls.volume),
            hotword=data.get("hotword", cls.hotword),
            tts_enabled=data.get("tts_enabled", cls.tts_enabled),
            tts_model_path=data.get("tts_model_path", cls.tts_model_path),
            tts_backend=data.get("tts_backend", cls.tts_backend),
            openai_tts_model=data.get("openai_tts_model", cls.openai_tts_model),
            openai_tts_voice=data.get("openai_tts_voice", cls.openai_tts_voice),
            elevenlabs_api_key=elevenlabs_key,
            elevenlabs_voice_id=data.get("elevenlabs_voice_id", cls.elevenlabs_voice_id),
            elevenlabs_model=data.get("elevenlabs_model", cls.elevenlabs_model),
            kokoro_model_path=data.get("kokoro_model_path", cls.kokoro_model_path),
            kokoro_voices_path=data.get("kokoro_voices_path", cls.kokoro_voices_path),
            kokoro_voice=data.get("kokoro_voice", cls.kokoro_voice),
            kokoro_lang=data.get("kokoro_lang", cls.kokoro_lang),
            memory_dir=Path(data.get("memory_dir", cls.memory_dir)),
            log_dir=Path(data.get("log_dir", cls.log_dir)),
            max_history_entries=data.get("max_history_entries", cls.max_history_entries),
            temperature=data.get("temperature", cls.temperature),
            timeout=data.get("timeout", cls.timeout),
            max_tokens=data.get("max_tokens", cls.max_tokens),
            debug=data.get("debug", cls.debug),
        )
        cfg.memory_dir.mkdir(parents=True, exist_ok=True)
        cfg.log_dir.mkdir(parents=True, exist_ok=True)
        return cfg
