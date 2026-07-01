"""OpenAI-TTS-Backend (Cloud) - siehe ADR-008.

Nutzt denselben API-Key wie die Chat-/Intent-Erkennung (core/ai.py),
also KEIN separater Key nötig. Erfordert Internetzugang und
verursacht laufende Kosten pro Zeichen - deshalb bewusst nicht der
Standard (Config.tts_backend bleibt "piper", solange nicht explizit
umgestellt wird). Siehe platform.openai.com/docs/guides/text-to-speech.
"""
from __future__ import annotations

import logging

from openai import OpenAI

logger = logging.getLogger("jarvis.tts.openai")


class OpenAITTSBackend:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini-tts",
        voice: str = "onyx",
        timeout: float = 15.0,
    ):
        if not api_key:
            raise RuntimeError("TTS-Backend 'openai' braucht einen OPENAI_API_KEY.")
        self.client = OpenAI(api_key=api_key, timeout=timeout)
        self.model = model
        self.voice = voice

    def synthesize_to_file(self, text: str, output_path: str) -> None:
        response = self.client.audio.speech.create(
            model=self.model,
            voice=self.voice,
            input=text,
            response_format="wav",
        )
        response.stream_to_file(output_path)
