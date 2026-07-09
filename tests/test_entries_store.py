"""Tests fuer memory/entries.py - EntryStore (A1): anlegen, auflisten nach
PO-Default (offen/zukuenftig + alle wichtigen), loeschen, Persistenz."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from memory.entries import Entry, EntryStore, is_past


def _future_iso(hours: float = 24.0) -> str:
    return (datetime.now() + timedelta(hours=hours)).isoformat(timespec="minutes")


def _past_iso(hours: float = 24.0) -> str:
    return (datetime.now() - timedelta(hours=hours)).isoformat(timespec="minutes")


def test_add_persists_and_returns_entry(tmp_path: Path):
    store = EntryStore(tmp_path)
    entry = store.add("Zahnarzt", when=_future_iso(), important=False)

    assert entry.id  # id vergeben
    assert entry.text == "Zahnarzt"
    # Persistenz: eine NEUE Store-Instanz liest denselben Eintrag.
    again = EntryStore(tmp_path)
    entries = again.list_open()
    assert [e.text for e in entries] == ["Zahnarzt"]


def test_when_and_important_are_optional(tmp_path: Path):
    store = EntryStore(tmp_path)
    entry = store.add("Milch kaufen")

    assert entry.when == ""
    assert entry.important is False
    assert [e.text for e in store.list_open()] == ["Milch kaufen"]


def test_default_list_shows_open_future_and_all_important(tmp_path: Path):
    """PO-Default: offene/zukuenftige + ALLE wichtigen; nicht-wichtige
    Vergangenheit ist ausgeblendet."""
    store = EntryStore(tmp_path)
    store.add("Zukunft", when=_future_iso())
    store.add("Undatiert")
    store.add("Wichtig-vergangen", when="2025-07-12", important=True)  # Audit-Fall
    store.add("Vergangen", when=_past_iso())

    texts = [e.text for e in store.list_open()]
    assert "Zukunft" in texts
    assert "Undatiert" in texts
    assert "Wichtig-vergangen" in texts  # important schlaegt Vergangenheit
    assert "Vergangen" not in texts      # nicht-wichtige Vergangenheit weg


def test_include_past_shows_everything(tmp_path: Path):
    store = EntryStore(tmp_path)
    store.add("Vergangen", when=_past_iso())

    assert store.list_open() == []
    assert [e.text for e in store.list_open(include_past=True)] == ["Vergangen"]


def test_keyword_and_important_filters(tmp_path: Path):
    store = EntryStore(tmp_path)
    store.add("Audit in Musterstadt", when="2025-07-12", important=True)
    store.add("Zahnarzt", when=_future_iso())

    assert [e.text for e in store.list_open(keyword="audit")] == ["Audit in Musterstadt"]
    assert [e.text for e in store.list_open(important_only=True)] == ["Audit in Musterstadt"]
    assert store.list_open(keyword="nichtvorhanden") == []


def test_sorting_dated_first_then_undated(tmp_path: Path):
    store = EntryStore(tmp_path)
    store.add("Undatiert-frueh")
    store.add("Spaeter", when=_future_iso(hours=48))
    store.add("Frueher", when=_future_iso(hours=2))

    texts = [e.text for e in store.list_open()]
    assert texts == ["Frueher", "Spaeter", "Undatiert-frueh"]


def test_delete_by_id_and_by_text(tmp_path: Path):
    store = EntryStore(tmp_path)
    first = store.add("Zahnarzt morgen")
    store.add("Milch kaufen")

    removed = store.delete(first.id)
    assert removed is not None and removed.text == "Zahnarzt morgen"
    removed2 = store.delete("milch")  # case-insensitive Teilstring
    assert removed2 is not None and removed2.text == "Milch kaufen"
    assert store.list_open() == []


def test_delete_not_found_returns_none(tmp_path: Path):
    store = EntryStore(tmp_path)
    store.add("Etwas")
    assert store.delete("gibtsnicht") is None
    assert store.delete("") is None
    assert len(store.list_open()) == 1  # nichts faelschlich geloescht


def test_is_past_date_only_counts_until_end_of_day():
    today = datetime.now().strftime("%Y-%m-%d")
    assert is_past(today) is False       # heutiges Datum bleibt offen
    assert is_past("2020-01-01") is True
    assert is_past("") is False
    assert is_past("kein-datum") is False  # fail-safe: unparsebar = offen


def test_corrupt_when_entry_stays_visible(tmp_path: Path):
    # Fail-safe: ein Eintrag mit kaputtem when verschwindet nicht still.
    store = EntryStore(tmp_path)
    store.add("Kaputte Zeit", when="irgendwann naechste Woche")
    assert [e.text for e in store.list_open()] == ["Kaputte Zeit"]
