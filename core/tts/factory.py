"""
Waehlt anhand von Config.tts_backend die passende TTSBackend-
Implementierung - siehe ADR-008.

Schlaegt die Konstruktion aus irgendeinem Grund fehl (Paket nicht
installiert, Modell-/Stimmdatei fehlt, API-Key fehlt, unbekannter
Backend-Name), liefert create_backend() None statt eine Exception zu
werfen. core/speech.py faellt dann - wie bisher bei reinem Piper -
automatisch auf reine Konsolenausgabe zurueck: Jarvis bleibt
benutzbar, auch wenn die Sprachausgabe gerade nicht funktioniert.
"""
from __future__ import annotations

import logging
from typing import Optional

from core.config import Config
from core.tts.base import TTSBackend

logger = logging.getLogger("jarvis.tts.factory")


def create_backend(config: Config) -> Optional[TTSBackend]:
    backend_name = (config.tts_backend or "piper").strip().lower()

    try:
        if backend_name == "piper":
            from core.tts.piper_backend import PiperBackend

            return PiperBackend(config.tts_model_path)

        if backend_name == "openai":
            from core.tts.openai_backend import OpenAITTSBackend

            return OpenAITTSBackend(
                api_key=config.openai_api_key,
                model=config.openai_tts_model,
                voice=config.openai_tts_voice,
                timeout=config.timeout,
                speed=config.openai_tts_speed,
            )

        if backend_name == "elevenlabs":
            from core.tts.elevenlabs_backend import ElevenLabsBackend

            return ElevenLabsBackend(
                api_key=config.elevenlabs_api_key,
                voice_id=config.elevenlabs_voice_id,
                model_id=config.elevenlabs_model,
            )

        if backend_name == "kokoro":
            from core.tts.kokoro_backend import KokoroBackend

            return KokoroBackend(
                model_path=config.kokoro_model_path,
                voices_path=config.kokoro_voices_path,
                voice=config.kokoro_voice,
                lang=config.kokoro_lang,
            )

        logger.warning(
            "Unbekanntes TTS-Backend '%s' - Sprachausgabe bleibt aus.", backend_name
        )
        return None

    except Exception as e:
        logger.warning(
            "TTS-Backend '%s' konnte nicht geladen werden (%s) - Sprachausgabe "
            "bleibt aus, Konsolenausgabe funktioniert weiter.",
            backend_name,
            e,
        )
        return None
