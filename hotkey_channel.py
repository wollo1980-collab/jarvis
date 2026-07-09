"""
Push-to-talk am PC (Welle 3.2, ADR-041) - dritter Runtime-Kanal neben
Telegram und Konsole: Hotkey druecken -> Signalton -> sprechen -> Hotkey
erneut druecken (oder max. 15 s) -> Jarvis verarbeitet und ANTWORTET
GESPROCHEN (Piper/Thorsten, lokal). Spotlight-Muster: minimale Distanz
zwischen Gedanke und Jarvis (PO-Ziel #3).

Aufbau analog TelegramChannel: eigener Kanal, die Runtime bleibt kanal-
agnostisch. Die Aufnahme lebt NUR im Speicher (kein Datei-Write, wie
ADR-038); die Transkription nutzt denselben OpenAITranscriber wie die
Telegram-Sprachnachrichten. Der Kanal ist strikt optional: fehlen
sounddevice/pynput/Mikrofon/Transcriber, startet er nicht und alles andere
laeuft unveraendert (graceful wie beim Voice-Handler).

Sicherheit: lokaler Kanal am Geraet -> volle Intents wie die Konsole (kein
plan_filter). Stufe-2/3-Befehle bleiben trotzdem fail-closed gesperrt - die
bestehende _RuntimeSpeech-Sperre der Runtime greift automatisch.

Testbarkeit: recorder, transcriber und speak sind injizierbar; die
optionalen Abhaengigkeiten liegen in Modul-Variablen (_sounddevice,
_keyboard), die Tests monkeypatchen koennen. Kein Test beruehrt echtes
Mikrofon oder echte Tastatur-Hooks.
"""
from __future__ import annotations

import io
import logging
import re
import threading
import time
import wave
from typing import Callable, Optional

logger = logging.getLogger("jarvis.runtime.hotkey")

try:  # optionale Abhaengigkeit (ADR-041)
    import sounddevice as _sounddevice
except Exception:  # noqa: BLE001 - fehlend/kaputt = Kanal bleibt aus
    _sounddevice = None

try:  # optionale Abhaengigkeit (ADR-041)
    from pynput import keyboard as _keyboard
except Exception:  # noqa: BLE001
    _keyboard = None

# Auslöser im pynput-GlobalHotKeys-Format. Bewusst Konstante, kein Config-
# Feld (YAGNI) - wird bei realem Bedarf konfigurierbar.
HOTKEY = "<ctrl>+<alt>+j"

SAMPLE_RATE = 16_000  # Whisper-freundlich: 16 kHz mono int16
MAX_RECORD_SECONDS = 15.0
_BLOCK_SECONDS = 0.1
_WORKER_JOIN_TIMEOUT = 5.0


def dependencies_available() -> bool:
    """True, wenn die optionalen Pakete importierbar sind. Das Mikrofon wird
    separat beim Start geprueft (Geraete koennen zur Laufzeit fehlen)."""
    return _sounddevice is not None and _keyboard is not None


# Sprechfassung (Nutzungslauf-Befund 2026-07-09): Text-Antworten sind fuer
# Text-Kanaele gebaut (URLs, Quellen-Bloecke, Laenge) - vorgelesen sind sie
# eine Qual. Vor dem Sprechen wird deshalb gekuerzt; Telegram/Konsole
# behalten den vollen Text samt Quellen.
_MAX_SPOKEN_CHARS = 600
_URL_RE = re.compile(r"https?://\S+")
_SPOKEN_SUFFIX = " — so weit der Überblick, Sir."

# Nummerierte Listen ("1. ...") liest die Stimme als "eins, zwei, drei" vor
# (Nutzungslauf-Befund 2026-07-09). Gesprochen wird daraus "Erstens: ..." -
# Text-Kanaele behalten die normale Nummerierung.
_LIST_ITEM_RE = re.compile(r"(?m)^(\d+)\.\s+")
_ORDINALS = {
    1: "Erstens: ", 2: "Zweitens: ", 3: "Drittens: ", 4: "Viertens: ",
    5: "Fünftens: ", 6: "Sechstens: ", 7: "Siebtens: ", 8: "Achtens: ",
}


def _spoken_ordinal(match: "re.Match") -> str:
    return _ORDINALS.get(int(match.group(1)), match.group(0))


def make_speakable(text: str) -> str:
    """Macht eine Text-Antwort vorlesbar: Quellen-Block weg, URLs weg,
    Laengen-Deckel mit sauberem Satzende. Kurze Texte passieren unveraendert."""
    if not text:
        return text
    # Quellen-Block (search_web haengt ihn ans Ende) nicht vorlesen.
    idx = text.find("Quellen:")
    if idx != -1:
        text = text[:idx]
    # Nackte URLs fliegen raus (vorgelesene Links sind wertlos).
    text = _URL_RE.sub("", text)
    # "1. ..." -> "Erstens: ..." (natuerliches Aufzaehlen statt "eins, zwei").
    text = _LIST_ITEM_RE.sub(_spoken_ordinal, text)
    # Aufgeraeumte Leerraeume nach den Schnitten.
    text = re.sub(r"[ \t]+", " ", text).strip()

    if len(text) <= _MAX_SPOKEN_CHARS:
        return text
    cut = text[:_MAX_SPOKEN_CHARS]
    sentence_end = cut.rfind(". ")
    if sentence_end > 100:
        cut = cut[: sentence_end + 1]
    return cut.rstrip() + _SPOKEN_SUFFIX


