"""Tests fuer hotkey_channel.py (ADR-041) - kein echtes Mikrofon, keine
echten Tastatur-Hooks: recorder/transcriber/speak sind injiziert, die
optionalen Modul-Abhaengigkeiten werden gemonkeypatcht."""
from __future__ import annotations

import io
import threading
import time
import wave
from unittest.mock import MagicMock

import hotkey_channel
from hotkey_channel import SAMPLE_RATE, HotkeyChannel, _to_wav


class FakeTranscriber:
    def __init__(self, text="erinnere mich an den Test"):
        self.text = text
        self.calls: list = []

    def transcribe(self, audio: bytes, filename: str = "") -> str:
        self.calls.append((audio, filename))
        if isinstance(self.text, Exception):
            raise self.text
        return self.text


def _channel(transcriber=None, recorder=None, runtime=None):
    return HotkeyChannel(
        runtime=runtime or MagicMock(),
        transcriber=transcriber or FakeTranscriber(),
        speak=MagicMock(),
        recorder=recorder or (lambda: b"PCM-DATEN"),
    )


def _run_toggle_cycle(channel):
    """Erster Hotkey-Druck startet den Worker; auf Abschluss warten."""
    channel._on_hotkey()
    channel._worker.join(timeout=2.0)
    assert not channel._worker.is_alive()


def test_toggle_records_transcribes_and_submits():
    runtime = MagicMock()
    transcriber = FakeTranscriber("was steht an?")
    channel = _channel(transcriber=transcriber, runtime=runtime)

    _run_toggle_cycle(channel)

    # Aufnahme wurde als WAV an den Transcriber gegeben ...
    audio, filename = transcriber.calls[0]
    assert audio.startswith(b"RIFF") and filename == "ptt.wav"
    # ... und das Transkript in die normale Pipeline (volle Intents, async).
    runtime.submit.assert_called_once()
    args, kwargs = runtime.submit.call_args
    assert args[0] == "was steht an?"
    assert kwargs.get("allow_async") is True
    assert "plan_filter" not in kwargs  # lokaler Kanal = wie Konsole


def test_second_press_stops_recording():
    """Toggle: Waehrend der recorder auf das Flag wartet, beendet der zweite
    Druck die Aufnahme - der Worker laeuft durch."""
    channel = _channel()

    def waiting_recorder():
        while channel._recording.is_set():
            time.sleep(0.01)
        return b"PCM"

    channel._recorder = waiting_recorder
    channel._on_hotkey()          # Start
    time.sleep(0.05)
    channel._on_hotkey()          # Stopp
    channel._worker.join(timeout=2.0)

    channel.runtime.submit.assert_called_once()


def test_empty_transcript_speaks_and_does_not_execute():
    runtime = MagicMock()
    channel = _channel(transcriber=FakeTranscriber(""), runtime=runtime)

    _run_toggle_cycle(channel)

    runtime.submit.assert_not_called()
    assert any("verstanden" in c.args[0].lower() for c in channel._raw_speak.call_args_list)


def test_transcriber_error_speaks_and_does_not_execute():
    runtime = MagicMock()
    channel = _channel(transcriber=FakeTranscriber(RuntimeError("api kaputt")), runtime=runtime)

    _run_toggle_cycle(channel)

    runtime.submit.assert_not_called()
    channel._raw_speak.assert_called()


def test_empty_audio_speaks_and_does_not_transcribe():
    runtime = MagicMock()
    transcriber = FakeTranscriber()
    channel = _channel(transcriber=transcriber, recorder=lambda: b"", runtime=runtime)

    _run_toggle_cycle(channel)

    assert transcriber.calls == []
    runtime.submit.assert_not_called()
    assert any("aufgenommen" in c.args[0].lower() for c in channel._raw_speak.call_args_list)


def test_start_refuses_gracefully_without_dependencies(monkeypatch):
    monkeypatch.setattr(hotkey_channel, "_sounddevice", None)
    channel = _channel()
    assert channel.start() is False  # kein Crash, kein Listener


def test_stop_without_start_is_safe():
    channel = _channel()
    channel.stop()  # darf nicht werfen


def test_make_speakable_drops_sources_and_urls():
    """Nutzungslauf-Befund 2026-07-09: URLs und Quellen-Bloecke werden nicht
    vorgelesen - Text-Kanaele behalten sie."""
    from hotkey_channel import make_speakable

    text = (
        "Kurzer Ueberblick zu den Treffern. Details unter https://example.com/sehr/lange/url dazu.\n\n"
        "Quellen:\n- https://tagesschau.de/x\n- https://spiegel.de/y"
    )
    spoken = make_speakable(text)
    assert "http" not in spoken
    assert "Quellen" not in spoken
    assert "Kurzer Ueberblick zu den Treffern." in spoken


def test_make_speakable_caps_long_answers_at_sentence():
    from hotkey_channel import _MAX_SPOKEN_CHARS, make_speakable

    long_text = ("Das ist ein Satz mit etwas Inhalt. " * 60).strip()
    spoken = make_speakable(long_text)
    assert len(spoken) < len(long_text)
    assert len(spoken) <= _MAX_SPOKEN_CHARS + 50
    assert spoken.endswith("— so weit der Überblick, Sir.")


