"""Tests fuer commands/restart.py (Welle 3.4) - der restart_runtime-Befehl
startet NICHT selbst neu, er ruft nur den injizierten Hook und meldet dessen
Ergebnis ehrlich. Kein echter Prozess-/Thread-Eingriff."""
from __future__ import annotations

import commands.restart as restart
from core.models import Plan, Status


def test_execute_calls_hook_and_reports_restart():
    calls = []
    restart.configure(lambda: (calls.append(True), True)[1])
    try:
        result = restart.RestartRuntimeCommand().execute(Plan(intent="restart_runtime"))
        assert result.status == Status.SUCCESS
        assert calls == [True]  # Hook genau einmal ausgeloest
        assert "neu" in result.message.lower()
    finally:
        restart.configure(None)


def test_failed_spawn_reports_failure_and_stays_alive():
    # Hook meldet False (Nachfolger-Start gescheitert) -> ehrliche
    # Fehlermeldung, KEIN "gleich wieder da"-Versprechen.
    restart.configure(lambda: False)
    try:
        result = restart.RestartRuntimeCommand().execute(Plan(intent="restart_runtime"))
        assert result.status == Status.FAILED
        assert "im Dienst" in result.message
    finally:
        restart.configure(None)


def test_execute_without_hook_is_graceful():
    # Ohne injizierten Hook (z. B. Konsole/main.py) kein Absturz, sondern eine
    # freundliche Meldung.
    restart.configure(None)
    result = restart.RestartRuntimeCommand().execute(Plan(intent="restart_runtime"))
    assert result.status == Status.SUCCESS
    assert "nicht" in result.message.lower()


def test_command_requires_no_confirmation():
    # Zwingend: die Runtime-Speech ist fail-closed - ein bestaetigungspflichtiger
    # Befehl waere ueber Telegram gesperrt und nie ausfuehrbar.
    assert restart.RestartRuntimeCommand().requires_confirmation is False
