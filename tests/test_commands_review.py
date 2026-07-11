"""Tests fuer commands/review.py (Wochen-Rueckblick, Angestellten-Vision
Idee 3) - deterministische Rechenschaft aus CHANGELOG + Delegations-Logs,
kein LLM beteiligt."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import commands.review as review
from commands import REGISTRY
from core.models import Plan, Status


def _write_changelog(tmp_path: Path, entries: list[tuple[date, str]]) -> Path:
    lines = ["# Changelog", ""]
    for entry_date, title in entries:
        lines += [f"## {entry_date.isoformat()} - {title}", "", "- Detailzeile", ""]
    path = tmp_path / "CHANGELOG.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_registered_and_stufe_0():
    cmd = REGISTRY["weekly_review"]
    assert cmd.name == "weekly_review"
    assert cmd.requires_confirmation is False


def test_review_lists_this_week_and_excludes_older(tmp_path):
    today = date.today()
    changelog = _write_changelog(tmp_path, [
        (today, "Heute geliefert"),
        (today - timedelta(days=6), "Vor sechs Tagen geliefert"),
        (today - timedelta(days=10), "Alt und draussen"),
    ])
    review.configure(changelog, None)

    result = review.WeeklyReviewCommand().execute(Plan(intent="weekly_review"))

    assert result.status == Status.SUCCESS
    assert "2 Verbesserungen" in result.message
    assert "Heute geliefert" in result.message
    assert "Vor sechs Tagen geliefert" in result.message
    assert "Alt und draussen" not in result.message
    assert result.data["changelog_entries"] == 2


def test_review_caps_shown_entries(tmp_path):
    today = date.today()
    changelog = _write_changelog(
        tmp_path, [(today, f"Scheibe {i}") for i in range(12)]
    )
    review.configure(changelog, None)

    result = review.WeeklyReviewCommand().execute(Plan(intent="weekly_review"))

    assert "12 Verbesserungen" in result.message
    assert "Scheibe 9" in result.message      # der zehnte gezeigte Titel
    assert "Scheibe 10" not in result.message  # ab hier gekappt
    assert "und 2 weitere" in result.message


def test_review_includes_delegation_stats(tmp_path):
    today = date.today()
    changelog = _write_changelog(tmp_path, [(today, "Eine Scheibe")])
    (tmp_path / "2026-07-10-runtime.log").write_text(
        "2026-07-10 10:00:00,100 INFO jarvis.commands.delegate: Repo-Analyse beendet: "
        "repo=jarvis status=✓ dauer=26.1s turns=3 kosten=0.1367 artefakt=a.md\n"
        "2026-07-10 15:00:00,100 INFO jarvis.commands.delegate: Schreib-Delegation beendet: "
        "repo=jkc status=✓ dauer=248.0s dateien=4 kosten=0.9500 artefakt=b.md\n",
        encoding="utf-8",
    )
    review.configure(changelog, tmp_path)

    result = review.WeeklyReviewCommand().execute(Plan(intent="weekly_review"))

    assert "Agenten-Arbeit: 2 von 2" in result.message
    assert "1.09 USD" in result.message
    assert "Grenzkosten 0" in result.message


def test_review_fail_safe_when_nothing_happened(tmp_path):
    review.configure(tmp_path / "fehlt.md", tmp_path)

    result = review.WeeklyReviewCommand().execute(Plan(intent="weekly_review"))

    assert result.status == Status.SUCCESS
    assert "stiller Anfang" in result.message


def test_system_prompt_routes_review_questions():
    from core.ai import build_system_prompt

    prompt = build_system_prompt()
    assert "weekly_review" in prompt
    assert "Wochenrueckblick" in prompt


def test_weekly_review_allowed_on_runtime_telegram():
    import telegram_channel
    import telegram_main

    assert "weekly_review" in telegram_channel.RUNTIME_ALLOWED_INTENTS
    assert "weekly_review" not in telegram_main.ALLOWED_INTENTS
