"""Tests fuer core/news_reader.py + commands/news.py (ADR-042) - der Fetcher
ist injiziert, kein Netzwerk."""
from __future__ import annotations

import commands.news as news_commands
from core.models import Plan, Status
from core.news_reader import fetch_headlines

_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>tagesschau.de</title>
  <item><title>Meldung Eins</title><description>&lt;p&gt;Beschreibung eins.&lt;/p&gt;</description></item>
  <item><title>Meldung Zwei</title><description>Beschreibung zwei.</description></item>
  <item><title>Meldung Drei</title><description></description></item>
</channel></rss>"""

_RSS_B = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Quelle B</title>
  <item><title>B-Eins</title><description>b1</description></item>
  <item><title>B-Zwei</title><description>b2</description></item>
</channel></rss>"""

_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom-Quelle</title>
  <entry><title>Atom-Meldung</title><summary>Kurz.</summary></entry>
</feed>"""


def _fetcher(mapping):
    def fetch(url, timeout):
        result = mapping[url]
        if isinstance(result, Exception):
            raise result
        return result

    return fetch


def test_parses_rss_strips_html_and_names_source():
    heads = fetch_headlines(["a"], limit=4, fetcher=_fetcher({"a": _RSS}))
    assert [h.title for h in heads] == ["Meldung Eins", "Meldung Zwei", "Meldung Drei"]
    assert heads[0].summary == "Beschreibung eins."  # HTML-Tags entfernt
    assert heads[0].source == "tagesschau.de"


def test_parses_atom_fallback():
    heads = fetch_headlines(["a"], limit=2, fetcher=_fetcher({"a": _ATOM}))
    assert heads[0].title == "Atom-Meldung" and heads[0].source == "Atom-Quelle"


def test_round_robin_across_feeds_and_limit():
    heads = fetch_headlines(["a", "b"], limit=3, fetcher=_fetcher({"a": _RSS, "b": _RSS_B}))
    # reihum: erst je Feed die erste Meldung, dann die zweite - Limit greift.
    assert [h.title for h in heads] == ["Meldung Eins", "B-Eins", "Meldung Zwei"]


def test_broken_feed_is_skipped_not_fatal():
    heads = fetch_headlines(
        ["kaputt", "b"],
        limit=4,
        fetcher=_fetcher({"kaputt": RuntimeError("timeout"), "b": _RSS_B}),
    )
    assert [h.title for h in heads] == ["B-Eins", "B-Zwei"]


def test_command_formats_briefing_in_persona(monkeypatch):
    news_commands.configure(["a"], timeout_seconds=5.0)
    monkeypatch.setattr(
        news_commands,
        "fetch_headlines",
        lambda feeds, limit, timeout: fetch_headlines(feeds, limit=limit, fetcher=_fetcher({"a": _RSS})),
    )

    result = news_commands.GetNewsCommand().execute(Plan(intent="get_news"))

    assert result.status == Status.SUCCESS
    assert result.message.startswith("Die Lage, Sir")
    assert "1. Meldung Eins — Beschreibung eins. (tagesschau.de)" in result.message
    assert result.data["count"] == 3


def test_command_reports_failure_when_no_feed_answers(monkeypatch):
    news_commands.configure(["a"], timeout_seconds=5.0)
    monkeypatch.setattr(news_commands, "fetch_headlines", lambda *a, **k: [])

    result = news_commands.GetNewsCommand().execute(Plan(intent="get_news"))

    assert result.status == Status.FAILED
    assert "nicht abrufbar" in result.message


def test_topic_uses_google_news_search_feed(monkeypatch):
    """ADR-043: 'was gibt's Neues in Usingen?' -> Google-News-RSS-Suche
    statt der Standard-Feeds."""
    news_commands.configure(["standard-feed"], timeout_seconds=5.0)
    captured = {}

    def fake_fetch(feeds, limit, timeout):
        captured["feeds"] = feeds
        return fetch_headlines(["a"], limit=limit, fetcher=_fetcher({"a": _RSS}))

    monkeypatch.setattr(news_commands, "fetch_headlines", fake_fetch)

    result = news_commands.GetNewsCommand().execute(
        Plan(intent="get_news", parameters={"topic": "Usingen"})
    )

    assert result.status == Status.SUCCESS
    assert result.message.startswith("Die Lage zu «Usingen», Sir:")
    assert len(captured["feeds"]) == 1
    assert "news.google.com/rss/search" in captured["feeds"][0]
    assert "Usingen" in captured["feeds"][0]
    assert result.data["topic"] == "Usingen"


def test_google_news_url_encodes_topic():
    from core.news_reader import google_news_feed_url

    url = google_news_feed_url("Bad Homburg")
    assert "q=Bad%20Homburg" in url
    assert "hl=de" in url


def test_command_not_configured_raises():
    news_commands._feeds = None
    try:
        news_commands.GetNewsCommand().execute(Plan(intent="get_news"))
        assert False, "erwartete RuntimeError"
    except RuntimeError as e:
        assert "nicht konfiguriert" in str(e)
