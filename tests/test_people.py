"""Tests fuer memory/people.py (ADR-066 Stein 1) - Personen-Gedaechtnis."""
from __future__ import annotations

from memory.people import PeopleStore


def test_remember_and_get(tmp_path):
    s = PeopleStore(tmp_path)
    s.remember("Anna", "meine Steuerberaterin")
    p = s.get("anna")                       # case-insensitive
    assert p["name"] == "Anna"
    assert "meine Steuerberaterin" in p["notes"]


def test_dedupe_same_note(tmp_path):
    s = PeopleStore(tmp_path)
    s.remember("Anna", "Steuerberaterin")
    s.remember("Anna", "Steuerberaterin")
    assert s.get("anna")["notes"] == ["Steuerberaterin"]


def test_append_second_note(tmp_path):
    s = PeopleStore(tmp_path)
    s.remember("Tom", "leitet Projekt X")
    s.remember("Tom", "sitzt in Berlin")
    assert len(s.get("tom")["notes"]) == 2


def test_find_in_text_is_word_boundary(tmp_path):
    s = PeopleStore(tmp_path)
    s.remember("Anna", "Steuerberaterin")
    assert s.find_in_text("Ich habe morgen ein Meeting mit Anna")
    assert not s.find_in_text("Ich denke an Marianna")   # kein Teilwort-Treffer


def test_context_block(tmp_path):
    s = PeopleStore(tmp_path)
    s.remember("Anna", "Steuerberaterin")
    block = PeopleStore.context_block(s.find_in_text("Termin mit Anna"))
    assert "Personen im Kontext" in block and "Anna" in block and "Steuerberaterin" in block


def test_empty_context_block():
    assert PeopleStore.context_block([]) == ""


def test_notes_are_redacted(tmp_path, monkeypatch):
    import memory.people as pm
    monkeypatch.setattr(pm, "redact", lambda t: t.replace("geheim123", "[SECRET]"))
    s = PeopleStore(tmp_path)
    s.remember("Bob", "Passwort ist geheim123")
    assert "[SECRET]" in s.get("bob")["notes"][0]
    assert "geheim123" not in s.get("bob")["notes"][0]
