"""
Werkzeug-Vorfilter (Plan B, 13.07.2026) - „dem Kern nur die relevanten Tools zeigen".

Bettet die Beschreibungen aller registrierten Werkzeuge ein und waehlt zu einer
Anfrage die aehnlichsten aus, statt ALLE ~35 Schemas an den denkenden Kern zu
geben. Das haelt den Prompt schlank und ist die Voraussetzung fuer Werkzeug-
Wachstum (S4b) und lokale Klein-Modelle (Ollama).

Der konkrete Embedder ist INJIZIERT (wie memory/semantic.py) - testbar, kein Netz
im Test. Durchgehend FAIL-OPEN: fehlen Embeddings (kein Key/Netzfehler/kaputte
Antwort), liefert `select` ALLE Schemas zurueck - also exakt das heutige Verhalten,
keine Regression und kein weggefiltertes Werkzeug.

Der Index wird per Fingerprint (Hash ueber Namen+Beschreibungen) gecacht und nur
neu gebaut, wenn sich die Werkzeug-Menge aendert.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Callable, Iterable

from core.embeddings import cosine
from core.fileio import read_json, write_json_atomic

logger = logging.getLogger("jarvis.tool_index")

# embed_fn(texts) -> Liste von Vektoren (gleiche Reihenfolge), wie core.embeddings.
EmbedFn = Callable[[list[str]], list[list[float]]]


def _tool_text(schema: dict) -> str:
    fn = schema.get("function", {}) if isinstance(schema, dict) else {}
    return f"{fn.get('name', '')}: {fn.get('description', '')}".strip()


def _name(schema: dict) -> str:
    return (schema.get("function", {}) or {}).get("name", "")


def _fingerprint(schemas: list[dict]) -> str:
    joined = "\n".join(sorted(_tool_text(s) for s in schemas))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


class ToolIndex:
    """Persistenter Embedding-Index der Werkzeug-Beschreibungen + Auswahl."""

    def __init__(self, path, embed_fn: EmbedFn):
        self._path = Path(path)
        self._embed = embed_fn

    def _load(self) -> dict:
        data = read_json(self._path, {})
        return data if isinstance(data, dict) else {}

    def ensure(self, schemas: list[dict]) -> dict:
        """Liefert {name: vektor} passend zur aktuellen Werkzeug-Menge; baut neu,
        wenn der Fingerprint abweicht. Fail-safe: {} bei Embedding-Fehler."""
        fingerprint = _fingerprint(schemas)
        cached = self._load()
        vectors = cached.get("vectors")
        if cached.get("fingerprint") == fingerprint and isinstance(vectors, dict) and vectors:
            return vectors

        names = [_name(s) for s in schemas]
        try:
            vecs = self._embed([_tool_text(s) for s in schemas])
        except Exception:  # noqa: BLE001 - der Vorfilter stoert den Kern nie
            logger.warning("Tool-Index: Embedding fehlgeschlagen (fail-safe leer).", exc_info=True)
            return {}
        if len(vecs) != len(names) or any(not v for v in vecs):
            logger.info("Tool-Index: unerwartete Embedding-Form (fail-safe leer).")
            return {}
        built = {n: v for n, v in zip(names, vecs)}
        write_json_atomic(self._path, {"fingerprint": fingerprint, "vectors": built})
        return built

    def select(self, user_input: str, schemas: list[dict], *,
               k: int = 12, always: Iterable[str] = ()) -> list[dict]:
        """Die zur Eingabe aehnlichsten k Werkzeuge PLUS die Immer-dabei-Menge
        `always`. Reihenfolge der Original-Schemas bleibt erhalten (Prompt-Cache).
        FAIL-OPEN: fehlen Embeddings/Query, kommen ALLE Schemas zurueck."""
        always_set = set(always)
        vectors = self.ensure(schemas)
        if not vectors:
            return schemas
        try:
            qv = self._embed([user_input or ""])
        except Exception:  # noqa: BLE001
            return schemas
        if not qv or not qv[0]:
            return schemas
        query = qv[0]
        ranked = sorted(vectors.items(), key=lambda kv: cosine(query, kv[1]), reverse=True)
        chosen = {name for name, _ in ranked[:max(1, k)]}
        chosen |= always_set
        keep = [s for s in schemas if _name(s) in chosen]
        return keep or schemas
