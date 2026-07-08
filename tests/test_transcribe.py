"""Tests fuer core/transcribe.py - der OpenAI-Client ist injiziert, es wird KEIN
echter API-Call gemacht. Audio bleibt Bytes (nichts wird gespeichert)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.transcribe import OpenAITranscriber


class _FakeTranscriptions:
    def __init__(self, text, captured):
        self._text = text
        self._captured = captured

    def create(self, model, file):
        self._captured["model"] = model
        self._captured["filename"] = getattr(file, "name", None)
        self._captured["data"] = file.read()
        return SimpleNamespace(text=self._text)


class _FakeClient:
    def __init__(self, text, captured):
        self.audio = SimpleNamespace(transcriptions=_FakeTranscriptions(text, captured))


def test_transcribe_returns_trimmed_text_and_passes_format_hint():
    captured: dict = {}
    client = _FakeClient(text="  erinnere mich morgen  ", captured=captured)
    transcriber = OpenAITranscriber(api_key="", model="whisper-1", client=client)

    result = transcriber.transcribe(b"OGGDATA", filename="voice.ogg")

    assert result == "erinnere mich morgen"       # getrimmt
    assert captured["model"] == "whisper-1"
    assert captured["filename"] == "voice.ogg"    # Endung -> Formaterkennung (OGG)
    assert captured["data"] == b"OGGDATA"          # exakt die Bytes, kein Datei-Umweg


def test_transcribe_empty_audio_raises():
    client = _FakeClient(text="egal", captured={})
    transcriber = OpenAITranscriber(api_key="", model="whisper-1", client=client)
    with pytest.raises(ValueError):
        transcriber.transcribe(b"")


def test_constructor_without_key_and_without_client_raises():
    # Ohne injizierten Client UND ohne Key kann kein echter Client gebaut werden.
    with pytest.raises(ValueError):
        OpenAITranscriber(api_key="", model="whisper-1")
