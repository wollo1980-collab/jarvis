"""Tests fuer scripts/thread_eval.py (Faden-Probe, Spektakulaer #3 Design
2026-07-13) - die Mess-Mechanik selbst, offline mit Attrappen. Die echten
LLM-Laeufe macht das Skript nur bei direktem Aufruf."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core.models import Message, Plan  # noqa: E402
from thread_eval import (  # noqa: E402
    COMPOSER_BATTERY,
    ROUTER_BATTERY,
    evaluate_composer,
    evaluate_router,
    format_composer_report,
    format_router_report,
)


def test_router_battery_contains_counterexample_family():
    """Die Anschluss-Familie (Kurz-Nachfrage MIT Werkzeug, 'und morgen?') ist
    das Gegenbeispiel gegen jeden Kurz-Eingabe-Klassifikator - sie darf nie
    aus der Batterie fallen, sonst misst die Probe nur die halbe Wahrheit."""
    families = {case["familie"] for case in ROUTER_BATTERY}
    assert {"gegenfrage", "anschluss"} <= families
    tool_expecting = [c for c in ROUTER_BATTERY
                      if c["familie"] == "anschluss" and "chat" not in c["erwartet"]]
    assert len(tool_expecting) >= 3


def test_router_battery_cases_carry_history():
    """Ohne History misst die Probe nichts - jeder Fall braucht Vorgespraech."""
    assert all(case["history"] for case in ROUTER_BATTERY)
    assert all(isinstance(case["history"][0], Message) for case in ROUTER_BATTERY)


def test_evaluate_router_scores_hits_and_errors_honestly():
    def fake_plan(eingabe: str, history: list[Message]) -> Plan:
        if "butter" in eingabe:
            return Plan(intent="add_to_list", raw_input=eingabe)
        if "kaputt" in eingabe:
            raise RuntimeError("api down")
        return Plan(intent="get_news", raw_input=eingabe)

    battery = [
        {"name": "a", "familie": "gegenfrage", "history": [Message(role="user", content="x")],
         "eingabe": "und bei dir?", "erwartet": {"chat"}},
        {"name": "b", "familie": "anschluss", "history": [Message(role="user", content="x")],
         "eingabe": "setz noch butter drauf", "erwartet": {"add_to_list"}},
        {"name": "c", "familie": "gegenfrage", "history": [Message(role="user", content="x")],
         "eingabe": "kaputt", "erwartet": {"chat"}},
    ]
    results = evaluate_router(fake_plan, battery)

    assert [r["ok"] for r in results] == [False, True, False]
    assert results[0]["got"] == "get_news"           # Fehlgriff ehrlich benannt
    assert results[2]["got"].startswith("ERR:")      # API-Fehler nie als Fehlgriff
    report = format_router_report(results)
    assert "1/2" in report or "gegenfrage: 0/2" in report


def test_evaluate_composer_detects_headline_repetition():
    def repeating_compose(eingabe, history, steps, results):
        return ("Bei mir alles gut. Uebrigens nochmal die Lage: Rauchen wird "
                "teurer, Sanktionen gegen Russland, Hilfe fuer die Ukraine.")

    def threadful_compose(eingabe, history, steps, results):
        return "Bei mir laeuft alles rund, Sir - danke der Nachfrage."

    repeated = evaluate_composer(repeating_compose)
    assert all(r["wiederholt"] for r in repeated)
    assert all(r["marker_treffer"] >= 2 for r in repeated)

    clean = evaluate_composer(threadful_compose)
    assert not any(r["wiederholt"] for r in clean)
    report = format_composer_report(clean)
    assert f"{len(COMPOSER_BATTERY)}/{len(COMPOSER_BATTERY)}" in report


def test_evaluate_composer_counts_errors_as_repetition_free_but_visible():
    def broken_compose(eingabe, history, steps, results):
        raise ValueError("boom")

    results = evaluate_composer(broken_compose)
    assert all(r["antwort"].startswith("ERR:") for r in results)
    assert not any(r["wiederholt"] for r in results)
