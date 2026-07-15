"""Tests fuer core/proactive.py - der Vorausschau-Motor (ADR-063). Rein,
deterministisch, kein Netz/LLM."""
from __future__ import annotations

from datetime import datetime

from core.proactive import PrepSuggestion, plan_preparation


def _ev(subject, start, all_day=False):
    return {"subject": subject, "start": start, "end": start, "all_day": all_day}


def test_picks_first_timed_event_and_builds_reminder():
    now = datetime(2026, 7, 12, 20, 0)          # Vorabend
    events = [_ev("Steuerberater", "2026-07-13T09:00:00")]

    sug = plan_preparation(events, now, lead_minutes=60)

    assert isinstance(sug, PrepSuggestion)
    assert sug.subject == "Steuerberater"
    assert sug.event_time == "09:00"
    assert sug.reminder_time == "08:00"
    assert sug.reminder_when_iso == "2026-07-13T08:00:00"
    assert sug.reminder_text == "Steuerberater um 09:00"
    assert "09:00" in sug.nudge and "08:00" in sug.nudge and "Steuerberater" in sug.nudge
    assert "(ja/nein)" in sug.nudge


def test_all_day_events_are_skipped():
    now = datetime(2026, 7, 12, 20, 0)
    events = [_ev("Urlaub", "2026-07-13T00:00:00", all_day=True)]

    assert plan_preparation(events, now) is None


def test_no_timed_event_returns_none():
    now = datetime(2026, 7, 12, 20, 0)
    assert plan_preparation([], now) is None


def test_earliest_timed_event_wins():
    now = datetime(2026, 7, 12, 20, 0)
    events = [
        _ev("Ganztag", "2026-07-13T00:00:00", all_day=True),
        _ev("Frueh", "2026-07-13T08:30:00"),
        _ev("Spaeter", "2026-07-13T14:00:00"),
    ]

    sug = plan_preparation(events, now)

    assert sug.subject == "Frueh"
    assert sug.event_time == "08:30"


def test_reminder_in_the_past_is_dropped():
    # Termin gleich (in 30 Min), Vorwarnzeit 60 Min -> Erinnerung laege in der
    # Vergangenheit -> kein sinnvoller Vorschlag.
    now = datetime(2026, 7, 13, 8, 30)
    events = [_ev("Gleich-Termin", "2026-07-13T09:00:00")]

    assert plan_preparation(events, now, lead_minutes=60) is None


def test_nudge_includes_people_and_related_tasks():
    """ADR-066 Stein 2: Person + verwandte offene Aufgabe reichern den Anstoss an."""
    now = datetime(2026, 7, 12, 20, 0)
    events = [_ev("Steuerberater", "2026-07-13T09:00:00")]

    sug = plan_preparation(
        events, now,
        people=[{"name": "Anna", "notes": ["meine Steuerberaterin"]}],
        related_tasks=["Steuerunterlagen sortieren"],
    )

    assert "Anna (meine Steuerberaterin)" in sug.nudge
    assert "Steuerunterlagen sortieren" in sug.nudge
    assert "(ja/nein)" in sug.nudge


def test_lead_minutes_are_respected():
    now = datetime(2026, 7, 12, 20, 0)
    events = [_ev("Termin", "2026-07-13T10:00:00")]

    sug = plan_preparation(events, now, lead_minutes=90)

    assert sug.reminder_time == "08:30"
