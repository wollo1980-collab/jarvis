"""Tests fuer scripts/reasoning_eval.py (ADR-060 Phase 2, Migrations-Batterie).

Nur die reine Auswert-Logik (evaluate/format_report) - kein echter Kern, kein
LLM-Call, kein Netz: `decide_fn` wird als Attrappe injiziert."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from core.models import Plan

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "reasoning_eval", _ROOT / "scripts" / "reasoning_eval.py"
)
reasoning_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reasoning_eval)


def _decider(mapping):
    """decide_fn-Attrappe: Phrase -> Plan(intent=mapping[phrase])."""
    return lambda phrase: Plan(intent=mapping[phrase], raw_input=phrase)


def test_evaluate_counts_hits_and_records_misses():
    battery = {"get_weather": ["a", "b"], "chat": ["c"]}
    mapping = {"a": "get_weather", "b": "get_news", "c": "chat"}

    results = reasoning_eval.evaluate(_decider(mapping), battery)

    assert results["get_weather"]["hits"] == 1
    assert results["get_weather"]["total"] == 2
    assert results["get_weather"]["misses"] == [("b", "get_news")]
    assert results["chat"]["hits"] == 1
    assert results["chat"]["misses"] == []


def test_evaluate_args_flags_missing_required_field():
    """Argument-Pruefung (Netflix/Kaffee-Lehre): richtiger Intent, aber leeres
    Pflichtfeld -> arg_ok False (genau der Bug, den die Intent-only-Eval nicht
    sah)."""
    battery = [
        ("guter fall", "add_entry", lambda p: bool(p.parameters.get("text"))),
        ("leerer fall", "add_entry", lambda p: bool(p.parameters.get("text"))),
        ("falscher intent", "add_entry", lambda p: True),
    ]
    plans = {
        "guter fall": Plan(intent="add_entry", parameters={"text": "Zahnarzt"}),
        "leerer fall": Plan(intent="add_entry", parameters={}),   # Intent ok, Feld leer
        "falscher intent": Plan(intent="chat"),
    }
    results = reasoning_eval.evaluate_args(lambda p: plans[p], battery)

    assert results[0]["arg_ok"] is True
    assert results[1]["intent_ok"] is True and results[1]["arg_ok"] is False
    assert results[2]["intent_ok"] is False and results[2]["arg_ok"] is False
    report = reasoning_eval.format_arg_report(results)
    assert "Args vollstaendig: 1/3" in report


def test_format_report_marks_perfect_partial_and_totals():
    results = {
        "get_weather": {"hits": 2, "total": 2, "misses": []},
        "get_briefing": {"hits": 1, "total": 2, "misses": [("x", "list_entries")]},
    }

    report = reasoning_eval.format_report(results)

    assert "[OK] get_weather: 2/2 (100%)" in report
    assert "[~]  get_briefing: 1/2 (50%)" in report
    assert "miss: 'x' -> list_entries" in report
    assert "Gesamt: 3/4 (75%)" in report


# --- Artefakt-Metadaten (Truth Repair II: einordenbare Messungen) -----------

def test_estimate_cost_only_for_known_models():
    """Kosten nur bei bekanntem Preis (ehrlich None statt geraten)."""
    cost = reasoning_eval._estimate_cost_usd("gpt-4o-mini", 1_000_000, 100_000)
    assert cost == round(0.15 + 0.06, 4)
    assert reasoning_eval._estimate_cost_usd("unbekannt-9000", 1000, 10) is None
    assert reasoning_eval._estimate_cost_usd("gpt-4o-mini", 0, 0) is None


def test_git_state_and_sdk_versions_are_failsoft_dicts():
    """Metadaten-Helfer liefern immer ein dict (fail-soft) - im echten Repo
    mit gefuelltem SHA + Python-Version."""
    git = reasoning_eval._git_state()
    assert set(git) == {"sha", "dirty"}
    assert git["sha"]                       # Tests laufen im Repo
    sdk = reasoning_eval._sdk_versions()
    assert sdk["python"]
    assert "openai" in sdk
