"""Tests fuer core/tool_index.py (Plan B, Tool-Vorfilter) - Embedder injiziert."""
from __future__ import annotations

from core.tool_index import ToolIndex

# Mini-Vokabular-Embedder (wie in test_jarvis_runtime): 1.0 wenn Wort vorkommt.
_VOCAB = ["wetter", "kalender", "termin", "musik", "spotify", "merken", "fakt", "liste"]


def _embed(texts):
    return [[1.0 if w in (t or "").lower() else 0.0 for w in _VOCAB] for t in texts]


def _schema(name, desc):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {}}}


_SCHEMAS = [
    _schema("get_weather", "zeigt das wetter"),
    _schema("calendar_agenda", "zeigt deine termine im kalender"),
    _schema("spotify_play", "spielt musik ueber spotify"),
    _schema("remember_fact", "merken eines fakt dauerhaft"),
    _schema("add_to_list", "etwas auf eine liste setzen"),
    _schema("chat", "normales gespraech"),
]


def test_ensure_builds_and_caches(tmp_path):
    idx = ToolIndex(tmp_path / "ti.json", _embed)
    vectors = idx.ensure(_SCHEMAS)
    assert set(vectors) == {s["function"]["name"] for s in _SCHEMAS}
    assert (tmp_path / "ti.json").exists()


def test_ensure_rebuilds_only_on_change(tmp_path):
    calls = {"n": 0}

    def counting_embed(texts):
        calls["n"] += 1
        return _embed(texts)

    idx = ToolIndex(tmp_path / "ti.json", counting_embed)
    idx.ensure(_SCHEMAS)
    idx.ensure(_SCHEMAS)                 # gleiche Menge -> kein Rebuild
    assert calls["n"] == 1
    idx.ensure(_SCHEMAS + [_schema("get_news", "nachrichten")])  # geaenderte Menge
    assert calls["n"] == 2


def test_select_picks_relevant_plus_always(tmp_path):
    idx = ToolIndex(tmp_path / "ti.json", _embed)
    keep = idx.select("wie ist das wetter morgen", _SCHEMAS, k=1, always={"chat"})
    names = {s["function"]["name"] for s in keep}
    assert "get_weather" in names          # relevant gewaehlt
    assert "chat" in names                 # Immer-dabei-Menge
    assert "spotify_play" not in names     # Irrelevantes weggefiltert


def test_select_preserves_schema_order(tmp_path):
    idx = ToolIndex(tmp_path / "ti.json", _embed)
    keep = idx.select("termin im kalender", _SCHEMAS, k=6)
    names = [s["function"]["name"] for s in keep]
    assert names == [s["function"]["name"] for s in _SCHEMAS if s["function"]["name"] in names]


def test_select_failopen_returns_all_when_no_embeddings(tmp_path):
    def broken_embed(texts):
        raise RuntimeError("kein Netz")

    idx = ToolIndex(tmp_path / "ti.json", broken_embed)
    keep = idx.select("egal", _SCHEMAS, k=1)
    assert keep == _SCHEMAS                 # FAIL-OPEN: alle Tools, keine Regression


def test_select_failopen_on_empty_query_vector(tmp_path):
    # ensure() gelingt, aber die Query-Einbettung ist leer -> alle Schemas
    state = {"first": True}

    def embed(texts):
        if state["first"]:
            state["first"] = False
            return _embed(texts)           # Index-Aufbau ok
        return [[]]                         # Query -> leer

    idx = ToolIndex(tmp_path / "ti.json", embed)
    keep = idx.select("wetter", _SCHEMAS, k=1)
    assert keep == _SCHEMAS
