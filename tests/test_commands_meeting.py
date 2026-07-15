"""Tests fuer commands/meeting.py (Plan C4) - prepare_meeting."""
from __future__ import annotations

import commands.meeting as meeting_commands
from core.models import Plan, Status


def test_prepare_meeting_calls_injected_prep(tmp_path):
    meeting_commands.configure(lambda q: f"PREP fuer {q or 'naechstes'}")
    result = meeting_commands.PrepareMeetingCommand().execute(
        Plan(intent="prepare_meeting", parameters={"query": "Anna"}))
    assert result.status == Status.SUCCESS
    assert "PREP fuer Anna" in result.message


def test_prepare_meeting_unconfigured_fails_safe(tmp_path):
    meeting_commands.configure(None)
    result = meeting_commands.PrepareMeetingCommand().execute(Plan(intent="prepare_meeting"))
    assert result.status == Status.FAILED
    assert "nicht verdrahtet" in result.message


def test_prepare_meeting_failsafe_on_prep_error(tmp_path):
    def boom(query):
        raise RuntimeError("kaputt")

    meeting_commands.configure(boom)
    result = meeting_commands.PrepareMeetingCommand().execute(Plan(intent="prepare_meeting"))
    assert result.status == Status.FAILED
