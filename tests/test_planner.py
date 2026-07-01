"""Tests für core/planner.py - AIEngine gemockt, es wird nur die
Splitting-Logik geprüft, kein echter API-Aufruf."""
from __future__ import annotations

from unittest.mock import MagicMock

from core.models import Plan
from core.planner import Planner


def test_plan_single_step_passthrough():
    ai = MagicMock()
    ai.get_plan.return_value = Plan(intent="chat", raw_input="wie spät ist es")
    planner = Planner(ai)

    steps = planner.plan("wie spät ist es", [])

    assert len(steps) == 1
    ai.get_plan.assert_called_once_with("wie spät ist es", [])


def test_plan_splits_on_und():
    ai = MagicMock()
    ai.get_plan.side_effect = lambda text, history: Plan(intent="chat", raw_input=text)
    planner = Planner(ai)

    steps = planner.plan("öffne excel und schreibe eine notiz", [])

    assert [s.raw_input for s in steps] == ["öffne excel", "schreibe eine notiz"]


def test_plan_splits_on_und_dann_not_double_split():
    ai = MagicMock()
    ai.get_plan.side_effect = lambda text, history: Plan(intent="chat", raw_input=text)
    planner = Planner(ai)

    steps = planner.plan("öffne excel und dann schließe den browser", [])

    assert [s.raw_input for s in steps] == ["öffne excel", "schließe den browser"]


def test_plan_splits_on_semicolon():
    ai = MagicMock()
    ai.get_plan.side_effect = lambda text, history: Plan(intent="chat", raw_input=text)
    planner = Planner(ai)

    steps = planner.plan("mach a; mach b", [])

    assert [s.raw_input for s in steps] == ["mach a", "mach b"]


def test_plan_preserves_order():
    ai = MagicMock()
    calls = []

    def fake_get_plan(text, history):
        calls.append(text)
        return Plan(intent="chat", raw_input=text)

    ai.get_plan.side_effect = fake_get_plan
    planner = Planner(ai)

    planner.plan("erst a und dann b und dann c", [])

    assert calls == ["erst a", "b", "c"]
