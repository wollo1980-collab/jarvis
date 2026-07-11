"""Tests für core/speech.py - TTS-Backend gemockt (nicht Piper direkt,
seit ADR-008 kennt SpeechEngine nur noch core.tts.create_backend).
Prüft vor allem den Fallback auf Konsolenausgabe, wenn kein Backend
verfügbar ist oder die Wiedergabe scheitert (Jarvis darf dadurch nie
unbenutzbar werden)."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from core.config import Config
from core.speech import SpeechEngine


def test_listen_reads_console_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "  hallo jarvis  ")
    engine = SpeechEngine(Config())
    assert engine.listen() == "hallo jarvis"


def test_say_always_prints_to_console(capsys):
    engine = SpeechEngine(Config())  # tts_enabled=False per Default
    engine.say("Alles klar.")
    assert "Jarvis: Alles klar." in capsys.readouterr().out


def test_no_backend_created_when_tts_disabled():
    with patch("core.speech.create_backend") as create_backend:
        engine = SpeechEngine(Config(tts_enabled=False))
    create_backend.assert_not_called()
    assert engine.backend is None


def test_backend_requested_when_tts_enabled():
    fake_backend = MagicMock(name="fake_backend")
    with patch("core.speech.create_backend", return_value=fake_backend) as create_backend:
        engine = SpeechEngine(Config(tts_enabled=True, tts_backend="piper"))
    create_backend.assert_called_once()
    assert engine.backend is fake_backend


def test_falls_back_when_backend_creation_fails(capsys):
    """create_backend() liefert None, wenn z. B. Piper fehlt, das
    Modell fehlt oder ein API-Key fehlt - siehe core/tts/factory.py."""
    with patch("core.speech.create_backend", return_value=None):
        engine = SpeechEngine(Config(tts_enabled=True))
    assert engine.backend is None
    engine.say("Test")  # darf nicht crashen
    assert "Jarvis: Test" in capsys.readouterr().out


def test_say_speaks_via_backend_on_windows():
    fake_backend = MagicMock(name="fake_backend")
    fake_winsound = MagicMock(SND_FILENAME=1)

    with patch("core.speech.create_backend", return_value=fake_backend):
        engine = SpeechEngine(Config(tts_enabled=True))

    with patch("core.speech.platform.system", return_value="Windows"), patch.dict(
        sys.modules, {"winsound": fake_winsound}
    ):
        engine.say("Hallo")

    fake_backend.synthesize_to_file.assert_called_once()
    fake_winsound.PlaySound.assert_called_once()


def test_say_skips_backend_on_non_windows():
    fake_backend = MagicMock(name="fake_backend")

    with patch("core.speech.create_backend", return_value=fake_backend):
        engine = SpeechEngine(Config(tts_enabled=True))

    with patch("core.speech.platform.system", return_value="Linux"):
        engine.say("Hallo")

    fake_backend.synthesize_to_file.assert_not_called()


def test_say_falls_back_when_backend_playback_fails(capsys):
    fake_backend = MagicMock(name="fake_backend")
    fake_backend.synthesize_to_file.side_effect = RuntimeError("boom")

    with patch("core.speech.create_backend", return_value=fake_backend):
        engine = SpeechEngine(Config(tts_enabled=True))

    with patch("core.speech.platform.system", return_value="Windows"):
        engine.say("Hallo")  # darf nicht crashen

    assert "Jarvis: Hallo" in capsys.readouterr().out


# --- TTS-Streaming (ADR-048) ----------------------------------------------

class _FakeRawOutputStream:
    """sounddevice-Ersatz: sammelt geschriebene PCM-Bytes."""
    instances: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.written: list[bytes] = []
        _FakeRawOutputStream.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def write(self, data):
        self.written.append(bytes(data))


def _engine_with_streaming_backend(stream_chunks, **config_kwargs):
    backend = MagicMock(name="fake_backend")
    backend.pcm_sample_rate = 24_000
    if stream_chunks is None:
        del backend.stream_pcm  # Backend ohne Streaming-Faehigkeit
    elif isinstance(stream_chunks, Exception):
        backend.stream_pcm.side_effect = stream_chunks
    else:
        backend.stream_pcm.return_value = iter(stream_chunks)
    with patch("core.speech.create_backend", return_value=backend):
        engine = SpeechEngine(Config(tts_enabled=True, **config_kwargs))
    return engine, backend


def test_streaming_plays_chunks_and_skips_file_path():
    _FakeRawOutputStream.instances = []
    engine, backend = _engine_with_streaming_backend([b"\x01\x02\x03", b"\x04"])

    with patch("core.speech.platform.system", return_value="Windows"), patch.dict(
        sys.modules, {"sounddevice": MagicMock(RawOutputStream=_FakeRawOutputStream)}
    ):
        engine.say("Hallo")

    backend.synthesize_to_file.assert_not_called()  # kein Datei-Umweg
    out = _FakeRawOutputStream.instances[0]
    assert out.kwargs["samplerate"] == 24_000
    # int16-Ausrichtung: 3+1 Bytes werden als 2+2 geschrieben, dann Stille-Schwanz.
    assert out.written[0] == b"\x01\x02"
    assert out.written[1] == b"\x03\x04"
    assert len(out.written) == 3 and set(out.written[2]) == {0}


def test_streaming_disabled_by_config_uses_file_path():
    engine, backend = _engine_with_streaming_backend([b"\x01\x02"], tts_streaming=False)
    fake_winsound = MagicMock(SND_FILENAME=1)

    with patch("core.speech.platform.system", return_value="Windows"), patch.dict(
        sys.modules, {"winsound": fake_winsound}
    ):
        engine.say("Hallo")

    backend.stream_pcm.assert_not_called()
    backend.synthesize_to_file.assert_called_once()


def test_streaming_failure_falls_back_to_file_path():
    """Fehler VOR dem ersten Ton => lautlos auf den Datei-Weg (kein Crash,
    keine verlorene Antwort)."""
    engine, backend = _engine_with_streaming_backend(RuntimeError("api kaputt"))
    fake_winsound = MagicMock(SND_FILENAME=1)

    with patch("core.speech.platform.system", return_value="Windows"), patch.dict(
        sys.modules,
        {"sounddevice": MagicMock(RawOutputStream=_FakeRawOutputStream), "winsound": fake_winsound},
    ):
        engine.say("Hallo")

    backend.synthesize_to_file.assert_called_once()


def test_backend_without_stream_pcm_uses_file_path():
    engine, backend = _engine_with_streaming_backend(None)
    fake_winsound = MagicMock(SND_FILENAME=1)

    with patch("core.speech.platform.system", return_value="Windows"), patch.dict(
        sys.modules, {"winsound": fake_winsound}
    ):
        engine.say("Hallo")

    backend.synthesize_to_file.assert_called_once()
