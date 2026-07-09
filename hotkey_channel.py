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
import sys
import threading
import time
import wave
from contextlib import contextmanager
from typing import Callable, Optional

logger = logging.getLogger("jarvis.runtime.hotkey")

try:  # optionale Abhaengigkeit (ADR-041)
    import numpy as _np
    import sounddevice as _sounddevice
except Exception:  # noqa: BLE001 - fehlend/kaputt = Kanal bleibt aus
    _sounddevice = None
    _np = None

try:  # optionale Abhaengigkeit (ADR-041)
    from pynput import keyboard as _keyboard
except Exception:  # noqa: BLE001
    _keyboard = None

try:  # optionale Abhaengigkeit (ADR-044, Wake-Word)
    import openwakeword as _openwakeword
    from openwakeword.model import Model as _WakeWordModel
except Exception:  # noqa: BLE001 - ohne Paket bleibt das Wake-Word aus
    _openwakeword = None
    _WakeWordModel = None

# Auslöser im pynput-GlobalHotKeys-Format. Bewusst Konstante, kein Config-
# Feld (YAGNI) - wird bei realem Bedarf konfigurierbar.
HOTKEY = "<ctrl>+<alt>+j"

SAMPLE_RATE = 16_000  # Whisper-freundlich: 16 kHz mono int16
MAX_RECORD_SECONDS = 15.0
_BLOCK_SECONDS = 0.1
_WORKER_JOIN_TIMEOUT = 5.0

# Wake-Word (ADR-044): openwakeword erwartet 80-ms-Frames bei 16 kHz.
WAKE_WORD_MODEL = "hey_jarvis"
_WAKE_FRAME_SAMPLES = 1280
_WAKE_SCORE_THRESHOLD = 0.5
_WAKE_COOLDOWN_SECONDS = 3.0
# Aufnahme nach dem Wake-Word: erst auf SPRACHBEGINN warten (Vorlauf zum
# Formulieren), dann bis ~1.5 s Stille nach dem Sprechen (RMS-Pegel).
# Live-Fund 2026-07-09: ohne Vorlauf endete die Aufnahme, bevor der Nutzer
# ueberhaupt anfing zu sprechen.
_SILENCE_RMS_THRESHOLD = 300.0
_SILENCE_SECONDS = 1.5
_LEADIN_SECONDS = 4.0
# Adaptive Sprach-Schwelle (Live-Fund 2026-07-09: feste 300 verpasste leise
# Sprecher/entfernte Mikrofone - die Frage wurde als "keine Sprache" verworfen).
# Kalibrierung am gerade gehoerten "Hey Jarvis": Schwelle = Anteil des
# Stimmpegels des Wake-Words, gedeckelt durch die alte Konstante, mit
# Untergrenze gegen Rauschen.
_RECENT_RMS_FRAMES = 13  # ~1 s Rueckblick (13 x 80 ms) - deckt das Wake-Word ab
_VOICE_LEVEL_FRACTION = 0.25
_MIN_RMS_THRESHOLD = 60.0


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


def _frame_rms(frame) -> float:
    """Lautstaerke (RMS) eines int16-Audio-Frames."""
    return float(_np.sqrt(_np.mean(frame.astype(_np.float64) ** 2)))


def _play_wav_bytes(data: bytes) -> None:
    """Spielt WAV-Bytes direkt aus dem Speicher (winsound SND_MEMORY) -
    fuer die gecachte Wake-Bestaetigung ("Ja, Sir?"). Darf nie werfen."""
    try:
        import winsound

        winsound.PlaySound(data, winsound.SND_MEMORY)
    except Exception:  # noqa: BLE001
        logger.debug("WAV-Bytes-Wiedergabe nicht verfuegbar.", exc_info=True)


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
        wake_word: bool = False,
        wake_ack: Optional[bytes] = None,
    ):
        self.runtime = runtime
        self.transcriber = transcriber
        self._raw_speak = speak
        self._recorder = recorder or self._record_microphone
        self._recording = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._listener = None
        self._toggle_lock = threading.Lock()
        # Wake-Word (ADR-044): waehrend Jarvis SELBST spricht, lauscht der
        # Wake-Listener nicht - sonst weckt ihn die eigene Stimme ("Ich bin
        # Jarvis ..."). speak() setzt dieses Flag um die Wiedergabe herum.
        self._speaking = threading.Event()
        self._wake_word_enabled = wake_word
        # Gecachte gesprochene Wake-Bestaetigung ("Ja, Sir?") - beim Start
        # einmal synthetisiert, dann piep-schnell abspielbar. None -> Piepton.
        self._wake_ack = wake_ack
        self._wake_listener: Optional["WakeWordListener"] = None

    def speak(self, text: str) -> None:
        """Gesprochene Ausgabe mit Selbstschutz: waehrend der Wiedergabe ist
        das Wake-Word stummgeschaltet (self._speaking)."""
        self._speaking.set()
        try:
            self._raw_speak(text)
        finally:
            self._speaking.clear()

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

        # Wake-Word (ADR-044) zusaetzlich zum Hotkey - optional, graceful.
        if self._wake_word_enabled:
            self._wake_listener = WakeWordListener(self)
            if not self._wake_listener.start():
                self._wake_listener = None
        return True

    def stop(self) -> None:
        """Beendet Listener und eine ggf. laufende Aufnahme (Runtime-Stop)."""
        self._recording.clear()
        if self._wake_listener is not None:
            self._wake_listener.stop()
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
        """Laeuft im PTT-Worker: aufnehmen, dann in die geteilte Pipeline."""
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

        self.process_audio(audio)

    def process_audio(self, audio: bytes) -> None:
        """Geteilte Pipeline fuer Hotkey UND Wake-Word (ADR-044):
        transkribieren -> in die normale Runtime-Pipeline geben. Fehler enden
        IMMER in einer gesprochenen Rueckmeldung, nie in einer Ausfuehrung
        (Muster ADR-038)."""
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


