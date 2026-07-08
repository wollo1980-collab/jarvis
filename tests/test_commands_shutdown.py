"""Tests fuer commands/shutdown.py - der stop_runtime-Befehl faehrt NICHT selbst
herunter, er ruft nur den injizierten Hook (Stop-Sentinel in die Runtime-Queue).
Kein echter Prozess-/Thread-Eingriff."""
from __future__ import annotations

import commands.shutdown as shutdown
from core.models import Plan, Status


def test_execute_calls_hook_and_reports():
    calls = []
    shutdown.configure(lambda: calls.append(True))
    try:
        result = shutdown.StopRuntimeCommand().execute(Plan(intent="stop_runtime"))
        assert result.status == Status.SUCCESS
        assert calls == [True]  # Hook genau einmal ausgeloest
        assert "herunter" in result.message.lower()
    finally:
        shutdown.configure(None)


def test_execute_without_hook_is_graceful():
    # Ohne injizierten Hook (z. B. Konsole/main.py) kein Absturz, sondern eine
    # freundliche Meldung.
    shutdown.configure(None)
    result = shutdown.StopRuntimeCommand().execute(Plan(intent="stop_runtime"))
    assert result.status == Status.SUCCESS
    assert "nicht" in result.message.lower()


def test_command_requires_no_confirmation():
    # Zwingend: die Runtime-Speech ist fail-closed - ein bestaetigungspflichtiger
    # Befehl waere ueber Telegram gesperrt und nie ausfuehrbar.
    assert shutdown.StopRuntimeCommand().requires_confirmation is False
