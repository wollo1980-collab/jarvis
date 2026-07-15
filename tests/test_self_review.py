"""Tests fuer memory/self_review.py (ADR-066 Stein 3) - LLM injiziert, kein Netz."""
from __future__ import annotations

from datetime import date

from memory.self_review import SelfReviewJournal, collect_signals, self_review


def _ep(ui, resp):
    return {"user_input": ui, "response": resp, "intents": ["x"], "ts": "12:00"}


def test_collect_signals_counts_failures_and_clarifications():
    eps = [_ep("a", "✓ ok"), _ep("b", "✗ Fehler"), _ep("c", "? Was genau?")]
    s = collect_signals(eps)
    assert s["total"] == 3
    assert s["failures"] == 1
    assert s["clarifications"] == 1


def test_collect_signals_detects_rephrasing():
    eps = [_ep("trag mir morgen zahnarzt ein", "✓"),
           _ep("trag mir bitte morgen zahnarzt ein", "✓")]
    assert collect_signals(eps)["rephrasings"] == 1


def test_self_review_uses_injected_llm_and_signals():
    out = self_review([_ep("x", "✗ Fehler")], "Woche", lambda p: "Beobachtung. PROMPT=" + p)
    assert out.startswith("# Selbstbewertung Woche")
    assert "Beobachtung." in out
    assert "Fehlgriffe" in out            # Kennzahlen flossen in den Prompt


def test_self_review_empty_period():
    out = self_review([], "Woche", lambda p: "x")
    assert "Keine Ereignisse" in out


def test_self_review_llm_failure_returns_empty():
    def boom(prompt):
        raise RuntimeError("down")

    assert self_review([_ep("a", "✗")], "W", boom) == ""


def test_journal_write_read_latest(tmp_path):
    j = SelfReviewJournal(tmp_path)
    j.write(date(2026, 7, 11), "# Selbstbewertung\n\nAelter")
    j.write(date(2026, 7, 12), "# Selbstbewertung\n\nNeuer")
    assert "Neuer" in j.read(date(2026, 7, 12))
    assert "Neuer" in j.latest()           # juengste
