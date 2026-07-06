"""Tests for commands/web.py - search backend and AI summary are injected."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import commands.web as web_commands
from core.models import Plan, Status
from core.web_search import SearchResult, WebSearchError


def test_search_web_needs_query():
    web_commands.configure(MagicMock())
    result = web_commands.SearchWebCommand().execute(Plan(intent="search_web", target=None))

    assert result.status == Status.NEEDS_CLARIFICATION


def test_search_web_returns_summary_and_sources():
    ai = MagicMock()
    ai.answer.return_value = "Kurzueberblick."

    def fake_searcher(query: str, max_results: int, timeout_seconds: float) -> list[SearchResult]:
        assert query == "aktuelle KI Nachrichten"
        assert max_results == 5
        assert timeout_seconds == 12.0
        return [
            SearchResult("Treffer A", "https://example.com/a", "Snippet A"),
            SearchResult("Treffer B", "https://example.com/b", "Snippet B"),
        ]

    web_commands.configure(ai, timeout_seconds=12.0, searcher=fake_searcher)
    result = web_commands.SearchWebCommand().execute(
        Plan(intent="search_web", target="aktuelle KI Nachrichten")
    )

    assert result.status == Status.SUCCESS
    assert "Kurzueberblick." in result.message
    assert "Quellen:" in result.message
    assert "https://example.com/a" in result.message
    assert result.data["query"] == "aktuelle KI Nachrichten"
    assert len(result.data["results"]) == 2
    ai.answer.assert_called_once()


def test_search_web_price_question_expands_query_when_target_is_too_generic():
    ai = MagicMock()
    ai.answer.return_value = "Aktuell ab 414,90 Euro."

    def fake_searcher(query: str, max_results: int, timeout_seconds: float) -> list[SearchResult]:
        assert query == "Switch 2 Preis"
        return [
            SearchResult("Idealo Switch 2", "https://example.com/switch2", "Ab 414,90 Euro."),
        ]

    web_commands.configure(ai, searcher=fake_searcher)
    result = web_commands.SearchWebCommand().execute(
        Plan(
            intent="search_web",
            target="Switch 2",
            raw_input="Wie teuer ist die Switch 2 aktuell?",
        )
    )

    assert result.status == Status.SUCCESS
    assert result.data["query"] == "Switch 2 Preis"
    prompt = ai.answer.call_args.args[0]
    assert "klarsten aktuellen Preis" in prompt


def test_search_web_returns_success_when_no_results_found():
    ai = MagicMock()
    web_commands.configure(ai, searcher=lambda query, max_results, timeout_seconds: [])

    result = web_commands.SearchWebCommand().execute(
        Plan(intent="search_web", target="sehr spezieller suchbegriff")
    )

    assert result.status == Status.SUCCESS
    assert "keine klaren Treffer" in result.message
    ai.answer.assert_not_called()


def test_search_web_reports_fetch_error():
    ai = MagicMock()

    def failing_searcher(query: str, max_results: int, timeout_seconds: float) -> list[SearchResult]:
        raise WebSearchError("timeout")

    web_commands.configure(ai, searcher=failing_searcher)
    result = web_commands.SearchWebCommand().execute(
        Plan(intent="search_web", target="aktuelle KI Nachrichten")
    )

    assert result.status == Status.FAILED
    assert "Websuche" in result.message


def test_search_web_not_configured_raises(monkeypatch):
    monkeypatch.setattr(web_commands, "_ai_engine", None)
    with pytest.raises(RuntimeError, match="configure"):
        web_commands.SearchWebCommand().execute(
            Plan(intent="search_web", target="aktuelle KI Nachrichten")
        )
