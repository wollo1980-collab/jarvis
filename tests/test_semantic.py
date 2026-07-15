"""Tests fuer memory/semantic.py (ADR-065 B2) - Embedding injiziert (Fake,
wort-basiert), kein Netz."""
from __future__ import annotations

from memory.semantic import SemanticIndex

_VOCAB = ["kaffee", "schwarz", "montag", "report", "python", "backup", "s3", "mutter"]


def _fake_embed(texts):
    """Deterministisches Wort-Praesenz-Embedding: aehnliche Texte teilen
    Dimensionen -> Kosinus > 0."""
    out = []
    for t in texts:
        low = t.lower()
        out.append([1.0 if w in low else 0.0 for w in _VOCAB])
    return out


def _index(tmp_path):
    return SemanticIndex(tmp_path / "sem.json", _fake_embed)


def test_add_and_search_finds_most_relevant(tmp_path):
    idx = _index(tmp_path)
    idx.add_texts([
        ("Ich trinke meinen Kaffee schwarz", "fakt"),
        ("Montags mache ich Reports", "fakt"),
        ("Das Backup-Tool sichert nach S3", "episode"),
    ])

    hits = idx.search("Wie trinke ich meinen Kaffee?", k=1)

    assert hits and hits[0]["text"] == "Ich trinke meinen Kaffee schwarz"
    assert hits[0]["source"] == "fakt"
    assert hits[0]["score"] > 0.3


def test_dedupe_does_not_reindex(tmp_path):
    idx = _index(tmp_path)
    assert idx.add_texts([("Kaffee schwarz", "fakt")]) == 1
    assert idx.add_texts([("kaffee   SCHWARZ", "fakt")]) == 0   # gleicher Text (normalisiert)


def test_search_empty_index_returns_nothing(tmp_path):
    assert _index(tmp_path).search("irgendwas") == []


def test_min_score_filters_unrelated(tmp_path):
    idx = _index(tmp_path)
    idx.add_texts([("Python Backup nach S3", "episode")])

    # voellig anderes Thema (kein gemeinsames Vokabular) -> kein Treffer
    assert idx.search("Mutter Geburtstag", k=3, min_score=0.3) == []


def test_add_texts_failsafe_when_embed_returns_wrong_count(tmp_path):
    idx = SemanticIndex(tmp_path / "sem.json", lambda texts: [])   # Embed liefert nichts
    assert idx.add_texts([("etwas", "fakt")]) == 0
    assert idx.search("etwas") == []
