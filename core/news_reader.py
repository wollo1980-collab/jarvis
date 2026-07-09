"""
News-Briefing (ADR-042) - liest Schlagzeilen aus RSS-Feeds. Read-only,
stdlib-only (urllib + xml.etree): kein API-Key, kein Scraping, kein neues
Paket. RSS ist der seit Jahrzehnten stabile, maschinenlesbare Weg an
Schlagzeilen - genau das, was eine Websuche fuer "was ist heute los?"
NICHT liefert (Suchtreffer sind Portale, keine Meldungen;
Nutzungslauf-Befund 2026-07-09).

Der Fetcher ist injizierbar - Tests laufen ohne Netzwerk.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger("jarvis.news")


def google_news_feed_url(topic: str) -> str:
    """RSS-Suche von Google News - liefert echte Schlagzeilen zu einem Ort
    oder Thema ("Usingen", "Bitcoin") im selben RSS-Format wie die
    Standard-Feeds (ADR-043-Erweiterung von ADR-042)."""
    query = urllib.parse.quote(topic.strip())
    return f"https://news.google.com/rss/search?q={query}&hl=de&gl=DE&ceid=DE:de"

_TAG_RE = re.compile(r"<[^>]+>")
_MAX_SUMMARY_CHARS = 200

# Atom-Namespace (tagesschau & Co. liefern RSS 2.0; Atom als Fallback).
_ATOM_NS = "{http://www.w3.org/2005/Atom}"


@dataclass
class Headline:
    title: str
    summary: str
    source: str


def _default_fetcher(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Jarvis-News/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _clean(text: Optional[str]) -> str:
    """HTML-Tags raus, Leerraum normalisieren, Laenge deckeln."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > _MAX_SUMMARY_CHARS:
        text = text[:_MAX_SUMMARY_CHARS].rsplit(" ", 1)[0] + " …"
    return text


def _dedupe_summary(title: str, summary: str) -> str:
    """tagesschau & Co. spiegeln bei manchen Meldungen den Titel 1:1 in die
    description - vorgetragen klingt das doppelt ("Merz verteidigt ... — Merz
    verteidigt ...", Nutzungslauf-Befund 2026-07-09). Redundanz verwerfen."""
    if not summary:
        return ""
    t = title.casefold().strip()
    s = summary.casefold().rstrip(" .…").strip()
    if s and (s in t or t in s):
        return ""
    return summary


def _parse_feed(data: bytes) -> tuple[str, list[Headline]]:
    """Parst RSS 2.0 (channel/item) oder Atom (feed/entry)."""
    root = ET.fromstring(data)
    headlines: list[Headline] = []

    channel = root.find("channel")
    if channel is not None:  # RSS 2.0
        source = _clean(channel.findtext("title")) or "Unbekannte Quelle"
        # Google-News-Feeds sind unordentlich (Nutzungslauf-Befund 2026-07-09):
        # die "description" ist eine HTML-Linkliste verwandter Artikel (nach
        # Tag-Strip: Wort-Salat), und der Titel traegt den Verlag hinten dran
        # ("Schlagzeile - Verlag"). Deshalb: description verwerfen, Verlag
        # als Quelle abtrennen.
        is_google_news = "google news" in source.lower()
        if not is_google_news:
            # Feed-Titel tragen oft einen Werbeslogan ("tagesschau.de - die
            # erste Adresse fuer ..."), der sonst an jeder Meldung klebt.
            source = source.split(" - ")[0].strip() or source
        for item in channel.findall("item"):
            title = _clean(item.findtext("title"))
            if not title:
                continue
            if is_google_news:
                head, sep, publisher = title.rpartition(" - ")
                item_source = publisher if sep and publisher else source
                headlines.append(Headline(title=head or title, summary="", source=item_source))
            else:
                summary = _dedupe_summary(title, _clean(item.findtext("description")))
                headlines.append(Headline(title=title, summary=summary, source=source))
        return source, headlines

    if root.tag == f"{_ATOM_NS}feed":  # Atom
        source = _clean(root.findtext(f"{_ATOM_NS}title")) or "Unbekannte Quelle"
        for entry in root.findall(f"{_ATOM_NS}entry"):
            title = _clean(entry.findtext(f"{_ATOM_NS}title"))
            if title:
                summary = _dedupe_summary(title, _clean(entry.findtext(f"{_ATOM_NS}summary")))
                headlines.append(Headline(title=title, summary=summary, source=source))
        return source, headlines

    return "Unbekannte Quelle", []


def fetch_headlines(
    feeds: list[str],
    limit: int = 4,
    timeout: float = 10.0,
    fetcher: Callable[[str, float], bytes] = _default_fetcher,
) -> list[Headline]:
    """Holt die Top-Schlagzeilen ueber alle konfigurierten Feeds. Ein kaputter
    Feed bricht nicht das Briefing - er wird geloggt und uebersprungen; die
    Meldungen werden reihum ueber die Feeds verteilt (erst je Feed die erste,
    dann je Feed die zweite, ...), damit eine Quelle nicht alles dominiert."""
    per_feed: list[list[Headline]] = []
    for url in feeds:
        try:
            _source, headlines = _parse_feed(fetcher(url, timeout))
            if headlines:
                per_feed.append(headlines)
        except Exception as e:  # noqa: BLE001 - ein Feed darf nie alles reissen
            logger.warning("News-Feed nicht lesbar (%s): %s", url, e)

    result: list[Headline] = []
    round_index = 0
    while len(result) < limit and any(round_index < len(h) for h in per_feed):
        for headlines in per_feed:
            if round_index < len(headlines) and len(result) < limit:
                result.append(headlines[round_index])
        round_index += 1
    return result
