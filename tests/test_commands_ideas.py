"""Tests fuer commands/ideas.py (Angestellten-Vision Stufe 1) - geerdete
Ideen aus Registry + Nutzungs-Statistik + Stand; AI gemockt."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import commands.ideas as ideas
from commands import REGISTRY
from core.models import Plan, Status
from memory.entries import EntryStore
from memory.habits import HabitStats
from memory.lists import ListStore


class FakeAI:
    def __init__(self, reply="1. Sag einfach: 'Briefing'", error=None):
        self._reply = reply
        self._error = error
        self.calls = []

    def generate(self, system, user_text, *, json_mode=False, max_tokens=None):
        self.calls.append({"system": system, "user": user_text})
        if self._error is not None:
            raise self._error
        return self._reply


def _configure(tmp_path: Path, ai=None):
    ai = ai or FakeAI()
    habits = HabitStats(tmp_path)
    entry_store = EntryStore(tmp_path)
    list_store = ListStore(tmp_path)
    ideas.configure(ai, habits, entry_store, list_store)
    return ai, habits, entry_store, list_store


def test_registered_and_stufe_0():
    cmd = REGISTRY["propose_ideas"]
    assert cmd.name == "propose_ideas"
    assert cmd.requires_confirmation is False


def test_ideas_context_is_grounded_in_real_sources(tmp_path):
    """Der Prompt-Kontext traegt Faehigkeits-Katalog, echte Nutzungs-
    Zaehlwerte und den aktuellen Stand - die Erdung gegen Luftschloesser."""
    ai, habits, entry_store, list_store = _configure(tmp_path)
    habits.record("get_news", when=datetime(2026, 7, 13, 7, 0))
    habits.record("get_news", when=datetime(2026, 7, 13, 7, 5))
    entry_store.add("Zahnarzt", when="2099-07-12T09:00")
    list_store.add("einkaufsliste", ["Milch"])

    result = ideas.ProposeIdeasCommand().execute(Plan(intent="propose_ideas"))

    assert result.status == Status.SUCCESS
    assert "Ein paar Gedanken, Sir:" in result.message
    # Entdeckbarkeit der Vertiefung (Angestellten-Vision Stufe 2).
    assert "recherchier Idee" in result.message
    context = ai.calls[0]["user"]
    assert "get_briefing" in context            # Katalog aus der Registry
    assert "get_news: 2x" in context            # echte Nutzung
    assert "einkaufsliste (1)" in context       # aktueller Stand
    assert "NUR Faehigkeiten aus dem Katalog" in ai.calls[0]["system"]
    assert "fuehrst nichts aus" in ai.calls[0]["system"]  # vorschlagen, nie handeln
    # Live-Befund 11.07. nachts: rohe Intent-Namen als Ausloese-Satz liessen
    # "recherchier Idee 2" direkt den Befehl ausfuehren statt zu recherchieren.
    assert "NIEMALS der technische Befehlsname" in ai.calls[0]["system"]


def test_ideas_fail_safe_on_api_error(tmp_path):
    _configure(tmp_path, ai=FakeAI(error=RuntimeError("api down")))

    result = ideas.ProposeIdeasCommand().execute(Plan(intent="propose_ideas"))

    assert result.status == Status.FAILED
    assert "klemmt" in result.message


def test_system_prompt_routes_idea_questions():
    from core.ai import build_system_prompt

    prompt = build_system_prompt()
    assert "propose_ideas" in prompt
    assert "was koennten wir machen?" in prompt


def test_system_prompt_routes_idea_deepening_to_web_search():
    """Angestellten-Vision Stufe 2: 'recherchier Idee 2' vertieft eine
    vorgeschlagene Idee per Websuche - der Planner soll den Idee-Wortlaut
    aus dem Verlauf holen, nie die nackte Nummer suchen."""
    from core.ai import build_system_prompt

    prompt = build_system_prompt()
    assert "recherchier Idee 2" in prompt
    assert "nie die woertliche Nummer" in prompt
    assert "NIEMALS den in der Idee" in prompt  # ... genannten Befehl ausfuehren


def test_propose_ideas_allowed_on_runtime_telegram():
    import telegram_channel
    import telegram_main

    assert "propose_ideas" in telegram_channel.RUNTIME_ALLOWED_INTENTS
    assert "propose_ideas" not in telegram_main.ALLOWED_INTENTS
