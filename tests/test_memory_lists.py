"""Tests fuer memory/lists.py - benannte Listen mit Papierkorb (Undo statt
Rueckfrage). Alles gegen tmp_path, kein globaler Zustand."""
from __future__ import annotations

from pathlib import Path

from memory.lists import ListStore, display_name, normalize_name


def test_normalize_and_display_name():
    assert normalize_name("  Einkaufsliste ") == "einkaufsliste"
    assert display_name("einkaufsliste") == "Einkaufsliste"
    assert display_name("") == ""


def test_add_creates_list_and_skips_duplicates_case_insensitive(tmp_path: Path):
    store = ListStore(tmp_path)

    added, skipped = store.add("Einkaufsliste", ["Milch", "Butter"])
    assert added == ["Milch", "Butter"] and skipped == []

    added, skipped = store.add("einkaufsliste", ["milch", "Brot"])
    assert added == ["Brot"]
    assert skipped == ["milch"]  # zweimal Milch heisst einmal Milch
    assert store.get("EINKAUFSLISTE") == ["Milch", "Butter", "Brot"]


def test_get_unknown_list_is_none_and_overview_sorted(tmp_path: Path):
    store = ListStore(tmp_path)
    assert store.get("packliste") is None
    store.add("packliste", ["Zelt"])
    store.add("einkaufsliste", ["Milch", "Brot"])
    assert store.overview() == [("einkaufsliste", 2), ("packliste", 1)]


def test_remove_by_text_and_by_index(tmp_path: Path):
    store = ListStore(tmp_path)
    store.add("einkaufsliste", ["Milch", "Butter", "Brot"])

    assert store.remove("einkaufsliste", item="butter") == ("einkaufsliste", "Butter")
    assert store.remove("einkaufsliste", index=2) == ("einkaufsliste", "Brot")
    assert store.get("einkaufsliste") == ["Milch"]


def test_remove_without_name_only_on_unique_hit(tmp_path: Path):
    store = ListStore(tmp_path)
    store.add("einkaufsliste", ["Milch"])
    store.add("packliste", ["Milchpulver"])

    # "Milch" trifft beide Listen -> nicht eindeutig -> None (nie raten).
    assert store.remove(None, item="milch") is None
    # "pulver" trifft nur die Packliste -> gestrichen.
    assert store.remove(None, item="pulver") == ("packliste", "Milchpulver")


def test_removing_last_item_drops_empty_list(tmp_path: Path):
    store = ListStore(tmp_path)
    store.add("einkaufsliste", ["Milch"])
    store.remove("einkaufsliste", item="Milch")
    assert store.get("einkaufsliste") is None
    assert store.overview() == []


def test_clear_moves_to_trash_and_restore_brings_back(tmp_path: Path):
    store = ListStore(tmp_path)
    store.add("einkaufsliste", ["Milch", "Brot"])

    cleared = store.clear("einkaufsliste")
    assert cleared == ["Milch", "Brot"]
    assert store.get("einkaufsliste") is None

    # Ohne Namen: genau eine Liste im Papierkorb -> eindeutig.
    name, items = store.restore()
    assert name == "einkaufsliste"
    assert store.get("einkaufsliste") == ["Milch", "Brot"]

    # Papierkorb ist danach leer - zweites restore geht ehrlich leer aus.
    assert store.restore() is None


def test_clear_unknown_list_is_none(tmp_path: Path):
    store = ListStore(tmp_path)
    assert store.clear("gibtsnicht") is None


def test_restore_merges_with_new_items_without_duplicates(tmp_path: Path):
    store = ListStore(tmp_path)
    store.add("einkaufsliste", ["Milch", "Brot"])
    store.clear("einkaufsliste")
    store.add("einkaufsliste", ["Milch", "Eier"])  # frisch begonnen

    name, _ = store.restore("einkaufsliste")
    assert name == "einkaufsliste"
    assert store.get("einkaufsliste") == ["Milch", "Eier", "Brot"]  # Milch nicht doppelt


def test_items_are_redacted_before_persist(tmp_path: Path, monkeypatch):
    """Auto-Redaction (ADR-040) gilt auch fuer Listen-Posten."""
    import memory.lists as lists_module

    monkeypatch.setattr(lists_module, "redact", lambda t: t.replace("geheim", "[GEHEIM]"))
    store = ListStore(tmp_path)
    store.add("einkaufsliste", ["geheim-zutat"])
    assert store.get("einkaufsliste") == ["[GEHEIM]-zutat"]
