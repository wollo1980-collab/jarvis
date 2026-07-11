"""Kokoro-Backend (offline wie Piper) - siehe ADR-008.

WICHTIG (Stand 01.07.2026): Kokoro v1.0 unterstuetzt aktuell KEIN
Deutsch - nur amerikanisches/britisches Englisch, Spanisch,
Franzoesisch, Hindi, Italienisch, brasilianisches Portugiesisch,
Japanisch und Chinesisch (siehe
huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md). Fuer
deutsche Gespraeche ist dieses Backend deshalb aktuell
NICHT geeignet - es existiert hier fuer den Fall, dass Kokoro
Deutsch nachliefert, oder falls gezielt eine englische Sprachausgabe
gewuenscht ist. Siehe Logbook-Eintrag 01.07.2026.

Erfordert zusaetzlich: pip install kokoro-onnx numpy, sowie die
Modell-/Stimmdateien kokoro-v1.0.onnx und voices-v1.0.bin (siehe
github.com/thewh1teagle/kokoro-onnx).
"""
from __future__ import annotations

import logging
import wave

logger = logging.getLogger("jarvis.tts.kokoro")

try:
    from kokoro_onnx import Kokoro
except ImportError:  # kokoro-onnx nicht installiert - optionale Abhaengigkeit
    Kokoro = None

try:
    import numpy as np
except ImportError:
    np = None

_SAMPLE_WIDTH = 2  # 16-bit PCM


class KokoroBackend:
    name = "kokoro"

    def __init__(
        self,
        model_path: str,
        voices_path: str,
        voice: str = "am_onyx",
        lang: str = "en-us",
    ):
        if Kokoro is None or np is None:
            raise RuntimeError(
                "'kokoro-onnx' (und numpy) sind nicht installiert "
                "(pip install kokoro-onnx numpy)."
            )
        from pathlib import Path

        if not Path(model_path).exists() or not Path(voices_path).exists():
            raise RuntimeError(
                f"Kokoro-Modelldateien nicht gefunden ('{model_path}', '{voices_path}')."
            )

        self.kokoro = Kokoro(model_path, voices_path)
        self.voice = voice
        self.lang = lang

    def synthesize_to_file(self, text: str, output_path: str) -> None:
        samples, sample_rate = self.kokoro.create(
            text, voice=self.voice, speed=1.0, lang=self.lang
        )
        pcm_bytes = (samples * 32767).astype(np.int16).tobytes()

        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(_SAMPLE_WIDTH)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)