def _to_wav(pcm: bytes) -> bytes:
    """PCM-Rohdaten (16 kHz mono int16) -> WAV-Bytes im Speicher."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buffer.getvalue()


def _beep(start: bool) -> None:
    """Kurzes akustisches Feedback fuer Aufnahme-Start/-Stopp. Darf nie
    den Ablauf brechen (winsound existiert nur unter Windows)."""
    try:
        import winsound

        winsound.Beep(880 if start else 440, 120)
    except Exception:  # noqa: BLE001
        logger.debug("Signalton nicht verfuegbar.", exc_info=True)


class HotkeyChannel:
    """Dritter Runtime-Kanal: globaler Hotkey als Toggle (druecken = Aufnahme
    an, erneut druecken = Aufnahme aus und verarbeiten)."""

    def __init__(
        self,
        runtime,
        transcriber,
        speak: Callable[[str], None],
        recorder: Optional[Callable[[], bytes]] = None,
    ):
        self.runtime = runtime
        self.transcriber = transcriber
        self.speak = speak
        self._recorder = recorder or self._record_microphone
        self._recording = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._listener = None
        self._toggle_lock = threading.Lock()

    # -- Lifecycle ---------------------------------------------------------

    def start(self) -> bool:
        """Startet den Hotkey-Listener. False (mit Log, ohne Exception), wenn
        Pakete oder Mikrofon fehlen - der Rest der Runtime laeuft normal."""
        if not dependencies_available():
            logger.info("Push-to-talk aus: sounddevice/pynput nicht installiert.")
            return False
        try:
            _sounddevice.query_devices(kind="input")
        except Exception:  # noqa: BLE001 - kein Eingabegeraet
            logger.info("Push-to-talk aus: kein Mikrofon gefunden.")
            return False

        self._listener = _keyboard.GlobalHotKeys({HOTKEY: self._on_hotkey})
        self._listener.start()
        logger.info("Push-to-talk aktiv: %s (max. %.0fs pro Aufnahme).", HOTKEY, MAX_RECORD_SECONDS)
        return True

    def stop(self) -> None:
        """Beendet Listener und eine ggf. laufende Aufnahme (Runtime-Stop)."""
        self._recording.clear()
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:  # noqa: BLE001 - Aufraeumen scheitert nie hart
                logger.debug("Hotkey-Listener-Stop unvollstaendig.", exc_info=True)
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=_WORKER_JOIN_TIMEOUT)

    # -- Hotkey-Toggle -------------------------------------------------------

    def _on_hotkey(self) -> None:
        with self._toggle_lock:
            if self._recording.is_set():
                # Zweiter Druck: Aufnahme beenden - der Worker verarbeitet.
                self._recording.clear()
                return
            self._recording.set()
            self._worker = threading.Thread(
                target=self._capture_and_process, name="jarvis-ptt", daemon=False
            )
            self._worker.start()

    def _capture_and_process(self) -> None:
        """Laeuft im PTT-Worker: aufnehmen -> transkribieren -> in die normale
        Runtime-Pipeline geben. Fehler enden IMMER in einer gesprochenen
        Rueckmeldung, nie in einer Ausfuehrung (Muster ADR-038)."""
        try:
            _beep(start=True)
            audio = self._recorder()
            _beep(start=False)
        except Exception:  # noqa: BLE001
            logger.exception("PTT-Aufnahme fehlgeschlagen.")
            self._recording.clear()
            self.speak("Verzeihung, Sir - die Aufnahme hat nicht geklappt.")
            return
        finally:
            self._recording.clear()

        if not audio:
            self.speak("Da wurde nichts aufgenommen, Sir - das Mikrofon blieb stumm.")
            return

        try:
            transcript = self.transcriber.transcribe(_to_wav(audio), "ptt.wav")
        except Exception:  # noqa: BLE001
            logger.exception("PTT-Transkription fehlgeschlagen.")
            self.speak("Verzeihung, Sir - ich konnte die Aufnahme nicht verstehen.")
            return

        if not transcript:
            self.speak("Ich habe nichts verstanden, Sir - bitte noch einmal.")
            return

        # Kein Inhalt im Log (nur Laenge) - gesprochene Eingaben koennen
        # Privates enthalten; die Redaction greift erst bei der Persistenz.
        logger.info("PTT: Transkript erhalten (%d Zeichen) - Verarbeitung startet.", len(transcript))
        # Lokaler Kanal = volle Intents wie die Konsole (kein plan_filter);
        # allow_async=True: langlaufende Delegationen quittieren gesprochen
        # und melden das Ergebnis spaeter gesprochen (speak ist push-faehig).
        self.runtime.submit(transcript, self.speak, allow_async=True)

    # -- Aufnahme ------------------------------------------------------------

    def _record_microphone(self) -> bytes:
        """Nimmt auf, solange das Toggle gesetzt ist (max. MAX_RECORD_SECONDS).
        Nur im Speicher - es entsteht keine Datei (ADR-038-Prinzip)."""
        frames: list[bytes] = []
        started = time.monotonic()
        with _sounddevice.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16"
        ) as stream:
            while self._recording.is_set() and (time.monotonic() - started) < MAX_RECORD_SECONDS:
                data, _overflowed = stream.read(int(SAMPLE_RATE * _BLOCK_SECONDS))
                frames.append(data.tobytes())
        return b"".join(frames)
