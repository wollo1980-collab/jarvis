"""
Sprach-Eingabe: Transkription (Speech-to-Text) ueber OpenAI - das Geschwister
des OpenAI-TTS-Backends (core/tts/openai_backend.py, das bereits
client.audio.speech.create nutzt; hier die Gegenrichtung
client.audio.transcriptions.create). Nutzt denselben openai_api_key (ADR-018).

Audio wird ausschliesslich IM SPEICHER verarbeitet - hier wird nichts auf Platte
geschrieben; der Aufrufer reicht die Bytes durch (PO-Auflage 2026-07-08). Der
OpenAI-Client ist fuer Tests injizierbar (kein echter API-Call/Netzwerk).

Datenschutz (ADR-038): die Sprachnachricht verlaesst den Rechner zur
Transkription an OpenAI - bewusste, dokumentierte Entscheidung, konsistent damit,
dass Text ohnehin an OpenAI geht.
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger("jarvis.transcribe")

# Standard-Transkriptionsmodell (in config.json ueberschreibbar).
DEFAULT_TRANSCRIPTION_MODEL = "whisper-1"


class OpenAITranscriber:
    """Transkribiert Audio-Bytes zu Text ueber die OpenAI-Audio-API. Der Client
    ist injizierbar (Tests uebergeben einen Fake, kein echter Aufruf)."""

    def __init__(self, api_key: str, model: str = DEFAULT_TRANSCRIPTION_MODEL, *, timeout: float = 60.0, client=None):
        self.model = model
        if client is not None:
            self.client = client
            return
        if not api_key:
            raise ValueError("Transkription braucht einen OpenAI-API-Key (OPENAI_API_KEY).")
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, timeout=timeout)

    def transcribe(self, audio: bytes, filename: str = "voice.ogg") -> str:
        """Wandelt Audio-Bytes in Text. Wirft bei leerem Audio; API-/Netzwerk-
        fehler propagieren an den Aufrufer, der sie OHNE Ausfuehrung abfaengt
        (PO-Auflage). Der Dateiname traegt nur die Endung, damit OpenAI das
        Format erkennt (Telegram-Sprachnachricht = OGG/OPUS)."""
        if not audio:
            raise ValueError("Leeres Audio - nichts zu transkribieren.")
        buffer = io.BytesIO(audio)
        buffer.name = filename
        result = self.client.audio.transcriptions.create(model=self.model, file=buffer)
        return (getattr(result, "text", "") or "").strip()
