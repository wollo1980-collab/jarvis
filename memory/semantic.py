"""
Semantischer Gedaechtnis-Index (ADR-065 Saeule B2, Gedaechtnis Stufe 4).

Bettet Gedaechtnis-Inhalte (Fakten, Episoden) als Vektoren ein und findet zu
einer Anfrage die AEHNLICHSTEN - so holt der Kern pro Runde die RELEVANTEN
Erinnerungen in den Kontext, statt nur die letzten Nachrichten zu sehen ("was
hatten wir letzte Woche zu X?").

Rein & testbar: die Embedding-Funktion (`embed_fn(list[str]) -> list[vector]`)
ist INJIZIERT - im Test ein deterministischer Fake, live OpenAI (core.embeddings).
Persistenz als JSON (Vektoren als Listen). Dedupe ueber Text-Hash; fail-safe
(kein Embed -> nichts indiziert / kein Treffer, nie ein Crash).
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Callable

from core.embeddings import cosine
from core.fileio import read_json, write_json_atomic

logger = logging.getLogger("jarvis.semantic")

EmbedFn = Callable[["list[str]"], "list[list[float]]"]


def _hash(text: str) -> str:
    # Whitespace normalisieren (auch intern), damit "a  b" == "a b" beim Dedupe.
    normalized = " ".join(text.split()).lower()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


class SemanticIndex:
    """Persistenter Vektor-Index ueber kurze Gedaechtnis-Texte. Klein gehalten:
    lineare Kosinus-Suche (fuer ein persoenliches Gedaechtnis voellig ausreichend)."""

    def __init__(self, path: Path, embed_fn: EmbedFn, max_entries: int = 2000):
        self._path = Path(path)
        self._embed = embed_fn
        self._max = max_entries

    def _load(self) -> list[dict]:
        data = read_json(self._path, [])
        return data if isinstance(data, list) else []

    def add_texts(self, entries: "list[tuple[str, str]]") -> int:
        """Indiziert (text, quelle)-Paare, die noch nicht drin sind. Ein EINZIGER
        Embedding-Aufruf fuer alle neuen. Liefert die Zahl neu indizierter."""
        items = self._load()
        seen = {it.get("hash") for it in items}
        fresh: list[tuple[str, str, str]] = []
        for text, source in entries:
            clean = (text or "").strip()
            if not clean:
                continue
            h = _hash(clean)
            if h in seen:
                continue
            seen.add(h)
            fresh.append((h, clean, source))
        if not fresh:
            return 0
        vectors = self._embed([t for _, t, _ in fresh])
        if len(vectors) != len(fresh):
            logger.info("Semantik: Embedding lieferte nicht alle Vektoren (fail-safe, nichts indiziert).")
            return 0
        for (h, text, source), vec in zip(fresh, vectors):
            items.append({"hash": h, "text": text, "source": source, "vector": vec})
        if len(items) > self._max:          # aeltestes zuerst raus (Deckel)
            items = items[-self._max:]
        write_json_atomic(self._path, items)
        return len(fresh)

    def search(self, query: str, k: int = 3, min_score: float = 0.30) -> list[dict]:
        """Die k aehnlichsten Eintraege ueber `min_score`. Liefert je {text,
        source, score}. Fail-safe: leere Liste bei kein-Index/kein-Embed."""
        query = (query or "").strip()
        items = self._load()
        if not query or not items:
            return []
        qv = self._embed([query])
        if not qv or not qv[0]:
            return []
        scored = [(cosine(qv[0], it.get("vector") or []), it) for it in items]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {"text": it["text"], "source": it.get("source", ""), "score": round(score, 3)}
            for score, it in scored[:k] if score >= min_score
        ]
