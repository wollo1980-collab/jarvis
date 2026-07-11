"""Piper-Backend (Standard, komplett offline) - siehe ADR-005/ADR-008."""
from __future__ import annotations

import logging
import wave
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger("jarvis.tts.piper")

try:
    from piper import PiperVoice
except ImportError:  # piper-tts nicht installiert - siehe README "TTS einrichten"
    PiperVoice = None


class PiperBackend:
    name = "piper"

    def __init__(self, model_path: Optional[Union[str, Path]]):
        if PiperVoice is None:
            raise RuntimeError(
                "'piper-tts' ist nicht installiert (pip install piper-tts). "
                "Siehe README.md, Abschnitt 'Piper TTS einrichten'."
            )
        if not model_path or not Path(model_path).exists():
            raise RuntimeError(f"Piper-Sprachmodell nicht gefunden unter '{model_path}'.")

        self.voice = PiperVoice.load(str(model_path))

    def synthesize_to_file(self, text: str, output_path: str) -> None:
        with wave.open(output_path, "wb") as wav_file:
            self.voice.synthesize_wav(text, wav_file)
