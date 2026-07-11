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
    # Einzige Quelle: einmal im Kopf, nicht an jeder Meldung (Ballast-Befund).
    assert "(Quelle: tagesschau.de)" in result.message
    # Nur Ueberschriften, keine Anrisse (Nutzungslauf-Befund 2026-07-10):
    # Titel+Summary sprengten den Sprech-Deckel, das Briefing brach ab.
    assert "1. Meldung Eins\n" in result.message
    assert "Beschreibung eins" not in result.message
    assert result.data["count"] == 3


def test_command_reports_failure_when_no_feed_answers(monkeypatch):
    news_commands.configure(["a"], timeout_seconds=5.0)
    monkeypatch.setattr(news_commands, "fetch_headlines", lambda *a, **k: [])

    result = news_commands.GetNewsCommand().execute(Plan(intent="get_news"))

    assert result.status == Status.FAILED
    assert "nicht abrufbar" in result.message


def test_topic_uses_google_news_search_feed(monkeypatch):
    """ADR-043: 'was gibt's Neues in Musterstadt?' -> Google-News-RSS-Suche
    statt der Standard-Feeds."""
    news_commands.configure(["standard-feed"], timeout_seconds=5.0)
    captured = {}

    def fake_fetch(feeds, limit, timeout):
        captured["feeds"] = feeds
        return fetch_headlines(["a"], limit=limit, fetcher=_fetcher({"a": _RSS}))

    monkeypatch.setattr(news_commands, "fetch_headlines", fake_fetch)

    result = news_commands.GetNewsCommand().execute(
        Plan(intent="get_news", parameters={"topic": "Musterstadt"})
    )

    assert result.status == Status.SUCCESS
    assert result.message.startswith("Die Lage zu «Musterstadt», Sir")
    assert len(captured["feeds"]) == 1
    assert "news.google.com/rss/search" in captured["feeds"][0]
    assert "Musterstadt" in captured["feeds"][0]
    assert result.data["topic"] == "Musterstadt"


def test_google_news_url_encodes_topic():
    from core.news_reader import google_news_feed_url

    url = google_news_feed_url("Bad Homburg")
    assert "q=Bad%20Homburg" in url
    assert "hl=de" in url


_GOOGLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>"Musterstadt" - Google News</title>
  <item><title>Stadtfest abgesagt - Musterstadt Anzeiger</title><description>&lt;ol&gt;&lt;li&gt;&lt;a href="x"&gt;Link-Salat&lt;/a&gt;&lt;/li&gt;&lt;/ol&gt;</description></item>
  <item><title>Luftqualit\xc3\xa4t in Musterstadt: aktuelle Messwerte - wetter.de</title><description>junk</description></item>
  <item><title>Neuer B\xc3\xbcrgermeister vereidigt - FNP</title><description>junk</description></item>
</channel></rss>"""


def test_google_news_items_use_clean_title_and_publisher():
    """Nutzungslauf-Befund 2026-07-09: Google-Descriptions sind Link-Salat ->
    verwerfen; der Verlag steckt im Titel -> als Quelle abtrennen."""
    heads = fetch_headlines(["g"], limit=4, fetcher=_fetcher({"g": _GOOGLE_RSS}))
    assert heads[0].title == "Stadtfest abgesagt"
    assert heads[0].source == "Musterstadt Anzeiger"
    assert heads[0].summary == ""  # kein Link-Salat
    assert "Link-Salat" not in heads[0].title


def test_topic_search_filters_autogenerated_junk(monkeypatch):
    news_commands.configure(["standard"], timeout_seconds=5.0)
    monkeypatch.setattr(
        news_commands,
        "fetch_headlines",
        lambda feeds, limit, timeout: fetch_headlines(["g"], limit=limit, fetcher=_fetcher({"g": _GOOGLE_RSS})),
    )

    result = news_commands.GetNewsCommand().execute(
        Plan(intent="get_news", parameters={"topic": "Musterstadt"})
    )

    assert "Stadtfest abgesagt" in result.message
    assert "Bürgermeister" in result.message
    assert "Luftqualität" not in result.message  # Fuellstoff ausgesiebt


_RSS_VERBOSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>tagesschau.de - die erste Adresse f\xc3\xbcr Nachrichten und Information</title>
  <item><title>Echte Meldung</title><description>Mit eigener Zusammenfassung.</description></item>
  <item><title>Livestream: Die Nachrichten auf tagesschau24</title><description>Verfolgen Sie das Programm hier.</description></item>
  <item><title>Merz verteidigt Reformvorhaben</title><description>Merz verteidigt Reformvorhaben</description></item>
</channel></rss>"""