def test_make_speakable_speaks_ordinals_instead_of_numbers():
    """Nutzungslauf-Befund 2026-07-09: '1. 2. 3.' wird als 'eins, zwei, drei'
    vorgelesen - gesprochen soll es 'Erstens ... Zweitens ...' heissen."""
    from hotkey_channel import make_speakable

    spoken = make_speakable("Die Lage, Sir:\n1. Meldung A\n2. Meldung B\n3. Meldung C")
    assert "Erstens: Meldung A" in spoken
    assert "Zweitens: Meldung B" in spoken
    assert "Drittens: Meldung C" in spoken
    assert "1." not in spoken and "2." not in spoken


def test_make_speakable_leaves_short_text_untouched():
    from hotkey_channel import make_speakable

    assert make_speakable("Notiert, Sir: «Zahnarzt» — 09:00") == "Notiert, Sir: «Zahnarzt» — 09:00"
    assert make_speakable("") == ""


def test_quiet_streams_bridges_missing_stderr(monkeypatch):
    """Live-Fund 2026-07-09: unter pythonw ist stderr None - openwakewords
    tqdm-Download crashte damit ('Wake-Word-Modell nicht ladbar'). Der
    Kontextmanager ueberbrueckt fehlende Streams und stellt sie wieder her."""
    import sys

    from hotkey_channel import _quiet_streams

    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(sys, "stdout", None)
    with _quiet_streams():
        assert sys.stderr is not None and sys.stdout is not None
        sys.stderr.write("tqdm darf schreiben")  # darf nicht werfen
    assert sys.stderr is None and sys.stdout is None  # sauber restauriert


# --- Wake-Word (ADR-044) ------------------------------------------------------


class FakeStream:
    """Mikrofonstream-Ersatz: liefert vorbereitete (frames, score)-Paare.
    numpy-Arrays wie sounddevice sie liefert."""

    def __init__(self, frames):
        import numpy as np

        self._frames = [np.full((1280, 1), amplitude, dtype=np.int16) for amplitude in frames]
        self._i = 0

    def read(self, n):
        if self._i >= len(self._frames):
            raise StopIteration("keine Frames mehr")
        frame = self._frames[self._i]
        self._i += 1
        return frame, False


def _wake_listener(channel, scores):
    """Listener mit injiziertem Scorer: gibt der Reihe nach `scores` zurueck."""
    from hotkey_channel import WakeWordListener

    it = iter(scores)
    return WakeWordListener(channel, scorer=lambda frame: next(it, 0.0))


def test_wake_word_triggers_shared_pipeline(monkeypatch):
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: None)
    channel = _channel()
    channel.process_audio = MagicMock()
    listener = _wake_listener(channel, scores=[0.1, 0.9])  # 2. Frame weckt
    # Nach dem Trigger: Aufnahme bis Stille - hier sofort still (Amplitude 0),
    # Mindestdauer erzwingt ein paar Frames.
    stream = FakeStream([500, 500] + [0] * 40)

    try:
        listener._listen_loop(stream)
    except StopIteration:
        pass  # Frames aufgebraucht = Loop-Ende im Test

    channel.process_audio.assert_called_once()
    audio = channel.process_audio.call_args.args[0]
    assert isinstance(audio, bytes) and len(audio) > 0


def test_wake_word_below_threshold_never_triggers(monkeypatch):
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: None)
    channel = _channel()
    channel.process_audio = MagicMock()
    listener = _wake_listener(channel, scores=[0.1, 0.3, 0.49, 0.2])
    stream = FakeStream([500] * 4)

    try:
        listener._listen_loop(stream)
    except StopIteration:
        pass

    channel.process_audio.assert_not_called()


def test_wake_word_muted_while_jarvis_speaks(monkeypatch):
    """Selbstschutz (ADR-044): waehrend der TTS-Wiedergabe zaehlt kein Score -
    Jarvis weckt sich nicht mit der eigenen Stimme."""
    monkeypatch.setattr(hotkey_channel, "_beep", lambda start: None)
    channel = _channel()
    channel.process_audio = MagicMock()
    channel._speaking.set()  # Jarvis "spricht"
    listener = _wake_listener(channel, scores=[0.99, 0.99, 0.99])
    stream = FakeStream([500] * 3)

    try:
        listener._listen_loop(stream)
    except StopIteration:
        pass

    channel.process_audio.assert_not_called()


def test_wake_word_start_refuses_without_package(monkeypatch):
    from hotkey_channel import WakeWordListener

    monkeypatch.setattr(hotkey_channel, "_openwakeword", None)
    listener = WakeWordListener(_channel())
    assert listener.start() is False


def test_channel_without_wake_flag_starts_no_listener(monkeypatch):
    """wake_word=False (Default): kein Dauer-Lauscher - Privacy-by-default."""
    channel = HotkeyChannel(
        runtime=MagicMock(), transcriber=MagicMock(), speak=MagicMock(), wake_word=False
    )
    assert channel._wake_word_enabled is False
    assert channel._wake_listener is None


def test_speak_sets_and_clears_speaking_flag():
    seen = []
    channel = HotkeyChannel(
        runtime=MagicMock(),
        transcriber=MagicMock(),
        speak=lambda text: seen.append(channel._speaking.is_set()),
    )
    channel.speak("Hallo")
    assert seen == [True]              # waehrend der Ausgabe gesetzt
    assert not channel._speaking.is_set()  # danach wieder frei


def test_to_wav_produces_valid_mono_16k():
    data = _to_wav(b"\x00\x01" * 160)
    with wave.open(io.BytesIO(data), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == SAMPLE_RATE
        assert w.getsampwidth() == 2
