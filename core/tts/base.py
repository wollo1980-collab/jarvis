"""
TTSBackend-Protokoll (ADR-008): einheitliche Schnittstelle für
unterschiedliche Sprachausgabe-Engines, damit core/speech.py nicht
wissen muss, welcher Anbieter gerade aktiv ist.

Kleinster gemeinsamer Nenner aller Anbieter (Piper, OpenAI,
ElevenLabs, Kokoro): Text rein, fertige WAV-Datei raus - passt zur
bestehenden winsound-Wiedergabe in core/speech.py, ohne dass die
Wiedergabe-Logik wissen muss, ob die Datei lokal synthetisiert oder
von einer Cloud-API heruntergeladen wurde.
"""
from __future__ import annotations

from typing import Protocol


class TTSBackend(Protocol):
    name: str

    def synthesize_to_file(self, text: str, output_path: str) -> None:
        """Erzeugt eine abspielbare WAV-Datei unter output_path.
        Muss Fehler (Netzwerk, API, fehlendes Modell) als Exception
        durchreichen - das Auffangen/Fallback-auf-Konsolenausgabe
        passiert bewusst zentral in core/speech.py, nicht hier."""
        ...
