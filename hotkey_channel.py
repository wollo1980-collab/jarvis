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
# 1.0 statt 1.5 (Latenz-Scheibe, PO-Befund 2026-07-10 "alles etwas langsamer
# als ChatGPT-Voice"): eine halbe Sekunde weniger Warten nach JEDEM Satzende.
# Rueckfall auf 1.5, falls langsame Sprecher mitten im Satz abgeschnitten werden.
_SILENCE_SECONDS = 1.0
_LEADIN_SECONDS = 4.0
# Adaptive Sprach-Schwelle (Live-Fund 2026-07-09: feste 300 verpasste leise
# Sprecher/entfernte Mikrofone - die Frage wurde als "keine Sprache" verworfen).
# Kalibrierung am gerade gehoerten "Hey Jarvis": Schwelle = Anteil des
# Stimmpegels des Wake-Words, gedeckelt durch die alte Konstante, mit
# Untergrenze gegen Rauschen.
# Die Untergrenze ist ihrerseits relativ gedeckelt (Live-Fund 2026-07-10:
# Wake-Word mit Pegel ~61, Frage mit Spitzenpegel 59 - die starre 60 verwarf
# sie wortlos): nie hoeher als die Haelfte des gehoerten Stimmpegels.
# ABER nie unter das absolute Rausch-Minimum (2. Live-Fund 2026-07-10,
# "er hoert staendig zu": Fehl-Trigger bei Stimmpegel ~21 = Grundrauschen
# ergab Schwelle 11 - UNTER dem Rauschen von 16-21; das Anschluss-Fenster
# konnte nie schliessen, Whisper transkribierte Rauschen). Trigger mit
# Stimmpegel unter dem Minimum sind Fehltrigger und werden still verworfen.
_RECENT_RMS_FRAMES = 13  # ~1 s Rueckblick (13 x 80 ms) - deckt das Wake-Word ab
_VOICE_LEVEL_FRACTION = 0.25
_MIN_RMS_THRESHOLD = 60.0
_FLOOR_LEVEL_FRACTION = 0.5
_ABS_MIN_RMS_THRESHOLD = 30.0  # deutlich ueber gemessenem Grundrauschen (16-21)
# Konversationsfluss (Nutzungslauf-Befund 2026-07-10: "Hey Jarvis" vor JEDEM
# Satz stoert): Nach einer gesprochenen Antwort bleibt ein Anschluss-Fenster
# offen - sprechen ohne neues Wake-Word, beliebig viele Runden. Schweigen
# schliesst das Fenster (dezenter Ton).
_FOLLOWUP_WINDOW_SECONDS = 6.0
# Maximale Wartezeit, bis die gesprochene Antwort beginnt (LLM+TTS-Latenz);
# kommt keine (z. B. Fehler), faellt der Lauscher in den Wake-Modus zurueck.
_REPLY_WAIT_SECONDS = 45.0


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
# Varianten statt Einheitssatz (Persona-Lebendigkeit, PO-Befund 2026-07-10).
_SPOKEN_SUFFIXES = (
    " — so weit der Überblick, Sir.",
    " — das Wesentliche in Kürze, Sir.",
    " — mehr davon gern auf Nachfrage, Sir.",
)

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
    # Listen (Briefings, Merkposten) nie mitten in einem Punkt abschneiden
    # (Nutzungslauf-Befund 2026-07-10: "Die Lage" brach mitten in Meldung 2
    # ab): erst an der letzten vollstaendigen Zeile kappen, nur einzeilige
    # Texte am Satzende.
    line_end = cut.rfind("\n")
    sentence_end = cut.rfind(". ")
    if line_end > 100:
        cut = cut[:line_end]
    elif sentence_end > 100:
        cut = cut[: sentence_end + 1]
    from core.phrases import pick

    return cut.rstrip() + pick(*_SPOKEN_SUFFIXES)


