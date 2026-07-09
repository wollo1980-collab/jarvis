"""
Speech Layer. Definiert die Schnittstelle, damit main.py nicht wissen
muss, welche STT/TTS-Engine tatsächlich verwendet wird.

v0.3: Sprachausgabe über Piper TTS (lokal/offline, kein Cloud-Dienst)
statt reiner Konsolenausgabe - siehe ADR-005. Spracheingabe bleibt
bewusst Konsole: Mikrofon/Wake-Word ist ein eigenes, noch offenes
Feature (Handbook Kap. 27, "Next"), nicht Teil der v0.3 Definition of
Done.

v0.3.6 (ADR-008): Die TTS-Engine ist jetzt hinter core.tts.TTSBackend
abstrahiert. SpeechEngine kennt nur noch "gibt es ein Backend, ja
oder nein" - welcher Anbieter (Piper/OpenAI/ElevenLabs/Kokoro) aktiv
ist, entscheidet sich allein über Config.tts_backend + die passenden
Zugangsdaten in config.json. Damit dieser Umbau NICHT zu einer
Regression wird: Backend fehlt/Fehler beim Laden/Fehler beim Sprechen
-> say() gibt IMMER den Text auf der Konsole aus, die gesprochene
Ausgabe fällt einfach weg (dasselbe Prinzip wie schon bei reinem
Piper in v0.3 - niemals stillschweigend scheitern, aber auch niemals
deswegen unbenutzbar werden).
"""
from __future__ import annotations

import logging
import platform
import sys
import tempfile
from pathlib import Path

from core.config import Config
from core.tts.factory import create_backend

logger = logging.getLogger("jarvis.speech")


class SpeechEngine:
    def __init__(self, config: Config):
        self.backend = create_backend(config) if config.tts_enabled else None

    def listen(self) -> str:
        """Gibt Nutzereingabe zurück. v0.3: weiterhin Konsole statt
        Mikrofon (siehe Moduldoc)."""
        return input("Du: ").strip()

    def say(self, text: str) -> None:
        """Gibt eine Antwort aus: auf der Konsole (falls vorhanden - unter
        pythonw ist sys.stdout None, ADR-041/PTT), zusätzlich per TTS-Backend
        gesprochen, wenn eins geladen werden konnte und Jarvis unter Windows
        läuft."""
        if sys.stdout is not None:
            print(f"Jarvis: {text}")

        if self.backend is None:
            return
        if platform.system() != "Windows":
            logger.debug("TTS-Wiedergabe übersprungen: nur unter Windows implementiert.")
            return

        self._speak(text)

    def _speak(self, text: str) -> None:
        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = tmp.name

            self.backend.synthesize_to_file(text, wav_path)

            import winsound  # Modul existiert nur unter Windows

            winsound.PlaySound(wav_path, winsound.SND_FILENAME)
        except Exception as e:
            logger.error(
                "TTS-Wiedergabe fehlgeschlagen (Backend '%s'): %s",
                getattr(self.backend, "name", "?"),
                e,
            )
        finally:
            if wav_path:
                Path(wav_path).unlink(missing_ok=True)
