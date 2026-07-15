"""
Embedding-Schicht (ADR-065 Saeule B2) - austauschbar.

Wandelt Text in Vektoren fuer den semantischen Abruf (Gedaechtnis Stufe 4). Der
konkrete Anbieter ist BEWUSST hinter einer schmalen Funktion gekapselt
(`embed_texts`), damit der Wechsel OpenAI -> lokal (mit dem Ollama-Umzug) spaeter
eine Config-Zeile ist - kein Lock-in.

Jetzt: OpenAI `text-embedding-3-small` (Cent/Monat, top Qualitaet, auch Deutsch),
stdlib-only (urllib) wie die uebrigen Connectoren. Fail-safe: bei fehlendem Key
oder Netzfehler leere Liste - der Aufrufer faellt dann auf "kein Abruf" zurueck.
"""
from __future__ import annotations

import json
import logging
import math
import urllib.error
import urllib.request

logger = logging.getLogger("jarvis.embeddings")

_ENDPOINT = "https://api.openai.com/v1/embeddings"
DEFAULT_MODEL = "text-embedding-3-small"


def embed_texts(texts: list[str], api_key: str, model: str = DEFAULT_MODEL,
                timeout: float = 20.0) -> list[list[float]]:
    """Bettet eine Liste von Texten ein -> Liste von Vektoren (gleiche
    Reihenfolge). Fail-safe: leere Liste bei fehlendem Key/Netzfehler/kaputter
    Antwort. Die Reihenfolge wird ueber den 'index' der Antwort abgesichert."""
    clean = [t for t in (texts or []) if t and t.strip()]
    if not clean or not api_key:
        return []
    body = json.dumps({"model": model or DEFAULT_MODEL, "input": clean}).encode()
    req = urllib.request.Request(
        _ENDPOINT, data=body, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read() or b"{}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        logger.info("Embedding fehlgeschlagen (fail-safe leer): %s", e)
        return []
    data = payload.get("data") or []
    ordered = sorted(data, key=lambda d: d.get("index", 0))
    vectors = [d.get("embedding") or [] for d in ordered]
    if len(vectors) != len(clean) or any(not v for v in vectors):
        logger.info("Embedding: unerwartete Antwortform (fail-safe leer).")
        return []
    return vectors


def cosine(a: list[float], b: list[float]) -> float:
    """Kosinus-Aehnlichkeit zweier Vektoren (0.0 bei leer/degeneriert)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
