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
from core.news_reader import fetch_headlines, google_news_feed_url

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

        # Orts-/Themen-News (ADR-043): "was gibt's Neues in Usingen?" ->
        # Google-News-RSS-Suche statt der Standard-Feeds.
        topic = str(plan.parameters.get("topic") or plan.target or "").strip()
        if topic:
            feeds = [google_news_feed_url(topic)]
            header = f"Die Lage zu «{topic}», Sir:"
        else:
            feeds = _require_feeds()
            header = "Die Lage, Sir — die wichtigsten Meldungen:"

        headlines = fetch_headlines(feeds, limit=limit, timeout=_timeout)
        if not headlines:
            detail = f" zu «{topic}»" if topic else ""
            return Result(
                status=Status.FAILED,
                message=f"Die Nachrichtenlage{detail} ist gerade nicht abrufbar, Sir.",
            )

        lines = []
        for i, h in enumerate(headlines, start=1):
            summary = f" — {h.summary}" if h.summary else ""
            lines.append(f"{i}. {h.title}{summary} ({h.source})")
        body = "\n".join(lines)
        return Result(
            status=Status.SUCCESS,
            message=f"{header}\n{body}",
            data={"count": len(headlines), "topic": topic or None},
        )


COMMANDS = [GetNewsCommand()]
