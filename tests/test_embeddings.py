"""Tests fuer core/embeddings.py (ADR-065 B2) - Kosinus + Fail-safe (kein Netz)."""
from __future__ import annotations

import json
import urllib.error

import core.embeddings as embeddings_mod
from core.embeddings import cosine, embed_texts


class _FakeResp:
    """Minimaler urlopen-Kontextmanager-Ersatz (kein Netz)."""

    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._payload


def _patch_urlopen(monkeypatch, payload=None, error=None):
    def fake(req, timeout=0):
        if error is not None:
            raise error
        return _FakeResp(json.dumps(payload).encode())

    monkeypatch.setattr(embeddings_mod.urllib.request, "urlopen", fake)


def test_cosine_identical_is_one():
    assert cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_cosine_orthogonal_is_zero():
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_handles_empty_or_degenerate():
    assert cosine([], [1.0]) == 0.0
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cosine([1.0, 2.0], [1.0]) == 0.0   # ungleiche Laenge


def test_embed_texts_failsafe_without_key():
    assert embed_texts(["irgendwas"], api_key="") == []


def test_embed_texts_failsafe_empty_input():
    assert embed_texts([], api_key="key") == []
    assert embed_texts(["  ", ""], api_key="key") == []


def test_embed_texts_orders_vectors_by_response_index(monkeypatch):
    """Die Reihenfolge wird ueber den 'index' der Antwort abgesichert - auch wenn
    die API die Bloecke vertauscht zurueckgibt."""
    payload = {"data": [
        {"index": 1, "embedding": [0.0, 1.0]},
        {"index": 0, "embedding": [1.0, 0.0]},
    ]}
    _patch_urlopen(monkeypatch, payload=payload)
    assert embed_texts(["a", "b"], api_key="k") == [[1.0, 0.0], [0.0, 1.0]]


def test_embed_texts_failsafe_on_length_mismatch(monkeypatch):
    """Weniger Vektoren als Eingaben -> leere Liste (kein teilweiser Index)."""
    _patch_urlopen(monkeypatch, payload={"data": [{"index": 0, "embedding": [1.0]}]})
    assert embed_texts(["a", "b"], api_key="k") == []


def test_embed_texts_failsafe_on_empty_vector(monkeypatch):
    _patch_urlopen(monkeypatch, payload={"data": [{"index": 0, "embedding": []}]})
    assert embed_texts(["a"], api_key="k") == []


def test_embed_texts_failsafe_on_network_error(monkeypatch):
    _patch_urlopen(monkeypatch, error=urllib.error.URLError("down"))
    assert embed_texts(["a"], api_key="k") == []
