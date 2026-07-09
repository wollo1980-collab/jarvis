"""Tests für core/tts/factory.py::create_backend - der zentrale
Umschalter zwischen Piper/OpenAI/ElevenLabs/Kokoro. Muss bei jedem
Fehler (fehlende Bibliothek, fehlender Key, unbekannter Name) None
zurückgeben statt zu crashen - siehe ADR-008."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.config import Config
from core.tts.factory import create_backend


def test_creates_piper_backend_by_default(tmp_path):
    model_path = tmp_path / "voice.onnx"
    model_path.write_text("dummy")
    config = Config(tts_backend="piper", tts_model_path=str(model_path))

    fake_backend = MagicMock()
    with patch("core.tts.piper_backend.PiperBackend", return_value=fake_backend) as cls:
        result = create_backend(config)

    cls.assert_called_once_with(str(model_path))
    assert result is fake_backend


def test_returns_none_when_piper_model_missing(tmp_path):
    config = Config(tts_backend="piper", tts_model_path=str(tmp_path / "fehlt.onnx"))
    assert create_backend(config) is None


def test_creates_openai_backend_when_configured():
    config = Config(
        tts_backend="openai",
        openai_api_key="test-key",
        openai_tts_model="tts-1",
        openai_tts_voice="onyx",
    )
    fake_backend = MagicMock()
    with patch(
        "core.tts.openai_backend.OpenAITTSBackend", return_value=fake_backend
    ) as cls:
        result = create_backend(config)

    cls.assert_called_once_with(
        api_key="test-key", model="tts-1", voice="onyx", timeout=config.timeout, speed=1.0
    )
    assert result is fake_backend


def test_returns_none_when_openai_key_missing():
    config = Config(tts_backend="openai", openai_api_key="")
    assert create_backend(config) is None


def test_returns_none_when_elevenlabs_credentials_missing():
    config = Config(tts_backend="elevenlabs", elevenlabs_api_key="", elevenlabs_voice_id="")
    assert create_backend(config) is None


def test_returns_none_when_kokoro_library_missing():
    config = Config(tts_backend="kokoro")
    # kokoro-onnx ist in der Testumgebung nicht installiert - genau
    # dieser Fall (optionale Abhängigkeit fehlt) soll None liefern.
    assert create_backend(config) is None


def test_returns_none_for_unknown_backend_name():
    config = Config(tts_backend="does_not_exist")
    assert create_backend(config) is None
