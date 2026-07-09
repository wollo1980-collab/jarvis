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
    assert any("verstanden" in c.args[0].lower() for c in channel.speak.call_args_list)


def test_transcriber_error_speaks_and_does_not_execute():
    runtime = MagicMock()
    channel = _channel(transcriber=FakeTranscriber(RuntimeError("api kaputt")), runtime=runtime)

    _run_toggle_cycle(channel)

    runtime.submit.assert_not_called()
    channel.speak.assert_called()


def test_empty_audio_speaks_and_does_not_transcribe():
    runtime = MagicMock()
    transcriber = FakeTranscriber()
    channel = _channel(transcriber=transcriber, recorder=lambda: b"", runtime=runtime)

    _run_toggle_cycle(channel)

    assert transcriber.calls == []
    runtime.submit.assert_not_called()
    assert any("aufgenommen" in c.args[0].lower() for c in channel.speak.call_args_list)


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


def test_make_speakable_leaves_short_text_untouched():
    from hotkey_channel import make_speakable

    assert make_speakable("Notiert, Sir: «Zahnarzt» — 09:00") == "Notiert, Sir: «Zahnarzt» — 09:00"
    assert make_speakable("") == ""


def test_to_wav_produces_valid_mono_16k():
    data = _to_wav(b"\x00\x01" * 160)
    with wave.open(io.BytesIO(data), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == SAMPLE_RATE
        assert w.getsampwidth() == 2
