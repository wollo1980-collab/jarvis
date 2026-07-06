"""
Web v1: read-only search connector for current information.

Jarvis fetches a small set of search results, summarizes them briefly and
always returns the source links. Scope is intentionally narrow:
- no browser control
- no opening links
- no writing or clicking
- no generic connector abstraction
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

from core.models import Plan, Result, Status
from core.web_search import SearchResult, WebSearchError, search_web

if TYPE_CHECKING:
    from core.ai import AIEngine

logger = logging.getLogger("jarvis.commands.web")

_ai_engine: Optional["AIEngine"] = None
_searcher: Callable[[str, int, float], list[SearchResult]] = search_web
_timeout_seconds: float = 15.0

_MAX_RESULTS = 5
_PRICE_HINT_WORDS = ("preis", "kostet", "kosten", "teuer", "wieviel", "wie viel")
_AVAILABILITY_HINT_WORDS = ("verfuegbar", "verfügbar", "lieferbar", "lieferung", "bestand")
_DISCLAIMER = (
    "Web-Ueberblick auf Basis der gefundenen Treffer. Fuer wichtige Entscheidungen "
    "bitte die Quellen selbst oeffnen."
)
_SUMMARY_PROMPT_TEMPLATE = (
    "Du bekommst eine Suchanfrage und die obersten Web-Treffer dazu. "
    "Fasse nur zusammen, was aus diesen Treffern plausibel ableitbar ist. "
    "Wenn die Lage duenn, unklar oder widerspruechlich ist, sage das offen. "
    "Erfinde keine Fakten und nenne keine Quellen, die nicht in der Liste stehen. "
    "Antworte kurz, konkret und auf Deutsch.\n\n"
    "Suchanfrage:\n{query}\n\n"
    "{focus_hint}\n"
    "Treffer:\n{results}"
)


def configure(
    ai_engine: "AIEngine",
    timeout_seconds: float = 15.0,
    searcher: Optional[Callable[[str, int, float], list[SearchResult]]] = None,
) -> None:
    """Wire the shared AIEngine and the web search backend into the command."""
    global _ai_engine, _searcher, _timeout_seconds
    _ai_engine = ai_engine
    _timeout_seconds = timeout_seconds
    if searcher is not None:
        _searcher = searcher


def _require_ai_engine() -> "AIEngine":
    """Fail clearly if main.py forgot to configure the command layer."""
    if _ai_engine is None:
        raise RuntimeError(
            "Websuche nicht konfiguriert - commands.web.configure() "
            "muss beim Start aufgerufen werden (siehe main.py)."
        )
    return _ai_engine


def _results_to_prompt_text(results: list[SearchResult]) -> str:
    """Render deterministic result text for the AI summary prompt."""
    lines: list[str] = []
    for index, result in enumerate(results, start=1):
        lines.append(f"{index}. {result.title}")
        if result.snippet:
            lines.append(f"Snippet: {result.snippet}")
        lines.append(f"URL: {result.url}")
    return "\n".join(lines)


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _normalize_query(plan: Plan) -> str:
    """Recover small but useful search hints the planner may omit in target."""
    query = (plan.target or "").strip()
    if not query:
        return ""

    raw_input = (plan.raw_input or "").strip().lower()
    query_lower = query.lower()
    suffixes: list[str] = []

    if raw_input and _contains_any(raw_input, _PRICE_HINT_WORDS) and not _contains_any(
        query_lower, _PRICE_HINT_WORDS
    ):
        suffixes.append("Preis")
    if raw_input and _contains_any(raw_input, _AVAILABILITY_HINT_WORDS) and not _contains_any(
        query_lower, _AVAILABILITY_HINT_WORDS
    ):
        suffixes.append("Verfuegbarkeit")

    if suffixes:
        return f"{query} {' '.join(suffixes)}"
    return query


def _focus_hint(query: str, raw_input: str) -> str:
    """Tighten the summary goal for product-price or availability questions."""
    combined = f"{query}\n{raw_input}".lower()
    if _contains_any(combined, _PRICE_HINT_WORDS):
        return (
            "Fokus: Wenn die Treffer Preise oder Preisbereiche enthalten, nenne zuerst "
            "den klarsten aktuellen Preis oder die engste plausible Preisspanne. "
            "Konzentriere dich auf den Preis, nicht auf allgemeine Produktmerkmale.\n"
        )
    if _contains_any(combined, _AVAILABILITY_HINT_WORDS):
        return (
            "Fokus: Wenn die Treffer Verfuegbarkeit, Lieferbarkeit oder Bestand nennen, "
            "beantworte zuerst genau diesen Punkt und bleibe bei belegbaren Aussagen.\n"
        )
    return ""


def _sources_text(results: list[SearchResult]) -> str:
    """Render the visible source block for the final user message."""
    return "\n".join(
        f"{index}. {result.title} - {result.url}"
        for index, result in enumerate(results, start=1)
    )


class SearchWebCommand:
    name = "search_web"
    description = (
        "Sucht im Web nach aktuellen Informationen oder recherchiert ein Thema "
        "(z. B. 'suche im Web nach ...', 'recherchiere im Internet ...', "
        "'was gibt es Neues zu ...', 'was kostet ...', 'wie teuer ist ...'). "
        "target = die Suchanfrage ohne Trigger-Worte. "
        "Sicherheitsstufe 0, read-only, liefert einen Ueberblick mit Quellen."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        query = _normalize_query(plan)
        if not query:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Wonach soll ich im Web suchen?",
            )

        _require_ai_engine()
        try:
            results = _searcher(query, _MAX_RESULTS, _timeout_seconds)
        except WebSearchError as e:
            return Result(status=Status.FAILED, message=f"Die Websuche hat nicht funktioniert: {e}")

        if not results:
            return Result(
                status=Status.SUCCESS,
                message=f"Ich habe zu '{query}' im Web keine klaren Treffer gefunden.",
                data={"query": query, "results": []},
            )

        prompt = _SUMMARY_PROMPT_TEMPLATE.format(
            query=query,
            focus_hint=_focus_hint(query, plan.raw_input or ""),
            results=_results_to_prompt_text(results),
        )
        summary = _require_ai_engine().answer(prompt, history=[])
        message = f"{summary}\n\nQuellen:\n{_sources_text(results)}\n\n{_DISCLAIMER}"

        return Result(
            status=Status.SUCCESS,
            message=message,
            data={
                "query": query,
                "results": [
                    {"title": result.title, "url": result.url, "snippet": result.snippet}
                    for result in results
                ],
            },
        )


COMMANDS = [SearchWebCommand()]
