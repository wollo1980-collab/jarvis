"""
core.tts: Abstraktion über verschiedene Sprachausgabe-Engines
(lokal/offline wie Piper und Kokoro, oder Cloud wie OpenAI und
ElevenLabs) - siehe ADR-008.

core/speech.py kennt nur das TTSBackend-Protokoll und
core.tts.factory.create_backend(); welcher Anbieter tatsächlich
läuft, entscheidet sich allein über Config.tts_backend.
"""
from __future__ import annotations

from core.tts.base import TTSBackend
from core.tts.factory import create_backend

__all__ = ["TTSBackend", "create_backend"]