def test_feed_title_slogan_is_trimmed_and_duplicate_summary_dropped():
    """Nutzungslauf-Befunde 2026-07-09: (1) Feed-Titel tragen Werbeslogans
    ("tagesschau.de - die erste Adresse fuer ...") - nur der Name bleibt;
    (2) manche Meldungen spiegeln den Titel in die description - die
    Dublette wird verworfen."""
    heads = fetch_headlines(["v"], limit=4, fetcher=_fetcher({"v": _RSS_VERBOSE}))
    assert heads[0].source == "tagesschau.de"
    assert heads[0].summary == "Mit eigener Zusammenfassung."
    # Livestream-Promo (Item 2 im Feed) ist bereits an der Quelle gefiltert
    # (PO-Reibung 2026-07-11) - deshalb ist "Merz" jetzt Index 1, nicht 2.
    assert [h.title for h in heads] == ["Echte Meldung", "Merz verteidigt Reformvorhaben"]
    assert heads[1].summary == ""  # Titel-Dublette weg


def test_fetch_headlines_filters_junk_at_source():
    """PO-Reibung 2026-07-11 ('Livestream passt nicht'): Programm-Promo und
    Fuellstoff (Luftqualitaet u. a.) fliegen schon in fetch_headlines raus -
    damit AUCH das Dashboard-Panel 'Die Lage' (news_summary) sauber ist, nicht
    nur das gesprochene Briefing."""
    heads = fetch_headlines(["v"], limit=4, fetcher=_fetcher({"v": _RSS_VERBOSE}))
    assert all("Livestream" not in h.title for h in heads)
    assert any(h.title == "Echte Meldung" for h in heads)


def test_standard_briefing_filters_livestream_promo(monkeypatch):
    """Programm-Promo ("Livestream: ...") ist keine Meldung - fliegt auch
    aus dem Standard-Briefing raus."""
    news_commands.configure(["v"], timeout_seconds=5.0)
    monkeypatch.setattr(
        news_commands,
        "fetch_headlines",
        lambda feeds, limit, timeout: fetch_headlines(feeds, limit=limit, fetcher=_fetcher({"v": _RSS_VERBOSE})),
    )

    result = news_commands.GetNewsCommand().execute(Plan(intent="get_news"))

    assert result.status == Status.SUCCESS
    assert "Livestream" not in result.message
    assert "Echte Meldung" in result.message
    assert "Merz verteidigt Reformvorhaben" in result.message
    assert result.data["count"] == 2


def test_mixed_sources_keep_per_item_attribution(monkeypatch):
    """Bei mehreren Quellen bleibt die Zuordnung an der Meldung (Belege-
    Prinzip) - nur die Einzelquelle wandert in den Kopf."""
    news_commands.configure(["a", "b"], timeout_seconds=5.0)
    monkeypatch.setattr(
        news_commands,
        "fetch_headlines",
        lambda feeds, limit, timeout: fetch_headlines(feeds, limit=limit, fetcher=_fetcher({"a": _RSS, "b": _RSS_B})),
    )

    result = news_commands.GetNewsCommand().execute(Plan(intent="get_news"))

    assert "(tagesschau.de)" in result.message
    assert "(Quelle B)" in result.message
    assert "(Quelle:" not in result.message  # kein Kopf-Vermerk bei Mischung


def test_command_not_configured_raises():
    news_commands._feeds = None
    try:
        news_commands.GetNewsCommand().execute(Plan(intent="get_news"))
        assert False, "erwartete RuntimeError"
    except RuntimeError as e:
        assert "nicht konfiguriert" in str(e)
