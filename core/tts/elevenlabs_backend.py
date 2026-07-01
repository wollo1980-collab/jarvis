"""ElevenLabs-TTS-Backend (Cloud) - siehe ADR-008.

Braucht einen EIGENEN ElevenLabs-API-Key (nicht denselben wie
OpenAI) und eine gewaehlte voice_id aus der ElevenLabs-Stimmen-
bibliothek. ElevenLabs liefert nativ MP3 oder rohes PCM ohne
Header - wir fordern pcm_24000 an und verpacken es selbst per
wave-Modul in eine abspielbare WAV-Datei, damit sich dieses Backend
fuer core/speech.py exakt wie jedes andere verhaelt.

Erfordert zusaetzlich: pip install elevenlabs
"""
from __future__ import annotations

import logging
import wave

logger = logging.getLogger("jarvis.tts.elevenlabs")

try:
    from elevenlabs.client import ElevenLabs
except ImportError:  # elevenlabs nicht installiert - optionale Abhaengigkeit
    ElevenLabs = None

_SAMPLE_RATE = 24000  # passend zu output_format="pcm_24000"
_SAMPLE_WIDTH = 2  # 16-bit PCM


class ElevenLabsBackend:
    name = "elevenlabs"

    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model_id: str = "eleven_multilingual_v2",
    ):
        if ElevenLabs is None:
            raise RuntimeError(
                "'elevenlabs' ist nicht installiert (pip install elevenlabs)."
            )
        if not api_key or not voice_id:
            raise RuntimeError(
                "TTS-Backend 'elevenlabs' braucht elevenlabs_api_key UND "
                "elevenlabs_voice_id in config.json."
            )
        self.client = ElevenLabs(api_key=api_key)
        self.voice_id = voice_id
        self.model_id = model_id

    def synthesize_to_file(self, text: str, output_path: str) -> None:
        chunks = self.client.text_to_speech.convert(
            voice_id=self.voice_id,
            model_id=self.model_id,
            text=text,
            output_format="pcm_24000",
        )
        pcm_bytes = b"".join(chunks)

        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(_SAMPLE_WIDTH)
            wav_file.setframerate(_SAMPLE_RATE)
            wav_file.writeframes(pcm_bytes)
