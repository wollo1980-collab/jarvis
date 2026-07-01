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