def _to_wav(pcm: bytes) -> bytes:
    """PCM-Rohdaten (16 kHz mono int16) -> WAV-Bytes im Speicher."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buffer.getvalue()


def _silence_wav(milliseconds: int = 700) -> bytes:
    """Kurzes Stille-WAV (16 kHz mono, 16 bit) als Aufweck-Vorlauf: Audio-
    geraete im Energiesparmodus verzerren nach langer Ruhe den ERSTEN Ton
    (Live-Befund 2026-07-10: "Ja, Sir?" kam als Rauschen). Die Stille weckt
    das Geraet, die Bestaetigung kommt danach sauber. 300 ms reichten nicht
    immer (Live-Befund 2026-07-10, 2. Runde: kurze Variante "Sir?" wurde
    nach ~18 s Ruhe komplett verschluckt) - deshalb 700 ms."""
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(b"\x00\x00" * int(SAMPLE_RATE * milliseconds / 1000))
    return buffer.getvalue()


_WAKE_PREROLL = _silence_wav()


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
        # WARNING statt DEBUG (Live-Befund 2026-07-10: eine stumme Wake-
        # Bestaetigung liess sich im Log nicht nachvollziehen).
        logger.warning("WAV-Bytes-Wiedergabe fehlgeschlagen.", exc_info=True)


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
        wake_acks: Optional[list] = None,
    ):
        self.runtime = runtime
        self.transcriber = transcriber
        self._raw_speak = speak
        # Mitschrift-Hook (PO-Wunsch 10.07.2026): (role, text) je Transkript/
        # Antwort - die Verdrahtungsschicht haengt hier das Browser-UI an.
        self.transcript_listener: Optional[Callable[[str, str], None]] = None
        # Orb-Zustaende ins UI (hoert/arbeitet/spricht/bereit) - dito.
        self.state_listener: Optional[Callable[[str], None]] = None
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
        # Gecachte gesprochene Wake-Bestaetigungen ("Ja, Sir?" & Varianten) -
        # beim Start synthetisiert, pro Zuruf zufaellig gewaehlt
        # (Lebendigkeit, PO-Befund 2026-07-10). Leer -> Piepton.
        self._wake_acks: list = list(wake_acks or [])
        self._wake_listener: Optional["WakeWordListener"] = None

    def speak(self, text: str) -> None:
        """Gesprochene Ausgabe mit Selbstschutz: waehrend der Wiedergabe ist
        das Wake-Word stummgeschaltet (self._speaking). Der Orb im UI atmet
        mit (PO-Wunsch 10.07.2026): spricht -> bereit."""
        self._speaking.set()
        self._notify_state("spricht")
        try:
            self._raw_speak(text)
        finally:
            self._speaking.clear()
            self._notify_state("bereit")

    def _notify_state(self, value: str) -> None:
        """Orb-Zustand ins UI (Verdrahtung setzt state_listener auf
        browser.publish). Beiwerk - darf nie die Sprachpipeline stoeren."""
        listener = getattr(self, "state_listener", None)
        if listener is None:
            return
        try:
            listener(value)
        except Exception:  # noqa: BLE001
            logger.debug("State-Listener fehlgeschlagen.", exc_info=True)

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
            self._notify_state("hoert")
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

        transcribe_started = time.monotonic()
        try:
            transcript = self.transcriber.transcribe(_to_wav(audio), "ptt.wav")
        except Exception:  # noqa: BLE001
            logger.exception("PTT-Transkription fehlgeschlagen.")
            self.speak("Verzeihung, Sir - ich konnte die Aufnahme nicht verstehen.")
            return
        transcribe_seconds = time.monotonic() - transcribe_started

        if not transcript:
            self.speak("Ich habe nichts verstanden, Sir - bitte noch einmal.")
            return

        # Kein Inhalt im Log (nur Laenge) - gesprochene Eingaben koennen
        # Privates enthalten; die Redaction greift erst bei der Persistenz.
        logger.info("PTT: Transkript erhalten (%d Zeichen) - Verarbeitung startet.", len(transcript))
        self._notify_state("arbeitet")
        # Mitschrift ins UI (PO-Wunsch 10.07.2026): Zuruf/Hotkey-Gespraeche
        # erscheinen im Browser-Gesicht. Der Listener wird von der
        # Verdrahtungsschicht gesetzt (BrowserChannel); Fehler dort duerfen
        # weder Transkription noch Antwort stoeren.
        self._notify_transcript("user", transcript)

        # Messinstrument (Latenz-Scheibe 2026-07-10): erst messen, dann
        # optimieren - nur Dauern und Laengen im Log, nie Inhalte.
        submitted = time.monotonic()

        def reply(answer: str) -> None:
            logger.info(
                "Latenz: Transkription %.1fs · Verarbeitung %.1fs (Antwort %d Zeichen).",
                transcribe_seconds, time.monotonic() - submitted, len(answer),
            )
            self._notify_transcript("jarvis", answer)
            self.speak(answer)

        # Lokaler Kanal = volle Intents wie die Konsole (kein plan_filter);
        # allow_async=True: langlaufende Delegationen quittieren gesprochen
        # und melden das Ergebnis spaeter gesprochen (speak ist push-faehig).
        self.runtime.submit(transcript, reply, allow_async=True, source="voice")

    def _notify_transcript(self, role: str, text: str) -> None:
        listener = getattr(self, "transcript_listener", None)
        if listener is None:
            return
        try:
            listener(role, text)
        except Exception:  # noqa: BLE001 - Mitschrift ist Beiwerk
            logger.debug("Transkript-Listener fehlgeschlagen.", exc_info=True)

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
            if voice_level < _ABS_MIN_RMS_THRESHOLD:
                # Fehltrigger aus Rauschen (Live-Fund 2026-07-10): ein echtes
                # "Hey Jarvis" hat deutlich mehr Pegel. Still verwerfen -
                # KEIN "Ja, Sir?" aus dem Nichts, keine Endlos-Lauscherei.
                logger.info(
                    "Wake-Trigger verworfen: Stimmpegel ~%.0f unter Rausch-Minimum %.0f.",
                    voice_level, _ABS_MIN_RMS_THRESHOLD,
                )
                self._reset_model()
                recent_rms.clear()
                self._last_trigger = time.monotonic()
                continue
            floor = min(
                _MIN_RMS_THRESHOLD,
                max(_ABS_MIN_RMS_THRESHOLD, voice_level * _FLOOR_LEVEL_FRACTION),
            )
            threshold = max(
                min(voice_level * _VOICE_LEVEL_FRACTION, _SILENCE_RMS_THRESHOLD),
                floor,
            )
            logger.info(
                "Wake-Word erkannt (Score %.2f, Stimmpegel ~%.0f, Sprach-Schwelle %.0f).",
                score, voice_level, threshold,
            )
            self._last_trigger = time.monotonic()
            self._announce()
            self.channel._notify_state("hoert")
            audio = self._record_until_silence(stream, threshold)
            _beep(start=False)
            if audio:
                self.channel.process_audio(audio)
                # Konversationsfluss: nach der Antwort direkt weitersprechen,
                # ohne neues Wake-Word (Nutzungslauf-Befund 2026-07-10).
                self._conversation_loop(stream, threshold)
            else:
                self.channel._notify_state("bereit")
                # Wake ohne Anschlussfrage (Fehltrigger/Schweigen): still
                # verwerfen statt jedes Mal zu antworten.
                logger.info("Wake-Word ohne Anschlussfrage - verworfen.")
            # Modell-Puffer leeren, sonst feuert das alte "Hey Jarvis" beim
            # Weiterlauschen sofort erneut (Endlos-Schleife, Live-Fund).
            self._reset_model()
            recent_rms.clear()
            self._last_trigger = time.monotonic()

    def _conversation_loop(self, stream, threshold: float) -> None:
        """Haelt das Gespraech offen: auf das Ende der gesprochenen Antwort
        warten, dann ein Anschluss-Fenster oeffnen (hoert-Zustand im Orb).
        Spricht der Nutzer, geht es in dieselbe Pipeline und die naechste
        Runde beginnt; Schweigen schliesst das Fenster (dezenter Ton)."""
        while not self._stop.is_set():
            if not self._await_reply_finished():
                logger.info("Keine gesprochene Antwort - Anschluss-Fenster entfaellt.")
                return
            self._drain_stream(stream)
            self.channel._notify_state("hoert")
            audio = self._record_until_silence(
                stream, threshold, leadin=_FOLLOWUP_WINDOW_SECONDS
            )
            if not audio:
                _beep(start=False)  # Fenster zu - ab jetzt wieder "Hey Jarvis"
                self.channel._notify_state("bereit")
                logger.info("Anschluss-Fenster geschlossen (Schweigen).")
                return
            logger.info("Anschlussfrage ohne Wake-Word aufgenommen.")
            self.channel.process_audio(audio)

    def _await_reply_finished(self, timeout: float = _REPLY_WAIT_SECONDS) -> bool:
        """Wartet, bis die gesprochene Antwort BEGONNEN und GEENDET hat
        (channel._speaking-Fenster). False, wenn keine Antwort kommt."""
        deadline = time.monotonic() + timeout
        while not self.channel._speaking.is_set():
            if self._stop.is_set() or time.monotonic() > deadline:
                return False
            time.sleep(0.1)
        while self.channel._speaking.is_set():
            if self._stop.is_set():
                return False
            time.sleep(0.1)
        return True

    @staticmethod
    def _drain_stream(stream) -> None:
        """Verwirft aufgelaufene Frames (waehrend Antwort/Verarbeitung hat
        das Mikrofon weiter gepuffert - inkl. Jarvis' eigener Stimme aus den
        Lautsprechern; die darf nicht als Anschlussfrage gelten)."""
        try:
            while getattr(stream, "read_available", 0) >= _WAKE_FRAME_SAMPLES:
                stream.read(_WAKE_FRAME_SAMPLES)
        except Exception:  # noqa: BLE001 - Drain ist Hygiene, nie fatal
            logger.debug("Stream-Drain unvollstaendig.", exc_info=True)

    def _announce(self) -> None:
        """Wake-Bestaetigung: gesprochenes "Ja, Sir?" (gecacht, PO-Wunsch
        2026-07-09) - Piepton nur als Rueckfall. Waehrend der Wiedergabe ist
        das Lauschen stumm (eigene Stimme weckt nicht)."""
        acks = self.channel._wake_acks
        if not acks:
            _beep(start=True)
            return
        import random

        self.channel._speaking.set()
        try:
            ack = random.choice(acks)
            # Aufweck-Vorlauf gegen verzerrten Erst-Ton nach Geraete-Standby.
            _play_wav_bytes(_WAKE_PREROLL)
            _play_wav_bytes(ack)
            # Sichtbar loggen (Live-Befund 2026-07-10: Bestaetigung blieb
            # stumm, das Log schwieg dazu - kein Raetselraten mehr).
            logger.info(
                "Wake-Bestaetigung abgespielt (Variante %d von %d, %d Bytes).",
                acks.index(ack) + 1, len(acks), len(ack),
            )
        finally:
            self.channel._speaking.clear()

    def _record_until_silence(
        self,
        stream,
        threshold: float = _SILENCE_RMS_THRESHOLD,
        leadin: float = _LEADIN_SECONDS,
    ) -> bytes:
        """Nimmt nach dem Wake-Word auf: wartet zuerst auf SPRACHBEGINN
        (Vorlauf `leadin` - der Nutzer braucht einen Moment zum Formulieren;
        das Anschluss-Fenster nutzt einen laengeren Vorlauf), dann bis ~1.5 s
        Stille nach dem Sprechen. Kommt gar keine Sprache: leeres Ergebnis
        (der Aufrufer verwirft still). Nur im Speicher; gerechnet in
        AUDIO-Zeit (deterministisch testbar). `threshold` kommt kalibriert
        vom Aufrufer (Pegel des Wake-Words)."""
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
            elif recorded_seconds >= leadin:
                # Diagnose-Pegel loggen (nur Zahlen, kein Inhalt) - damit ein
                # Live-"verworfen" nicht wieder Raetselraten bedeutet.
                logger.info(
                    "Keine Sprache im Vorlauf (Spitzenpegel %.0f, Schwelle %.0f).",
                    peak, threshold,
                )
                return b""  # nie gesprochen - Fehltrigger/Schweigen
        return b"".join(frames) if speech_seen else b""
