"""Tests fuer memory/reflection.py - die naechtliche Reflexion ('dreaming',
Gedaechtnis Stufe 2). Der LLM-Aufruf ist injiziert (kein Netz)."""
from __future__ import annotations

from datetime import date

from memory.reflection import (
    ReflectionJournal,
    build_reflection_prompt,
    reflect,
    suggestion_from_reflection,
)

_EPISODES = [
    {"ts": "2026-07-12T08:00", "user_input": "wie wird das wetter?", "intents": ["get_weather"]},
    {"ts": "2026-07-12T08:01", "user_input": "was steht heute an?", "intents": ["list_entries"]},
]


def test_prompt_contains_episodes_and_vorschlag_rule():
    prompt = build_reflection_prompt(_EPISODES, date(2026, 7, 12))
    assert "wie wird das wetter?" in prompt
    assert "get_weather" in prompt
    assert "Vermutung" in prompt          # Vorschlag-statt-Aktion-Anweisung
    assert "2026-07-12" in prompt


def test_reflect_uses_injected_llm_and_wraps_markdown():
    seen = {}

    def fake_llm(prompt):
        seen["prompt"] = prompt
        return "Der Nutzer startet den Tag mit Wetter und Terminen."

    text = reflect(_EPISODES, date(2026, 7, 12), fake_llm)

    assert text.startswith("# Reflexion 2026-07-12")
    assert "Wetter und Terminen" in text
    assert "wie wird das wetter?" in seen["prompt"]   # Episoden gingen rein


def test_reflect_empty_day_is_a_quiet_note_without_llm():
    called = {"n": 0}
    text = reflect([], date(2026, 7, 12), lambda p: called.__setitem__("n", 1))
    assert "stiller Tag" in text
    assert called["n"] == 0                # kein LLM-Aufruf bei leerem Tag


def test_reflect_llm_failure_yields_empty(caplog):
    def boom(prompt):
        raise RuntimeError("LLM weg")

    assert reflect(_EPISODES, date(2026, 7, 12), boom) == ""


def test_suggestion_from_reflection_parses_first_vermutung():
    text = (
        "# Reflexion\n\nMartin plant morgens.\n\n"
        "Vermutung: fragt morgens oft nach dem Wochenrueckblick — nachfragen?\n"
        "Vermutung: zweite these — vertiefen?\n"
    )
    assert suggestion_from_reflection(text) == "fragt morgens oft nach dem Wochenrueckblick"


def test_suggestion_from_reflection_empty_when_absent_or_too_long():
    assert suggestion_from_reflection("keine Vermutung hier, nur Text.") == ""
    assert suggestion_from_reflection("") == ""
    too_long = "Vermutung: " + ("x" * 200) + " — nachfragen?"
    assert suggestion_from_reflection(too_long) == ""


def test_journal_write_read_and_latest(tmp_path):
    j = ReflectionJournal(tmp_path)
    j.write(date(2026, 7, 11), "# Reflexion 2026-07-11\n\nGestern.\n")
    j.write(date(2026, 7, 12), "# Reflexion 2026-07-12\n\nHeute.\n")

    assert "Gestern." in j.read(date(2026, 7, 11))
    assert "Heute." in j.latest()          # juengste Datei
    j.write(date(2026, 7, 12), "")         # leerer Text schreibt nichts
    assert "Heute." in j.read(date(2026, 7, 12))
