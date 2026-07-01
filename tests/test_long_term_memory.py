"""Tests für memory/long_term.py - arbeitet auf tmp_path, keine
Berührung des echten memory_data-Ordners."""
from __future__ import annotations

from pathlib import Path

from memory.long_term import LongTermMemory


def test_creates_default_file(tmp_path: Path):
    LongTermMemory(tmp_path)
    assert (tmp_path / "long_term.json").exists()


def test_remember_and_list_roundtrip(tmp_path: Path):
    store = LongTermMemory(tmp_path)
    store.remember("arbeitet an Jarvis", category="projekt")
    store.remember("macht montags Reports", category="gewohnheit")

    facts = store.all_facts()
    assert [f.text for f in facts] == ["arbeitet an Jarvis", "macht montags Reports"]
    assert [f.category for f in facts] == ["projekt", "gewohnheit"]


def test_remember_persists_after_reload(tmp_path: Path):
    store_a = LongTermMemory(tmp_path)
    store_a.remember("mag trockenen Humor", category="praeferenz")

    store_b = LongTermMemory(tmp_path)
    facts = store_b.all_facts()
    assert [f.text for f in facts] == ["mag trockenen Humor"]


def test_unknown_category_falls_back_to_allgemein(tmp_path: Path):
    store = LongTermMemory(tmp_path)
    store.remember("irgendwas", category="nicht_vorgesehen")

    facts = store.all_facts()
    assert facts[0].category == "allgemein"


def test_forget_removes_matching_fact(tmp_path: Path):
    store = LongTermMemory(tmp_path)
    store.remember("macht montags Reports", category="gewohnheit")

    removed = store.forget("montags Reports")

    assert removed is True
    assert store.all_facts() == []


def test_forget_returns_false_when_nothing_matches(tmp_path: Path):
    store = LongTermMemory(tmp_path)
    store.remember("macht montags Reports", category="gewohnheit")

    removed = store.forget("nichts passt hier")

    assert removed is False
    assert len(store.all_facts()) == 1


def test_summary_text_empty_when_no_facts(tmp_path: Path):
    store = LongTermMemory(tmp_path)
    assert store.summary_text() == ""


def test_summary_text_lists_all_facts(tmp_path: Path):
    store = LongTermMemory(tmp_path)
    store.remember("arbeitet an Jarvis", category="projekt")
    store.remember("mag trockenen Humor", category="praeferenz")

    summary = store.summary_text()

    assert "(projekt) arbeitet an Jarvis" in summary
    assert "(praeferenz) mag trockenen Humor" in summary


def test_summary_text_respects_max_facts(tmp_path: Path):
    store = LongTermMemory(tmp_path)
    for i in range(5):
        store.remember(f"fakt {i}")

    summary = store.summary_text(max_facts=2)

    assert "fakt 3" in summary
    assert "fakt 4" in summary
    assert "fakt 0" not in summary
