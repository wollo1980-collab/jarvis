"""Tests fuer commands/people.py (ADR-066 Stein 1)."""
from __future__ import annotations

import commands.people as people
from commands import REGISTRY
from core.models import Plan, Status
from memory.people import PeopleStore


def test_registered_and_stufe_0():
    cmd = REGISTRY["remember_person"]
    assert cmd.name == "remember_person"
    assert cmd.requires_confirmation is False


def test_remember_person_stores(tmp_path):
    store = PeopleStore(tmp_path)
    people.configure(store)
    result = people.RememberPersonCommand().execute(
        Plan(intent="remember_person", parameters={"name": "Anna", "note": "meine Steuerberaterin"}))
    assert result.status == Status.SUCCESS
    assert "Anna" in result.message
    assert store.get("anna")["notes"] == ["meine Steuerberaterin"]


def test_remember_person_needs_name_and_note(tmp_path):
    people.configure(PeopleStore(tmp_path))
    result = people.RememberPersonCommand().execute(
        Plan(intent="remember_person", parameters={"name": "Anna"}))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_who_is_answers_from_store(tmp_path):
    store = PeopleStore(tmp_path)
    store.remember("Anna", "meine Steuerberaterin")
    people.configure(store)
    result = people.WhoIsCommand().execute(
        Plan(intent="who_is", parameters={"name": "Anna"}))
    assert result.status == Status.SUCCESS
    assert "Steuerberaterin" in result.message


def test_who_is_unknown_is_honest(tmp_path):
    people.configure(PeopleStore(tmp_path))
    result = people.WhoIsCommand().execute(
        Plan(intent="who_is", parameters={"name": "Xaver"}))
    assert result.status == Status.SUCCESS
    assert "noch nichts gemerkt" in result.message
