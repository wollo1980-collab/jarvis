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
        # Kill-Switch fuer den Streaming-Pfad (ADR-048): tts_streaming=false
        # erzwingt den bewaehrten Datei-Weg, ohne Code anzufassen.
        self.streaming_enabled = bool(getattr(config, "tts_streaming", True))

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
        import time

        # Streaming zuerst (ADR-048): erster Ton nach dem ersten Chunk statt
        # nach der kompletten Synthese. Jeder Fehlschlag VOR dem ersten Ton
        # faellt lautlos auf den bewaehrten Datei-Weg zurueck.
        if self._speak_streaming(text):
            return

        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = tmp.name

            synth_started = time.monotonic()
            self.backend.synthesize_to_file(text, wav_path)
            synth_seconds = time.monotonic() - synth_started

            import winsound  # Modul existiert nur unter Windows

            playback_started = time.monotonic()
            winsound.PlaySound(wav_path, winsound.SND_FILENAME)
            # Messinstrument (Latenz-Scheibe 2026-07-10): Synthese = Wartezeit
            # bis zum ersten Ton (der Optimierungs-Kandidat fuer Streaming),
            # Wiedergabe = reine Sprechdauer. Nur Zahlen, kein Inhalt.
            logger.info(
                "TTS-Latenz: Synthese %.1fs · Wiedergabe %.1fs (%d Zeichen).",
                synth_seconds, time.monotonic() - playback_started, len(text),
            )
        except Exception as e:
            logger.error(
                "TTS-Wiedergabe fehlgeschlagen (Backend '%s'): %s",
                getattr(self.backend, "name", "?"),
                e,
            )
        finally:
            if wav_path:
                Path(wav_path).unlink(missing_ok=True)

    def _speak_streaming(self, text: str) -> bool:
        """Spielt den Text als PCM-Stream (Backend liefert Chunks, sounddevice
        gibt sie sofort wieder) - True, wenn gesprochen wurde. False heisst:
        Aufrufer soll den Datei-Weg gehen. Bricht der Stream MITTEN in der
        Wiedergabe ab, wird NICHT wiederholt (kein doppeltes Anreden) -
        dann True mit Fehler-Log."""
        if not self.streaming_enabled:
            return False
        stream_fn = getattr(self.backend, "stream_pcm", None)
        if stream_fn is None:
            return False  # Backend (Piper/ElevenLabs/...) kann nur Datei
        try:
            import sounddevice
        except Exception:  # noqa: BLE001 - ohne sounddevice kein Streaming
            return False
        import time

        rate = int(getattr(self.backend, "pcm_sample_rate", 24_000))
        started = time.monotonic()
        first_sound: float | None = None
        leftover = b""
        try:
            with sounddevice.RawOutputStream(
                samplerate=rate, channels=1, dtype="int16"
            ) as out:
                for chunk in stream_fn(text):
                    buf = leftover + chunk
                    cut = len(buf) - (len(buf) % 2)  # int16-Ausrichtung
                    leftover = buf[cut:]
                    if not cut:
                        continue
                    if first_sound is None:
                        first_sound = time.monotonic() - started
                    out.write(buf[:cut])
                # Kurzer Stille-Schwanz, damit das Schliessen des Streams
                # nicht die letzte Silbe kappt.
                out.write(b"\x00\x00" * int(rate * 0.15))
        except Exception as e:  # noqa: BLE001
            if first_sound is None:
                logger.warning("TTS-Streaming fehlgeschlagen (%s) - Datei-Rueckfall.", e)
                return False
            # Es wurde schon gesprochen: nicht nochmal von vorn anreden.
            logger.error("TTS-Streaming mitten in der Wiedergabe abgebrochen: %s", e)
            return True
        if first_sound is None:
            logger.warning("TTS-Streaming lieferte kein Audio - Datei-Rueckfall.")
            return False
        logger.info(
            "TTS-Latenz: erster Ton nach %.1fs · gesamt %.1fs (Streaming, %d Zeichen).",
            first_sound, time.monotonic() - started, len(text),
        )
        return True
