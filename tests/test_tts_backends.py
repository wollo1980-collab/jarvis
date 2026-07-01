"""Tests für die einzelnen TTSBackend-Implementierungen (ADR-008).
Alle externen Bibliotheken/Netzwerkaufrufe gemockt - keine echten
API-Keys, kein echtes Modell, kein Netzwerk nötig."""
from __future__ import annotations

import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.tts.openai_backend import OpenAITTSBackend
from core.tts.piper_backend import PiperBackend


# --- Piper -------------------------------------------------------------

def test_piper_backend_raises_when_library_missing(tmp_path):
    model_path = tmp_path / "voice.onnx"
    model_path.write_text("dummy")
    with patch("core.tts.piper_backend.PiperVoice", None):
        with pytest.raises(RuntimeError):
            PiperBackend(str(model_path))


def test_piper_backend_raises_when_model_missing(tmp_path):
    fake_piper = MagicMock()
    with patch("core.tts.piper_backend.PiperVoice", fake_piper):
        with pytest.raises(RuntimeError):
            PiperBackend(str(tmp_path / "fehlt.onnx"))
    fake_piper.load.assert_not_called()


def test_piper_backend_synthesize_writes_wav(tmp_path):
    model_path = tmp_path / "voice.onnx"
    model_path.write_text("dummy")
    output_path = tmp_path / "out.wav"

    def fake_synthesize(text, wav_file):
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x00\x00")

    fake_voice = MagicMock()
    fake_voice.synthesize_wav.side_effect = fake_synthesize
    fake_piper = MagicMock(load=MagicMock(return_value=fake_voice))

    with patch("core.tts.piper_backend.PiperVoice", fake_piper):
        backend = PiperBackend(str(model_path))
        backend.synthesize_to_file("Hallo", str(output_path))

    fake_piper.load.assert_called_once_with(str(model_path))
    assert output_path.exists()


# --- OpenAI --------------------------------------------------------------

def test_openai_backend_raises_without_api_key():
    with pytest.raises(RuntimeError):
        OpenAITTSBackend(api_key="")


def test_openai_backend_calls_speech_api(tmp_path):
    output_path = tmp_path / "out.wav"
    backend = OpenAITTSBackend(api_key="test-key", model="tts-1", voice="onyx")
    fake_response = MagicMock()

    with patch.object(
        backend.client.audio.speech, "create", return_value=fake_response
    ) as create:
        backend.synthesize_to_file("Hallo", str(output_path))

    create.assert_called_once_with(
        model="tts-1", voice="onyx", input="Hallo", response_format="wav"
    )
    fake_response.stream_to_file.assert_called_once_with(str(output_path))


# --- ElevenLabs ------------------------------------------------------------

def test_elevenlabs_backend_raises_when_library_missing():
    from core.tts.elevenlabs_backend import ElevenLabsBackend

    with patch("core.tts.elevenlabs_backend.ElevenLabs", None):
        with pytest.raises(RuntimeError):
            ElevenLabsBackend(api_key="key", voice_id="voice")


def test_elevenlabs_backend_raises_without_credentials():
    from core.tts.elevenlabs_backend import ElevenLabsBackend

    with patch("core.tts.elevenlabs_backend.ElevenLabs", MagicMock()):
        with pytest.raises(RuntimeError):
            ElevenLabsBackend(api_key="", voice_id="")


def test_elevenlabs_backend_wraps_pcm_into_wav(tmp_path):
    from core.tts.elevenlabs_backend import ElevenLabsBackend

    output_path = tmp_path / "out.wav"
    fake_client_cls = MagicMock()
    fake_client = fake_client_cls.return_value
    fake_client.text_to_speech.convert.return_value = iter([b"\x00\x00", b"\x01\x00"])

    with patch("core.tts.elevenlabs_backend.ElevenLabs", fake_client_cls):
        backend = ElevenLabsBackend(api_key="key", voice_id="voice-id")
        backend.synthesize_to_file("Hallo", str(output_path))

    fake_client.text_to_speech.convert.assert_called_once()
    with wave.open(str(output_path), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 24000
        assert wav_file.readframes(wav_file.getnframes()) == b"\x00\x00\x01\x00"


# --- Kokoro ---------------------------------------------------------------

def test_kokoro_backend_raises_when_library_missing(tmp_path):
    from core.tts.kokoro_backend import KokoroBackend

    model_path = tmp_path / "model.onnx"
    voices_path = tmp_path / "voices.bin"
    model_path.write_text("dummy")
    voices_path.write_text("dummy")

    with patch("core.tts.kokoro_backend.Kokoro", None):
        with pytest.raises(RuntimeError):
            KokoroBackend(str(model_path), str(voices_path))


def test_kokoro_backend_raises_when_model_files_missing(tmp_path):
    from core.tts.kokoro_backend import KokoroBackend

    with patch("core.tts.kokoro_backend.Kokoro", MagicMock()):
        with pytest.raises(RuntimeError):
            KokoroBackend(
                str(tmp_path / "fehlt.onnx"), str(tmp_path / "fehlt.bin")
            )


def test_kokoro_backend_writes_wav(tmp_path):
    from core.tts.kokoro_backend import KokoroBackend

    model_path = tmp_path / "model.onnx"
    voices_path = tmp_path / "voices.bin"
    model_path.write_text("dummy")
    voices_path.write_text("dummy")
    output_path = tmp_path / "out.wav"

    fake_kokoro_instance = MagicMock()
    fake_kokoro_instance.create.return_value = (
        np.array([0.0, 0.5, -0.5], dtype=np.float32),
        24000,
    )
    fake_kokoro_cls = MagicMock(return_value=fake_kokoro_instance)

    with patch("core.tts.kokoro_backend.Kokoro", fake_kokoro_cls):
        backend = KokoroBackend(str(model_path), str(voices_path))
        backend.synthesize_to_file("Hallo", str(output_path))

    fake_kokoro_instance.create.assert_called_once()
    with wave.open(str(output_path), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
