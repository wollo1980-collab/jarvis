"""Sicherheits-Invarianten des LLM-Kerns (ADR-061).

I1 - Secrets nie im LLM-Kontext: kein Key/Token aus der Config darf je in einen
an das LLM gesendeten System-Prompt oder eine Message gelangen. Regression
gegen die #1-Klasse an Agenten-Vorfaellen (Prompt-Injection -> Credential-Leak).
"""
from __future__ import annotations

import json
from unittest.mock import patch

from core.ai import AIEngine
from core.config import Config
from core.tool_schemas import build_tool_schemas

_SECRETS = {
    "openai_api_key": "sk-FAKEopenaiSECRETkey000111222333444555",  # release-scan: ok (erfundenes Beispiel-Secret)
    "elevenlabs_api_key": "sk_FAKEelevenlabsSECRET0001112223334",
    "spotify_client_secret": "FAKEspotifyClientSecret0001112223334",
    "spotify_refresh_token": "FAKEspotifyRefreshToken0001112223334",
    "anthropic_api_key": "sk-ant-FAKEanthropicSECRET00011122233",  # release-scan: ok (erfundenes Beispiel-Secret)
}


def test_no_config_secret_reaches_the_llm_context():
    """I1: get_plan/answer/choose_tool senden NIE ein Config-Secret ans LLM.
    Wir kapern die Provider-Aufrufe und pruefen den kompletten gesendeten
    Kontext (System-Prompt + alle Message-Inhalte)."""
    config = Config(model="gpt-4o-mini", owner_name="Martin", **_SECRETS)
    ai = AIEngine(config)

    seen: list[str] = []

    def cap_chat(system, messages, **_kw):
        seen.append(system)
        seen.extend(m.content for m in messages)
        return '{"intent": "chat", "target": null, "parameters": {}, "confidence": 1.0}'

    def cap_tools(system, messages, tools, **_kw):
        seen.append(system)
        seen.extend(m.content for m in messages)
        seen.append(json.dumps(tools))  # auch die Werkzeug-Schemas pruefen
        return []

    with patch.object(ai.provider, "chat", side_effect=cap_chat), \
         patch.object(ai.provider, "choose_tool", side_effect=cap_tools):
        ai.get_plan("wie wird das wetter?", [])
        ai.answer("erzaehl mir was", [], long_term_summary="trinkt seinen Kaffee schwarz")
        ai.choose_tool("wetter morgen", [], build_tool_schemas())

    blob = "\n".join(seen)
    assert blob  # es wurde ueberhaupt Kontext gesendet
    for name, secret in _SECRETS.items():
        assert secret not in blob, f"Secret {name} ist in den LLM-Kontext geleakt!"


def test_tool_schemas_carry_no_secrets():
    """I1: die Werkzeug-Schemas stammen aus der Command-Registry (Namen +
    Beschreibungen) - nie aus der Config, also nie mit Secrets."""
    blob = json.dumps(build_tool_schemas())
    for secret in _SECRETS.values():
        assert secret not in blob
