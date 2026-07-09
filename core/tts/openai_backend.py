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

# Streaming-Platzhalter, den OpenAI in die WAV-Groessenfelder schreibt.
_STREAMING_PLACEHOLDER = 0xFFFFFFFF


def _fix_wav_header(data: bytes) -> bytes:
    """Repariert die Groessenfelder im WAV-Header. OpenAI streamt die Datei
    (Transfer-Encoding: chunked) und traegt als RIFF-/data-Groesse den
    Platzhalter 0xFFFFFFFF ein - tolerante Player schlucken das, Windows'
    winsound.PlaySound verweigert STUMM (Live-Fund 2026-07-09: Piptoene ja,
    Antwort nein, kein Fehler im Log). Nicht-WAV-Daten kommen unveraendert
    zurueck (fail-safe)."""
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return data

    out = bytearray(data)
    out[4:8] = (len(data) - 8).to_bytes(4, "little")
    # data-Chunk direkt suchen statt Chunk-Iteration - die Platzhalter-
    # Groessen wuerden jede Iteration in die Irre fuehren.
    i = data.find(b"data", 12)
    if i != -1 and i + 8 <= len(data):
        out[i + 4 : i + 8] = (len(data) - i - 8).to_bytes(4, "little")
    return bytes(out)


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
        # Header reparieren statt direkt zu streamen - sonst spielt winsound
        # die Datei stumm nicht ab (siehe _fix_wav_header).
        with open(output_path, "wb") as f:
            f.write(_fix_wav_header(response.content))