@contextmanager
def _quiet_streams():
    """Ersetzt fehlende std-Streams temporaer durch Puffer. Unter pythonw
    sind sys.stdout/stderr None - openwakewords Modell-Download zeigt einen
    tqdm-Fortschrittsbalken, der dann mit AttributeError crasht (Live-Fund
    2026-07-09: 'Wake-Word-Modell nicht ladbar')."""
    original_out, original_err = sys.stdout, sys.stderr
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()
    try:
        yield
    finally:
        sys.stdout, sys.stderr = original_out, original_err


def wake_word_available() -> bool:
    """True, wenn openwakeword importierbar ist (zusaetzlich zu den
    Basis-Abhaengigkeiten des Kanals)."""
    return dependencies_available() and _openwakeword is not None


class WakeWordListener:
    """Dauer-Lauscher (ADR-044): Mikrofon-Stream -> 80-ms-Frames -> lokales
    hey_jarvis-Modell. Score ueber Schwelle -> Signalton -> Aufnahme bis
    Stille -> dieselbe Pipeline wie der Hotkey (channel.process_audio).

    Privacy: JEDES Frame wird ausschliesslich lokal bewertet und sofort
    verworfen - nichts wird gespeichert, nichts verlaesst den Rechner, bis
    das Wake-Word erkannt wurde. Waehrend Jarvis selbst spricht
    (channel._speaking), wird nicht gelauscht (kein Selbst-Aufwecken).

    scorer ist injizierbar (Tests: Funktion frame->float statt Modell)."""

    def __init__(
        self,
        channel: HotkeyChannel,
        scorer: Optional[Callable] = None,
        reset: Optional[Callable[[], None]] = None,
    ):
        self.channel = channel
        self._scorer = scorer
        # Modell-Reset nach jedem Trigger (Live-Fund 2026-07-09): openwakeword
        # puffert ~1-2 s Audio - ohne Reset feuert das alte "Hey Jarvis" beim
        # Weiterlauschen sofort erneut (Endlos-Piep-Schleife).
        self._reset_model = reset or (lambda: None)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_trigger = 0.0

    def start(self) -> bool:
        if not wake_word_available():
            logger.info("Wake-Word aus: openwakeword nicht installiert.")
            return False
        if self._scorer is None:
            try:
                # Modelldateien sind klein (~7 MB) und werden nur beim ersten
                # Start heruntergeladen (idempotent). _quiet_streams: der
                # tqdm-Fortschrittsbalken des Downloads braucht stderr, das
                # unter pythonw fehlt.
                with _quiet_streams():
                    _openwakeword.utils.download_models([WAKE_WORD_MODEL])
                model = _WakeWordModel(
                    wakeword_models=[WAKE_WORD_MODEL], inference_framework="onnx"
                )
                self._scorer = lambda frame: float(model.predict(frame)[WAKE_WORD_MODEL])
                if hasattr(model, "reset"):
                    self._reset_model = model.reset
            except Exception:  # noqa: BLE001 - Wake-Word ist strikt optional
                logger.warning("Wake-Word-Modell nicht ladbar - Wake-Word bleibt aus.", exc_info=True)
                return False

        self._thread = threading.Thread(target=self._run, name="jarvis-wakeword", daemon=True)
        self._thread.start()
        logger.info('Wake-Word aktiv: "Hey Jarvis" (Modell lokal, Schwelle %.2f).', _WAKE_SCORE_THRESHOLD)
        return True

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=_WORKER_JOIN_TIMEOUT)

    def _run(self) -> None:
        try:
            with _sounddevice.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16"
            ) as stream:
                self._listen_loop(stream)
        except Exception:  # noqa: BLE001 - Lauscher darf die Runtime nie reissen
            logger.exception("Wake-Word-Lauscher beendet sich nach Fehler.")

    def _listen_loop(self, stream) -> None:
        """Kern-Schleife, mit Fake-Stream testbar. Ein Trigger verarbeitet
        die Folge-Aufnahme SYNCHRON in diesem Thread - waehrenddessen wird
        naturgemaess nicht gelauscht (plus explizite Abklingzeit)."""
        from collections import deque

        recent_rms: deque = deque(maxlen=_RECENT_RMS_FRAMES)
        while not self._stop.is_set():
            data, _overflowed = stream.read(_WAKE_FRAME_SAMPLES)
            frame = data.reshape(-1)
            if self.channel._speaking.is_set():
                continue  # eigene Stimme zaehlt nicht (Selbstschutz)
            if (time.monotonic() - self._last_trigger) < _WAKE_COOLDOWN_SECONDS:
                continue
            recent_rms.append(_frame_rms(frame))
            score = self._scorer(frame)
            if score < _WAKE_SCORE_THRESHOLD:
                continue

            # Sprach-Schwelle am Pegel des gerade gehoerten Wake-Words
            # kalibrieren - so laut wie "Hey Jarvis" kommt, kommt auch die
            # Frage (leiser Sprecher/entferntes Mikrofon inklusive).
            voice_level = max(recent_rms, default=0.0)
            threshold = max(
                min(voice_level * _VOICE_LEVEL_FRACTION, _SILENCE_RMS_THRESHOLD),
                _MIN_RMS_THRESHOLD,
            )
            logger.info(
                "Wake-Word erkannt (Score %.2f, Stimmpegel ~%.0f, Sprach-Schwelle %.0f).",
                score, voice_level, threshold,
            )
            self._last_trigger = time.monotonic()
            self._announce()
            audio = self._record_until_silence(stream, threshold)
            _beep(start=False)
            if audio:
                self.channel.process_audio(audio)
            else:
                # Wake ohne Anschlussfrage (Fehltrigger/Schweigen): still
                # verwerfen statt jedes Mal zu antworten.
                logger.info("Wake-Word ohne Anschlussfrage - verworfen.")
            # Modell-Puffer leeren, sonst feuert das alte "Hey Jarvis" beim
            # Weiterlauschen sofort erneut (Endlos-Schleife, Live-Fund).
            self._reset_model()
            recent_rms.clear()
            self._last_trigger = time.monotonic()

    def _announce(self) -> None:
        """Wake-Bestaetigung: gesprochenes "Ja, Sir?" (gecacht, PO-Wunsch
        2026-07-09) - Piepton nur als Rueckfall. Waehrend der Wiedergabe ist
        das Lauschen stumm (eigene Stimme weckt nicht)."""
        ack = self.channel._wake_ack
        if not ack:
            _beep(start=True)
            return
        self.channel._speaking.set()
        try:
            _play_wav_bytes(ack)
        finally:
            self.channel._speaking.clear()

    def _record_until_silence(self, stream, threshold: float = _SILENCE_RMS_THRESHOLD) -> bytes:
        """Nimmt nach dem Wake-Word auf: wartet zuerst auf SPRACHBEGINN
        (Vorlauf _LEADIN_SECONDS - der Nutzer braucht einen Moment zum
        Formulieren), dann bis ~1.5 s Stille nach dem Sprechen. Kommt gar
        keine Sprache: leeres Ergebnis (der Aufrufer verwirft still). Nur im
        Speicher; gerechnet in AUDIO-Zeit (deterministisch testbar).
        `threshold` kommt kalibriert vom Aufrufer (Pegel des Wake-Words)."""
        frames: list[bytes] = []
        frame_seconds = _WAKE_FRAME_SAMPLES / SAMPLE_RATE
        recorded_seconds = 0.0
        silent_seconds = 0.0
        speech_seen = False
        peak = 0.0
        while recorded_seconds < MAX_RECORD_SECONDS:
            data, _overflowed = stream.read(_WAKE_FRAME_SAMPLES)
            frames.append(data.tobytes())
            recorded_seconds += frame_seconds
            rms = _frame_rms(data)
            peak = max(peak, rms)
            if rms >= threshold:
                speech_seen = True
                silent_seconds = 0.0
            elif speech_seen:
                silent_seconds += frame_seconds
                if silent_seconds >= _SILENCE_SECONDS:
                    break
            elif recorded_seconds >= _LEADIN_SECONDS:
                # Diagnose-Pegel loggen (nur Zahlen, kein Inhalt) - damit ein
                # Live-"verworfen" nicht wieder Raetselraten bedeutet.
                logger.info(
                    "Keine Sprache im Vorlauf (Spitzenpegel %.0f, Schwelle %.0f).",
                    peak, threshold,
                )
                return b""  # nie gesprochen - Fehltrigger/Schweigen
        return b"".join(frames) if speech_seen else b""
