"""
Read-only web search for Jarvis (web v1, Nutzwert-Phase).

The connector deliberately stays small and provider-neutral:
- stdlib HTTP only (`urllib`)
- no browser automation
- no page actions, no page clicks
- only title, snippet and URL of search results

Search results are fetched from the Lite endpoint of DuckDuckGo and parsed
locally. The command layer decides how to present or summarize the results.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger("jarvis.web_search")

_SEARCH_ENDPOINT = "https://lite.duckduckgo.com/lite/"
_SEARCH_REGION = "de-de"
_USER_AGENT = "Mozilla/5.0 (compatible; Jarvis/1.0; +https://local.invalid)"


@dataclass
class SearchResult:
    """A single read-only web search hit."""

    title: str
    url: str
    snippet: str = ""


class WebSearchError(RuntimeError):
    """Raised when Jarvis cannot fetch or parse web search results."""


def _build_search_url(query: str) -> str:
    """Build the search URL for a single query."""
    params = urlencode({"q": query, "kl": _SEARCH_REGION})
    return f"{_SEARCH_ENDPOINT}?{params}"


def _clean_text(text: str) -> str:
    """Normalize whitespace inside parsed HTML text."""
    return " ".join(text.split())


def _looks_like_challenge_page(html: str) -> bool:
    """Detect provider-side bot/captcha pages before parsing empty results."""
    lowered = html.lower()
    return (
        "anomaly-modal" in lowered
        or "anomaly.js" in lowered
        or "bots use duckduckgo too" in lowered
        or "complete the following challenge" in lowered
    )


def _decode_result_url(raw_url: str) -> str:
    """Unwrap DuckDuckGo redirect links and normalize relative URLs."""
    url = raw_url.strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = urljoin("https://duckduckgo.com", url)

    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc:
        redirected = parse_qs(parsed.query).get("uddg", [""])[0]
        if redirected:
            return unquote(redirected)
    return url


def _is_noise_result(url: str) -> bool:
    """Drop known DuckDuckGo ad/help redirect results from the final hit list."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    query = parse_qs(parsed.query)

    if "duckduckgo.com" not in host:
        return False
    if path.endswith("/y.js"):
        return True
    if path.startswith("/duckduckgo-help-pages/"):
        return True
    return "ad_provider" in query or "click_metadata" in query


class _DuckDuckGoHtmlParser(HTMLParser):
    """Extracts result titles, URLs and snippets from DuckDuckGo HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self._capture_kind: Optional[str] = None
        self._capture_tag: Optional[str] = None
        self._buffer: list[str] = []
        self._pending_result: Optional[SearchResult] = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        """Start capturing title or snippet blocks when a result element starts."""
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())

        if "result__a" in classes or "result-link" in classes:
            href = _decode_result_url(attr_map.get("href", ""))
            if href:
                self._pending_result = SearchResult(title="", url=href, snippet="")
                self._start_capture("title", tag)
            return

        if ("result__snippet" in classes or "result-snippet" in classes) and self.results:
            if not self.results[-1].snippet:
                self._start_capture("snippet", tag)

    def handle_data(self, data: str) -> None:
        """Collect text while a title or snippet block is active."""
        if self._capture_kind is not None:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        """Finalize a captured title or snippet when its element closes."""
        if self._capture_kind is None or tag != self._capture_tag:
            return

        text = _clean_text("".join(self._buffer))
        if self._capture_kind == "title":
            if self._pending_result is not None and text:
                self._pending_result.title = text
                self.results.append(self._pending_result)
            self._pending_result = None
        elif self._capture_kind == "snippet":
            if self.results and text and not self.results[-1].snippet:
                self.results[-1].snippet = text

        self._capture_kind = None
        self._capture_tag = None
        self._buffer = []

    def _start_capture(self, kind: str, tag: str) -> None:
        """Reset the capture buffer for a new result field."""
        self._capture_kind = kind
        self._capture_tag = tag
        self._buffer = []


def _dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    """Drop duplicate URLs while preserving the original order."""
    seen: set[str] = set()
    deduped: list[SearchResult] = []
    for result in results:
        key = result.url.strip().lower()
        if not key or key in seen or _is_noise_result(result.url):
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def _parse_results(html: str, max_results: int) -> list[SearchResult]:
    """Parse search result HTML into normalized, deduplicated hits."""
    parser = _DuckDuckGoHtmlParser()
    parser.feed(html)
    parser.close()
    return _dedupe_results(parser.results)[:max_results]


def search_web(query: str, max_results: int = 5, timeout_seconds: float = 15.0) -> list[SearchResult]:
    """Fetch top search hits for a query via DuckDuckGo HTML search."""
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("query must not be empty")

    request = Request(
        _build_search_url(clean_query),
        headers={"User-Agent": _USER_AGENT},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            charset = "utf-8"
            get_charset = getattr(response.headers, "get_content_charset", None)
            if callable(get_charset):
                charset = get_charset() or "utf-8"
            html = response.read().decode(charset, errors="replace")
    except OSError as e:
        raise WebSearchError(f"Websuche nicht erreichbar: {e}") from e
    except UnicodeError as e:
        raise WebSearchError(f"Websuche konnte nicht gelesen werden: {e}") from e

    if _looks_like_challenge_page(html):
        raise WebSearchError(
            "Websuche wurde vom Suchanbieter blockiert (Bot-/Captcha-Seite). "
            "Bitte spaeter erneut versuchen."
        )

    results = _parse_results(html, max_results=max_results)
    logger.info("Websuche: %d Treffer fuer %r", len(results), clean_query)
    return results
