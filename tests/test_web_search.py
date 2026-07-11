"""Tests for core/web_search.py - no real network, deterministic HTML fixtures."""
from __future__ import annotations

from unittest.mock import patch

import pytest

import core.web_search as web_search


class _FakeHeaders:
    def get_content_charset(self):
        return "utf-8"


class _FakeResponse:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")
        self.headers = _FakeHeaders()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_decode_result_url_unwraps_duckduckgo_redirect():
    raw = "/l/?uddg=https%3A%2F%2Fexample.com%2Farticle&rut=abc"
    assert web_search._decode_result_url(raw) == "https://example.com/article"


def test_build_search_url_encodes_query_and_region():
    url = web_search._build_search_url("ki nachrichten")
    assert "lite.duckduckgo.com/lite/" in url
    assert "q=ki+nachrichten" in url
    assert "kl=de-de" in url


def test_parse_results_extracts_title_snippet_and_url():
    html = """
    <html><body>
      <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fa">Erster Treffer</a>
      <a class="result__snippet">Kurze Zusammenfassung eins.</a>
      <a class="result__a" href="https://example.org/b">Zweiter Treffer</a>
      <div class="result__snippet">Kurze Zusammenfassung zwei.</div>
    </body></html>
    """
    results = web_search._parse_results(html, max_results=5)

    assert len(results) == 2
    assert results[0].title == "Erster Treffer"
    assert results[0].url == "https://example.com/a"
    assert results[0].snippet == "Kurze Zusammenfassung eins."
    assert results[1].title == "Zweiter Treffer"
    assert results[1].url == "https://example.org/b"


def test_parse_results_deduplicates_and_limits():
    html = """
    <html><body>
      <a class="result__a" href="https://example.com/a">A1</a>
      <div class="result__snippet">eins</div>
      <a class="result__a" href="https://example.com/a">A2</a>
      <div class="result__snippet">doppelt</div>
      <a class="result__a" href="https://example.com/b">B</a>
      <div class="result__snippet">zwei</div>
    </body></html>
    """
    results = web_search._parse_results(html, max_results=1)

    assert len(results) == 1
    assert results[0].title == "A1"


def test_parse_results_filters_duckduckgo_ad_and_help_noise():
    html = """
    <html><body>
      <a class="result-link" href="https://duckduckgo.com/y.js?ad_provider=bing&click_metadata=abc">Anzeige</a>
      <div class="result-snippet">Werbung.</div>
      <a class="result-link" href="https://duckduckgo.com/duckduckgo-help-pages/company/ads-by-microsoft-on-duckduckgo-private-search/">more info</a>
      <div class="result-snippet">Hilfe.</div>
      <a class="result-link" href="https://www.idealo.de/preisvergleich/OffersOfProduct/201490239_-playstation-5-ps5-sony.html">Idealo PS5</a>
      <div class="result-snippet">Ab 609 Euro.</div>
    </body></html>
    """
    results = web_search._parse_results(html, max_results=5)

    assert len(results) == 1
    assert results[0].title == "Idealo PS5"
    assert "idealo" in results[0].url


def test_search_web_fetches_and_parses_results():
    html = """
    <html><body>
      <a class="result__a" href="https://example.com/a">Erster Treffer</a>
      <div class="result__snippet">Kurztext.</div>
    </body></html>
    """
    with patch("core.web_search.urlopen", return_value=_FakeResponse(html)):
        results = web_search.search_web("jarvis web", max_results=5, timeout_seconds=7.0)

    assert len(results) == 1
    assert results[0].title == "Erster Treffer"
    assert results[0].snippet == "Kurztext."


def test_search_web_raises_web_search_error_on_network_failure():
    with patch("core.web_search.urlopen", side_effect=OSError("timeout")):
        with pytest.raises(web_search.WebSearchError, match="nicht erreichbar"):
            web_search.search_web("jarvis web")


def test_search_web_retries_transient_connection_reset(monkeypatch):
    """Nutzungslauf-Befund 2026-07-10: WinError 10054 (Reset durch die
    Gegenseite) riss eine Sprach-Recherche ab - der zweite Versuch klappt
    praktisch immer. Fluechtige Abbrueche werden bis zu 2x wiederholt."""
    from urllib.error import URLError

    monkeypatch.setattr(web_search.time, "sleep", lambda s: None)  # kein Warten im Test
    html = '<a class="result__a" href="https://example.com/a">Treffer</a>'
    calls = {"n": 0}

    def flaky(request, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise URLError(ConnectionResetError(10054, "Verbindung wurde vom Remotehost geschlossen"))
        return _FakeResponse(html)

    with patch("core.web_search.urlopen", side_effect=flaky):
        results = web_search.search_web("jarvis web")

    assert calls["n"] == 2  # 1 Fehlversuch + 1 Erfolg
    assert results[0].title == "Treffer"


def test_search_web_gives_up_after_max_retries(monkeypatch):
    from urllib.error import URLError

    monkeypatch.setattr(web_search.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def always_reset(request, timeout):
        calls["n"] += 1
        raise URLError(ConnectionResetError(10054, "reset"))

    with patch("core.web_search.urlopen", side_effect=always_reset):
        with pytest.raises(web_search.WebSearchError, match="nicht erreichbar"):
            web_search.search_web("jarvis web")

    assert calls["n"] == 3  # genau _RETRY_ATTEMPTS, dann ehrlich scheitern


def test_search_web_does_not_retry_non_transient_errors():
    """Offline/DNS (kein Reset): sofort ehrlich scheitern - kein 3x-Warten."""
    calls = {"n": 0}

    def offline(request, timeout):
        calls["n"] += 1
        raise OSError("getaddrinfo failed")

    with patch("core.web_search.urlopen", side_effect=offline):
        with pytest.raises(web_search.WebSearchError, match="nicht erreichbar"):
            web_search.search_web("jarvis web")

    assert calls["n"] == 1  # kein Retry


def test_search_web_raises_on_duckduckgo_challenge_page():
    html = """
    <html><body>
      <div class="anomaly-modal__title">Unfortunately, bots use DuckDuckGo too.</div>
      <form action="//duckduckgo.com/anomaly.js"></form>
    </body></html>
    """
    with patch("core.web_search.urlopen", return_value=_FakeResponse(html)):
        with pytest.raises(web_search.WebSearchError, match="Bot-/Captcha-Seite"):
            web_search.search_web("jarvis web")
