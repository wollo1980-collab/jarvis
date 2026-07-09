"""Tests für commands/memory.py (remember_fact/forget_fact, v0.4,
ADR-009). configure() wird in jedem Test mit tmp_path aufgerufen,
damit nie der echte memory_data-Ordner angefasst wird."""
from __future__ import annotations

from pathlib import Path

import commands.memory as memory_commands
from commands.memory import ForgetFactCommand, ListFactsCommand, RememberFactCommand
from core.models import Plan, Status


def test_remember_fact_needs_target(tmp_path: Path):
    memory_commands.configure(tmp_path)
    cmd = RememberFactCommand()

    result = cmd.execute(Plan(intent="remember_fact", target=None))

    assert result.status == Status.NEEDS_CLARIFICATION


def test_remember_fact_stores_with_category(tmp_path: Path):
    memory_commands.configure(tmp_path)
    cmd = RememberFactCommand()

    result = cmd.execute(
        Plan(
            intent="remember_fact",
            target="macht montags Reports",
            parameters={"category": "gewohnheit"},
        )
    )

    assert result.status == Status.SUCCESS
    assert "Gemerkt, Sir" in result.message  # Persona-Pass 2026-07-09
    facts = memory_commands._require_long_term().all_facts()
    assert facts[0].text == "macht montags Reports"
    assert facts[0].category == "gewohnheit"


def test_remember_fact_defaults_to_allgemein_without_category(tmp_path: Path):
    memory_commands.configure(tmp_path)
    cmd = RememberFactCommand()

    cmd.execute(Plan(intent="remember_fact", target="irgendein Fakt"))

    facts = memory_commands._require_long_term().all_facts()
    assert facts[0].category == "allgemein"


def test_forget_fact_needs_target(tmp_path: Path):
    memory_commands.configure(tmp_path)
    cmd = ForgetFactCommand()

    result = cmd.execute(Plan(intent="forget_fact", target=None))

    assert result.status == Status.NEEDS_CLARIFICATION


def test_forget_fact_success(tmp_path: Path):
    memory_commands.configure(tmp_path)
    memory_commands._require_long_term().remember("macht montags Reports", category="gewohnheit")
    cmd = ForgetFactCommand()

    result = cmd.execute(Plan(intent="forget_fact", target="montags Reports"))

    assert result.status == Status.SUCCESS
    # Welle 1.2: die Bestaetigung ENTWERTET den Fakt ausdruecklich (landet im
    # Gespraechsverlauf und soll das Loeschen verstaerken, nicht den alten
    # Wortlaut bekraeftigen).
    assert "Langzeitgedächtnis entfernt" in result.message
    assert "gilt ab sofort nicht mehr" in result.message


def test_forget_fact_not_found(tmp_path: Path):
    memory_commands.configure(tmp_path)
    cmd = ForgetFactCommand()

    result = cmd.execute(Plan(intent="forget_fact", target="gibt es nicht"))

    assert result.status == Status.FAILED


def test_list_facts_empty_is_honest(tmp_path: Path):
    # Welle 1.3 (sichtbares Gedaechtnis): leerer Zustand wird klar benannt.
    memory_commands.configure(tmp_path)

    result = ListFactsCommand().execute(Plan(intent="list_facts"))

    assert result.status == Status.SUCCESS
    assert "leer" in result.message.lower()


def test_list_facts_shows_all_with_category(tmp_path: Path):
    memory_commands.configure(tmp_path)
    memory_commands._require_long_term().remember("macht montags Reports", category="gewohnheit")
    memory_commands._require_long_term().remember("Alexander ist mein Sohn", category="allgemein")

    result = ListFactsCommand().execute(Plan(intent="list_facts"))

    assert result.status == Status.SUCCESS
    assert "(gewohnheit) macht montags Reports" in result.message
    assert "(allgemein) Alexander ist mein Sohn" in result.message
    assert result.data["count"] == 2


def test_raises_clear_error_when_not_configured(monkeypatch):
    monkeypatch.setattr(memory_commands, "_long_term", None)

    cmd = RememberFactCommand()
    try:
        cmd.execute(Plan(intent="remember_fact", target="irgendwas"))
        assert False, "hätte RuntimeError werfen müssen"
    except RuntimeError as e:
        assert "configure()" in str(e)


def test_commands_are_registered_in_registry(tmp_path: Path):
    from commands import REGISTRY

    assert "remember_fact" in REGISTRY
    assert "forget_fact" in REGISTRY
