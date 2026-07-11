"""Tests fuer commands/lists.py - Einkaufsliste erzaehlen, nummeriert
zeigen, streichen, leeren mit Undo. Store gegen tmp_path."""
from __future__ import annotations

from pathlib import Path

import commands.lists as lists
from commands import REGISTRY
from core.models import Plan, Status


def _configure(tmp_path: Path):
    return lists.configure(tmp_path)


def test_all_list_commands_registered_and_stufe_0():
    for intent in ("add_to_list", "show_list", "remove_from_list", "clear_list", "restore_list"):
        assert REGISTRY[intent].name == intent
        assert REGISTRY[intent].requires_confirmation is False  # Undo statt Rueckfrage


def test_add_with_items_array(tmp_path: Path):
    _configure(tmp_path)
    result = lists.AddToListCommand().execute(
        Plan(intent="add_to_list", parameters={"list": "einkaufsliste",
                                               "items": ["Milch", "Butter", "drei Zwiebeln"]})
    )
    assert result.status == Status.SUCCESS
    assert "Milch, Butter, drei Zwiebeln" in result.message
    assert "Einkaufsliste" in result.message
    assert result.data["total"] == 3


def test_add_falls_back_to_colon_payload(tmp_path: Path):
    """Der Doppelpunkt-Schutz des Satz-Splitters liefert die Nutzlast am
    Stueck - der Rueckfall zerlegt sie an Kommas und 'und'."""
    _configure(tmp_path)
    result = lists.AddToListCommand().execute(
        Plan(intent="add_to_list", parameters={"list": "einkaufsliste"},
             raw_input="Einkaufsliste: Milch, Butter und drei Zwiebeln")
    )
    assert result.status == Status.SUCCESS
    assert result.data["added"] == ["Milch", "Butter", "drei Zwiebeln"]


def test_add_without_name_uses_single_existing_list(tmp_path: Path):
    store = _configure(tmp_path)
    store.add("packliste", ["Zelt"])
    result = lists.AddToListCommand().execute(
        Plan(intent="add_to_list", parameters={"items": ["Schlafsack"]})
    )
    assert result.status == Status.SUCCESS
    assert store.get("packliste") == ["Zelt", "Schlafsack"]


def test_add_without_name_and_no_lists_defaults_to_einkaufsliste(tmp_path: Path):
    store = _configure(tmp_path)
    result = lists.AddToListCommand().execute(
        Plan(intent="add_to_list", parameters={"items": ["Milch"]})
    )
    assert result.status == Status.SUCCESS
    assert store.get("einkaufsliste") == ["Milch"]


def test_add_without_items_asks_back(tmp_path: Path):
    _configure(tmp_path)
    result = lists.AddToListCommand().execute(Plan(intent="add_to_list", parameters={"list": "x"}))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_show_list_is_numbered(tmp_path: Path):
    """Nummeriert (C-Scheibe): Grundlage fuer 'streich Nummer 2'."""
    store = _configure(tmp_path)
    store.add("einkaufsliste", ["Milch", "Butter"])
    result = lists.ShowListCommand().execute(
        Plan(intent="show_list", parameters={"list": "einkaufsliste"})
    )
    assert result.status == Status.SUCCESS
    assert "1. Milch" in result.message
    assert "2. Butter" in result.message


def test_show_without_name_gives_overview_when_multiple(tmp_path: Path):
    store = _configure(tmp_path)
    store.add("einkaufsliste", ["Milch"])
    store.add("packliste", ["Zelt", "Schlafsack"])
    result = lists.ShowListCommand().execute(Plan(intent="show_list"))
    assert "Einkaufsliste (1 Posten)" in result.message
    assert "Packliste (2 Posten)" in result.message


def test_show_unknown_list_fails_honestly(tmp_path: Path):
    _configure(tmp_path)
    result = lists.ShowListCommand().execute(
        Plan(intent="show_list", parameters={"list": "gibtsnicht"})
    )
    assert result.status == Status.FAILED


def test_remove_by_item_text(tmp_path: Path):
    store = _configure(tmp_path)
    store.add("einkaufsliste", ["Milch", "Butter"])
    result = lists.RemoveFromListCommand().execute(
        Plan(intent="remove_from_list", parameters={"item": "milch"})
    )
    assert result.status == Status.SUCCESS
    assert "«Milch»" in result.message
    assert store.get("einkaufsliste") == ["Butter"]


def test_remove_by_index_uses_numbered_view(tmp_path: Path):
    store = _configure(tmp_path)
    store.add("einkaufsliste", ["Milch", "Butter", "Brot"])
    result = lists.RemoveFromListCommand().execute(
        Plan(intent="remove_from_list", parameters={"index": 2})
    )
    assert result.status == Status.SUCCESS
    assert "«Butter»" in result.message


def test_remove_ambiguous_without_list_fails_honestly(tmp_path: Path):
    store = _configure(tmp_path)
    store.add("einkaufsliste", ["Milch"])
    store.add("packliste", ["Milchpulver"])
    result = lists.RemoveFromListCommand().execute(
        Plan(intent="remove_from_list", parameters={"item": "milch"})
    )
    assert result.status == Status.FAILED
    assert store.get("einkaufsliste") == ["Milch"]  # nichts geraten, nichts geloescht


def test_clear_mentions_restore_and_restore_brings_back(tmp_path: Path):
    """Undo statt Rueckfrage (PIS): leeren wirkt sofort, nichts ist weg."""
    store = _configure(tmp_path)
    store.add("einkaufsliste", ["Milch", "Brot"])

    cleared = lists.ClearListCommand().execute(
        Plan(intent="clear_list", parameters={"list": "einkaufsliste"})
    )
    assert cleared.status == Status.SUCCESS
    assert "wieder her" in cleared.message  # Undo-Hinweis
    assert store.get("einkaufsliste") is None

    restored = lists.RestoreListCommand().execute(Plan(intent="restore_list"))
    assert restored.status == Status.SUCCESS
    assert store.get("einkaufsliste") == ["Milch", "Brot"]


def test_clear_without_name_resolves_single_list(tmp_path: Path):
    store = _configure(tmp_path)
    store.add("einkaufsliste", ["Milch"])
    result = lists.ClearListCommand().execute(Plan(intent="clear_list"))
    assert result.status == Status.SUCCESS
    assert store.get("einkaufsliste") is None


def test_clear_without_name_asks_when_multiple(tmp_path: Path):
    store = _configure(tmp_path)
    store.add("einkaufsliste", ["Milch"])
    store.add("packliste", ["Zelt"])
    result = lists.ClearListCommand().execute(Plan(intent="clear_list"))
    assert result.status == Status.NEEDS_CLARIFICATION
    assert store.get("einkaufsliste") == ["Milch"]  # nichts passiert


def test_restore_with_empty_trash_fails_honestly(tmp_path: Path):
    _configure(tmp_path)
    result = lists.RestoreListCommand().execute(Plan(intent="restore_list"))
    assert result.status == Status.FAILED
