"""
News-Briefing-Command (ADR-042) - "Was gibt's Neues?" liefert die Top-
Schlagzeilen aus konfigurierten RSS-Feeds (core/news_reader.py), im
Butler-Ton vorgetragen und dank Kuerze auch gesprochen angenehm
(Sprechfassung des PTT-Kanals greift zusaetzlich).

Abgrenzung: get_news = aktuelle Schlagzeilen (RSS, deterministisch);
search_web = explizite Recherche zu einem Thema. Read-only, Stufe 0.
"""
from __future__ import annotations

from typing import Optional

from core.models import Plan, Result, Status
from core.news_reader import JUNK_HEADLINE_RE, fetch_headlines, google_news_feed_url

# Fuellstoff-Filter kanonisch in core/news_reader.py (dort greift er jetzt
# schon beim Fetch, fuer Dashboard UND gesprochene News). Hier als zweite,
# guenstige Sicherung belassen - falls je ein Konsument ungefilterte
# Headlines liefert.
_JUNK_RE = JUNK_HEADLINE_RE

_feeds: Optional[list] = None
_timeout: float = 10.0

_DEFAULT_LIMIT = 4
_MAX_LIMIT = 8


def configure(feeds: list, timeout_seconds: float = 10.0) -> None:
    """Von main.py/jarvis_runtime.py beim Start aufgerufen (Feeds aus Config)."""
    global _feeds, _timeout
    _feeds = list(feeds)
    _timeout = timeout_seconds


def _require_feeds() -> list:
    if not _feeds:
        raise RuntimeError(
            "News-Briefing nicht konfiguriert - commands.news.configure() "
            "muss beim Start aufgerufen werden (siehe main.py)."
        )
    return _feeds


class GetNewsCommand:
    name = "get_news"
    description = (
        "Traegt die aktuellen Top-Schlagzeilen aus den konfigurierten "
        "Nachrichten-Feeds vor (z. B. 'was gibt es Neues?', 'gibt es "
        "Nachrichten?', 'was ist heute in der Welt los?'). Read-only."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        try:
            limit = min(int(plan.parameters.get("count", _DEFAULT_LIMIT)), _MAX_LIMIT)
        except (TypeError, ValueError):
            limit = _DEFAULT_LIMIT

        # Orts-/Themen-News (ADR-043): "was gibt's Neues in Berlin?" ->
        # Google-News-RSS-Suche statt der Standard-Feeds.
        topic = str(plan.parameters.get("topic") or plan.target or "").strip()
        feeds = [google_news_feed_url(topic)] if topic else _require_feeds()

        # Mehr holen und Fuellstoff aussieben (Wetter-Junk, Livestream-Promo) -
        # lieber zwei echte Meldungen als vier ueber Feinstaub.
        headlines = fetch_headlines(feeds, limit=limit * 3, timeout=_timeout)
        headlines = [h for h in headlines if not _JUNK_RE.search(h.title)][:limit]
        if not headlines:
            detail = f" zu «{topic}»" if topic else ""
            return Result(
                status=Status.FAILED,
                message=f"Die Nachrichtenlage{detail} ist gerade nicht abrufbar, Sir.",
            )

        # Eine einzige Quelle wird nur einmal im Kopf genannt statt an jeder
        # Meldung (Nutzungslauf-Befund 2026-07-09: "(tagesschau.de - ...)"
        # hinter jeder Zeile ist Ballast - gesprochen frisst er den
        # Laengen-Deckel auf, Meldungen fallen hinten runter).
        sources = {h.source for h in headlines}
        single_source = sources.pop() if len(sources) == 1 else None
        src_note = f" (Quelle: {single_source})" if single_source else ""
        if topic:
            header = f"Die Lage zu «{topic}», Sir{src_note}:"
        else:
            header = f"Die Lage, Sir — die wichtigsten Meldungen{src_note}:"

        # Nur die Ueberschriften, keine Anrisse (Nutzungslauf-Befund
        # 2026-07-10): Titel + 200-Zeichen-Summary je Meldung sprengten den
        # Sprech-Deckel - vorgelesen brach das Briefing mitten in Meldung 2
        # ab. Die Anrisse sind meist Teaser ohne Mehrwert; wer mehr will,
        # fragt nach ("erzaehl mir mehr zu ..." -> search_web).
        lines = []
        for i, h in enumerate(headlines, start=1):
            source = "" if single_source else f" ({h.source})"
            lines.append(f"{i}. {h.title}{source}")
        body = "\n".join(lines)
        return Result(
            status=Status.SUCCESS,
            message=f"{header}\n{body}",
            data={"count": len(headlines), "topic": topic or None},
        )


COMMANDS = [GetNewsCommand()]
