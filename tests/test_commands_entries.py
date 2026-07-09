"""Tests fuer commands/entries.py - add/list/delete_entry (A1). Der Store
laeuft gegen tmp_path (configure-Muster wie commands/memory.py)."""
from __future__ import annotations

from pathlib import Path

import commands.entries as entries
from core.models import Plan, Result, Status


def _configure(tmp_path: Path) -> None:
    entries.configure(tmp_path)


def test_add_entry_echoes_text_and_readable_time(tmp_path: Path):
    _configure(tmp_path)
    result = entries.AddEntryCommand().execute(
        Plan(
            intent="add_entry",
            parameters={"text": "Zahnarzt", "when": "2099-07-10T09:00"},
        )
    )

    assert result.status == Status.SUCCESS
    assert "«Zahnarzt»" in result.message
    assert "10.07.2099 09:00" in result.message  # Echo mit lesbarer Zeit
    assert result.data["id"]


def test_add_entry_important_gets_star_and_date_only_format(tmp_path: Path):
    _configure(tmp_path)
    result = entries.AddEntryCommand().execute(
        Plan(
            intent="add_entry",
            parameters={"text": "Audit in Musterstadt", "when": "2025-07-12", "important": True},
        )
    )

    assert result.status == Status.SUCCESS
    assert result.message.startswith("⭐ Wichtiger Eintrag gespeichert")
    assert "12.07.2025" in result.message  # ganztaegig ohne Uhrzeit


def test_add_entry_without_text_asks_back(tmp_path: Path):
    _configure(tmp_path)
    result = entries.AddEntryCommand().execute(Plan(intent="add_entry"))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_add_entry_falls_back_to_target(tmp_path: Path):
    # Der Planner legt den Text idealerweise in parameters.text ab -
    # faellt er auf target zurueck, geht nichts verloren.
    _configure(tmp_path)
    result = entries.AddEntryCommand().execute(Plan(intent="add_entry", target="Milch kaufen"))
    assert result.status == Status.SUCCESS
    assert "«Milch kaufen»" in result.message


def test_list_entries_empty_is_friendly(tmp_path: Path):
    _configure(tmp_path)
    result = entries.ListEntriesCommand().execute(Plan(intent="list_entries"))
    assert result.status == Status.SUCCESS
    assert "keine" in result.message.lower()


def test_list_entries_shows_star_and_date(tmp_path: Path):
    _configure(tmp_path)
    entries.AddEntryCommand().execute(
        Plan(intent="add_entry", parameters={"text": "Audit", "when": "2025-07-12", "important": True})
    )
    entries.AddEntryCommand().execute(Plan(intent="add_entry", parameters={"text": "Milch kaufen"}))

    result = entries.ListEntriesCommand().execute(Plan(intent="list_entries"))

    assert result.status == Status.SUCCESS
    assert "⭐ «Audit» — 12.07.2025" in result.message
    assert "«Milch kaufen»" in result.message
    assert result.data["count"] == 2


def test_list_entries_keyword_filter_via_parameters(tmp_path: Path):
    _configure(tmp_path)
    entries.AddEntryCommand().execute(Plan(intent="add_entry", parameters={"text": "Zahnarzt"}))
    entries.AddEntryCommand().execute(Plan(intent="add_entry", parameters={"text": "Milch kaufen"}))

    result = entries.ListEntriesCommand().execute(
        Plan(intent="list_entries", parameters={"keyword": "zahn"})
    )

    assert "Zahnarzt" in result.message
    assert "Milch" not in result.message


def test_delete_entry_found_and_not_found(tmp_path: Path):
    _configure(tmp_path)
    entries.AddEntryCommand().execute(Plan(intent="add_entry", parameters={"text": "Zahnarzt morgen"}))

    ok = entries.DeleteEntryCommand().execute(
        Plan(intent="delete_entry", parameters={"text": "zahnarzt"})
    )
    assert ok.status == Status.SUCCESS
    assert "«Zahnarzt morgen»" in ok.message

    miss = entries.DeleteEntryCommand().execute(
        Plan(intent="delete_entry", parameters={"text": "gibtsnicht"})
    )
    assert miss.status == Status.FAILED


def test_delete_entry_without_text_asks_back(tmp_path: Path):
    _configure(tmp_path)
    result = entries.DeleteEntryCommand().execute(Plan(intent="delete_entry"))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_not_configured_raises_clear_error():
    entries._store = None
    try:
        entries.AddEntryCommand().execute(Plan(intent="add_entry", target="x"))
        assert False, "erwartete RuntimeError"
    except RuntimeError as e:
        assert "nicht konfiguriert" in str(e)
