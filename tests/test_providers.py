"""Tests für core/providers.py (v0.8 Multi-KI, ADR-029).

Beide SDK-Clients sind gemockt - kein echter API-Key, kein Netzwerk. Das
anthropic-SDK ist im Projekt bewusst NICHT installiert (lazy/optional,
ADR-029); die Claude-Tests injizieren deshalb ein Fake-Modul ueber
sys.modules, statt das echte Paket vorauszusetzen."""
from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.config import Config
from core.models import Message
from core.providers import (
    ClaudeProvider,
    OpenAIProvider,
    ProviderRouter,
    TaskType,
    build_named_provider,
    build_provider,
    build_router,
)


# --- OpenAIProvider -------------------------------------------------------

def _openai_provider_with_mock_client():
    """Erzeugt einen OpenAIProvider, dessen OpenAI-Client gemockt ist
    (kein echter Konstruktoraufruf ans SDK)."""
    with patch("openai.OpenAI") as mock_openai_cls:
        client = MagicMock()
        mock_openai_cls.return_value = client
        provider = OpenAIProvider(
            "test-key", "gpt-4o-mini", timeout=15.0, temperature=0.0, max_tokens=300
        )
    return provider, client


def _openai_response(content: str) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    return response


def test_openai_chat_builds_request_and_extracts_text():
    provider, client = _openai_provider_with_mock_client()
    client.chat.completions.create.return_value = _openai_response("  Hallo  ")

    text = provider.chat("SYS", [Message(role="user", content="hi")])

    assert text == "Hallo"  # gestrippt
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["temperature"] == 0.0
    assert kwargs["max_tokens"] == 300
    # system als erste Nachricht, dann die Turns:
    assert kwargs["messages"][0] == {"role": "system", "content": "SYS"}
    assert kwargs["messages"][1] == {"role": "user", "content": "hi"}
    # ohne json_mode kein response_format:
    assert "response_format" not in kwargs


def test_openai_chat_json_mode_sets_response_format():
    provider, client = _openai_provider_with_mock_client()
    client.chat.completions.create.return_value = _openai_response("{}")

    provider.chat("SYS", [Message(role="user", content="hi")], json_mode=True)

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}


# --- ClaudeProvider -------------------------------------------------------

def _install_fake_anthropic(monkeypatch, client: MagicMock):
    """Injiziert ein Fake-anthropic-Modul mit Anthropic-Klasse, deren
    Instanz der uebergebene Mock-Client ist."""
    fake = SimpleNamespace(Anthropic=MagicMock(return_value=client))
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    return fake


def _claude_response(*blocks) -> MagicMock:
    response = MagicMock()
    response.content = list(blocks)
    return response


def test_claude_chat_builds_request_and_extracts_text_blocks(monkeypatch):
    client = MagicMock()
    fake = _install_fake_anthropic(monkeypatch, client)
    # Ein Text-Block und ein Nicht-Text-Block: nur Text wird uebernommen.
    client.messages.create.return_value = _claude_response(
        MagicMock(type="text", text="Hallo "),
        MagicMock(type="thinking", text="ignored"),
        MagicMock(type="text", text="Welt"),
    )

    provider = ClaudeProvider("test-key", "claude-sonnet-5", timeout=15.0, max_tokens=300)
    text = provider.chat("SYS", [Message(role="user", content="hi")], json_mode=True)

    assert text == "Hallo Welt"
    # Anthropic-Konvention: system als eigener Parameter, thinking deaktiviert.
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-5"
    assert kwargs["system"] == "SYS"
    assert kwargs["max_tokens"] == 300
    assert kwargs["messages"] == [{"role": "user", "content": "hi"}]
    assert kwargs["thinking"] == {"type": "disabled"}
    # Sonnet 5 lehnt non-default temperature ab -> darf NICHT gesetzt sein.
    assert "temperature" not in kwargs
    # Phase 1: kein Structured-Output/Tool-Use, json_mode aendert den Request nicht.
    assert "response_format" not in kwargs


def test_claude_provider_raises_without_api_key(monkeypatch):
    _install_fake_anthropic(monkeypatch, MagicMock())
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        ClaudeProvider("", "claude-sonnet-5", timeout=15.0, max_tokens=300)


def test_claude_provider_raises_when_anthropic_not_installed(monkeypatch):
    # anthropic-Import soll fehlschlagen -> RuntimeError mit Hinweis.
    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(RuntimeError, match="anthropic"):
        ClaudeProvider("test-key", "claude-sonnet-5", timeout=15.0, max_tokens=300)


# --- build_provider -------------------------------------------------------

def test_build_provider_openai_is_default():
    config = Config(openai_api_key="test-key", ai_provider="openai")
    with patch("openai.OpenAI", return_value=MagicMock()):
        provider = build_provider(config)
    assert isinstance(provider, OpenAIProvider)


def test_build_provider_claude(monkeypatch):
    _install_fake_anthropic(monkeypatch, MagicMock())
    config = Config(
        ai_provider="claude", anthropic_api_key="test-key", claude_model="claude-sonnet-5"
    )
    provider = build_provider(config)
    assert isinstance(provider, ClaudeProvider)


def test_build_provider_unknown_raises():
    config = Config(ai_provider="gemini")
    with pytest.raises(RuntimeError, match="Unbekannter Provider"):
        build_provider(config)


def test_build_named_provider_unknown_raises():
    with pytest.raises(RuntimeError, match="Unbekannter Provider"):
        build_named_provider("gemini", Config())


# --- ProviderRouter (v0.8 Phase 2, ADR-030) ------------------------------

def test_router_uses_default_when_no_rule():
    r = ProviderRouter("openai", {})
    assert r.select(TaskType.PLANNING) == ("openai", "default")
    assert r.select(TaskType.GENERATION) == ("openai", "default")


def test_router_rule_wins_and_reports_reason():
    r = ProviderRouter("openai", {TaskType.GENERATION: "claude"})
    assert r.select(TaskType.GENERATION) == ("claude", "regel")
    # Nicht beregelter TaskType faellt weiter auf den Default:
    assert r.select(TaskType.PLANNING) == ("openai", "default")


def test_build_router_from_config_fields():
    cfg = Config(ai_provider="openai", answer_provider="claude")
    r = build_router(cfg)
    assert r.select(TaskType.GENERATION) == ("claude", "regel")
    assert r.select(TaskType.PLANNING) == ("openai", "default")


def test_build_router_without_fields_is_backward_compatible():
    """Ohne planning_provider/answer_provider routet jeder TaskType auf
    ai_provider - exakt das Phase-1-Verhalten."""
    cfg = Config(ai_provider="claude")
    r = build_router(cfg)
    assert r.select(TaskType.PLANNING) == ("claude", "default")
    assert r.select(TaskType.GENERATION) == ("claude", "default")
