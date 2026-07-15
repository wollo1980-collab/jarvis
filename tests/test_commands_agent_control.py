"""Tests fuer commands/agent_control.py - Agenten-Stopp auf Zuruf (c1)."""
from __future__ import annotations

import commands.agent_control as agent_control
from core.models import Plan, Status


def _plan():
    return Plan(intent="stop_agent", raw_input="stopp den agenten")


def test_stop_agent_cancels_running_delegation():
    calls = []
    agent_control.configure(lambda: calls.append(1) or True)
    try:
        result = agent_control.StopAgentCommand().execute(_plan())
    finally:
        agent_control.configure(None)

    assert result.status == Status.SUCCESS
    assert calls == [1]
    assert "gestoppt" in result.message


def test_stop_agent_when_nothing_runs():
    agent_control.configure(lambda: False)
    try:
        result = agent_control.StopAgentCommand().execute(_plan())
    finally:
        agent_control.configure(None)

    assert result.status == Status.SUCCESS
    assert "kein Agent" in result.message


def test_stop_agent_without_hook_is_honest():
    agent_control.configure(None)
    result = agent_control.StopAgentCommand().execute(_plan())
    assert result.status == Status.SUCCESS
    assert "keinen Kill-Switch-Hook" in result.message


def test_stop_agent_registered_and_confirmation_free():
    """Zwingend requires_confirmation=False (muss ueber fail-closed Kanaele
    greifen) + in der Registry."""
    from commands import REGISTRY

    assert "stop_agent" in REGISTRY
    assert REGISTRY["stop_agent"].requires_confirmation is False
