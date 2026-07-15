"""Tests fuer commands/selfreview.py (ADR-066 Stein 3)."""
from __future__ import annotations

from datetime import date

import commands.selfreview as selfreview
from commands import REGISTRY
from core.models import Plan, Status
from memory.self_review import SelfReviewJournal


def test_registered_and_stufe_0():
    cmd = REGISTRY["self_review"]
    assert cmd.name == "self_review"
    assert cmd.requires_confirmation is False


def test_returns_latest_without_markdown_header(tmp_path):
    journal = SelfReviewJournal(tmp_path)
    journal.write(date(2026, 7, 12),
                  "# Selbstbewertung Woche\n\nIch habe Kalender-Wuensche mehrfach missverstanden.")
    selfreview.configure(journal)

    result = selfreview.SelfReviewCommand().execute(Plan(intent="self_review"))

    assert result.status == Status.SUCCESS
    assert "missverstanden" in result.message
    assert "#" not in result.message        # Markdown-Kopf abgetrennt


def test_empty_and_no_on_demand_is_friendly(tmp_path):
    selfreview.configure(SelfReviewJournal(tmp_path))   # kein on_demand
    result = selfreview.SelfReviewCommand().execute(Plan(intent="self_review"))
    assert result.status == Status.SUCCESS
    assert "noch nicht selbst bewertet" in result.message


def test_generates_on_demand_when_journal_empty(tmp_path):
    """'Wie schlaegst du dich?' erzeugt bei leerem Journal SOFORT eine Bewertung
    (statt auf den Scheduler zu warten) - die Reibung aus dem PO-Log."""
    journal = SelfReviewJournal(tmp_path)
    calls = {"n": 0}

    def on_demand():
        calls["n"] += 1
        journal.write(date.today(), "# Selbstbewertung\n\nHeute lief es solide.")
        return journal.latest()

    selfreview.configure(journal, on_demand=on_demand)
    result = selfreview.SelfReviewCommand().execute(Plan(intent="self_review"))

    assert calls["n"] == 1
    assert result.status == Status.SUCCESS
    assert "solide" in result.message
    assert "#" not in result.message           # Markdown-Kopf abgetrennt
