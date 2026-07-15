"""Tests fuer commands/calendar.py (ADR-062, read-first). Der Client ist
injiziert (kein Netz)."""
from __future__ import annotations

from datetime import datetime, timedelta

import commands.calendar as calendar
from core.models import Plan, Status


class _FakeCal:
    """Liefert vorbereitete, schon geparste Events (Form von client.agenda())."""

    def __init__(self, events):
        self._events = events
        self.calls = []

    def agenda(self, start, end):
        self.calls.append((start, end))
        return self._events


def test_agenda_not_configured_is_friendly():
    calendar.configure(config=None, client=None)   # kein Zugang
    result = calendar.CalendarAgendaCommand().execute(Plan(intent="calendar_agenda"))
    assert result.status == Status.NEEDS_CLARIFICATION
    assert "nicht eingerichtet" in result.message


def test_agenda_lists_events_with_time_and_location():
    today = datetime.now().strftime("%Y-%m-%d")
    fake = _FakeCal([
        {"subject": "Steuerberater", "start": f"{today}T09:00:00",
         "end": f"{today}T10:00:00", "location": "Büro", "all_day": False},
        {"subject": "Urlaub", "start": f"{today}T00:00:00",
         "end": f"{today}T23:59:00", "location": "", "all_day": True},
    ])
    calendar.configure(config=None, client=fake)

    result = calendar.CalendarAgendaCommand().execute(
        Plan(intent="calendar_agenda", parameters={"day": "heute"}))

    assert result.status == Status.SUCCESS
    assert "Heute im Kalender" in result.message
    assert "09:00 Steuerberater (Büro)" in result.message
    assert "ganztägig Urlaub" in result.message
    assert result.data["count"] == 2


def test_agenda_empty_day_is_free():
    calendar.configure(config=None, client=_FakeCal([]))
    result = calendar.CalendarAgendaCommand().execute(
        Plan(intent="calendar_agenda", parameters={"day": "morgen"}))
    assert result.status == Status.SUCCESS
    assert "gehört dir" in result.message
    assert "Morgen" in result.message


def test_agenda_resolves_tomorrow_window():
    fake = _FakeCal([])
    calendar.configure(config=None, client=fake)
    calendar.CalendarAgendaCommand().execute(
        Plan(intent="calendar_agenda", parameters={"day": "morgen"}))

    start, end = fake.calls[0]
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    assert start.startswith(tomorrow) and start.endswith("T00:00:00")


# --- Schreiben: calendar_add_event (Sicherheitsstufe 2) ---------------------

class _FakeWrite:
    """Merkt sich angelegte Termine (Form von client.create_event())."""

    def __init__(self):
        self.created = []

    def create_event(self, subject, start_iso, end_iso, location="", all_day=False):
        self.created.append({"subject": subject, "start": start_iso, "end": end_iso,
                             "location": location, "all_day": all_day})
        return {"id": "1", "subject": subject}


def test_add_event_not_configured_is_friendly():
    calendar.configure(config=None)   # kein Schreibzugang
    result = calendar.CreateCalendarEventCommand().execute(
        Plan(intent="calendar_add_event", parameters={"subject": "X", "day": "morgen"}))
    assert result.status == Status.NEEDS_CLARIFICATION
    assert "nicht eingerichtet" in result.message


def test_add_event_preview_shows_concrete_details():
    calendar.configure(config=None, write_client=_FakeWrite())
    prev = calendar.CreateCalendarEventCommand().preview(
        Plan(intent="calendar_add_event",
             parameters={"subject": "Zahnarzt", "day": "morgen", "time": "14:00",
                         "location": "Praxis"}))
    assert "Zahnarzt" in prev and "Morgen" in prev and "14:00" in prev and "Praxis" in prev


def test_add_event_creates_timed_one_hour_event():
    w = _FakeWrite()
    calendar.configure(config=None, write_client=w)
    result = calendar.CreateCalendarEventCommand().execute(
        Plan(intent="calendar_add_event",
             parameters={"subject": "Meeting", "day": "morgen", "time": "9:30"}))

    assert result.status == Status.SUCCESS
    assert len(w.created) == 1
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    assert w.created[0]["start"] == f"{tomorrow}T09:30:00"
    assert w.created[0]["end"] == f"{tomorrow}T10:30:00"   # Standard: 1 Stunde
    assert w.created[0]["all_day"] is False


def test_add_event_without_time_is_all_day():
    w = _FakeWrite()
    calendar.configure(config=None, write_client=w)
    result = calendar.CreateCalendarEventCommand().execute(
        Plan(intent="calendar_add_event", parameters={"subject": "Urlaub", "day": "morgen"}))

    assert result.status == Status.SUCCESS
    assert w.created[0]["all_day"] is True


def test_add_event_needs_a_subject():
    w = _FakeWrite()
    calendar.configure(config=None, write_client=w)
    result = calendar.CreateCalendarEventCommand().execute(
        Plan(intent="calendar_add_event", parameters={"day": "morgen", "time": "14:00"}))

    assert result.status == Status.NEEDS_CLARIFICATION
    assert w.created == []   # nichts angelegt ohne Titel


# --- Verschieben / Absagen (Sicherheitsstufe 2) -----------------------------

class _FakeCalWrite:
    """Fake-Graph-Schreib-Client: liefert Termine (mit id) und merkt sich
    Aenderungen/Loeschungen."""

    def __init__(self, events=None):
        self._events = events or []
        self.updated = []
        self.deleted = []

    def agenda(self, start, end):
        return list(self._events)

    def update_event(self, event_id, start_iso=None, end_iso=None, subject=None, location=None):
        self.updated.append({"id": event_id, "start": start_iso, "end": end_iso})
        return {"id": event_id}

    def delete_event(self, event_id):
        self.deleted.append(event_id)


def _ev(subject, start, end, event_id="E1", all_day=False):
    return {"id": event_id, "subject": subject, "start": start, "end": end,
            "location": "", "all_day": all_day}


def test_move_event_not_configured_is_friendly():
    calendar.configure(config=None)   # kein Schreibzugang
    result = calendar.MoveCalendarEventCommand().execute(
        Plan(intent="calendar_move_event", parameters={"subject": "Zahnarzt", "time": "15:00"}))
    assert result.status == Status.NEEDS_CLARIFICATION
    assert "eingerichtet" in result.message


def test_move_event_reschedules_and_keeps_duration():
    w = _FakeCalWrite([_ev("Zahnarzt", "2030-01-02T09:00:00", "2030-01-02T10:00:00")])
    calendar.configure(config=None, write_client=w)

    prev = calendar.MoveCalendarEventCommand().preview(
        Plan(intent="calendar_move_event", parameters={"subject": "zahnarzt", "time": "15:00"}))
    assert "verschiebe" in prev.lower() and "15:00" in prev

    result = calendar.MoveCalendarEventCommand().execute(
        Plan(intent="calendar_move_event", parameters={"subject": "zahnarzt", "time": "15:00"}))

    assert result.status == Status.SUCCESS
    assert len(w.updated) == 1
    assert w.updated[0]["start"] == "2030-01-02T15:00:00"
    assert w.updated[0]["end"] == "2030-01-02T16:00:00"   # 1 h Dauer erhalten


def test_move_event_not_found_asks():
    w = _FakeCalWrite([])
    calendar.configure(config=None, write_client=w)
    result = calendar.MoveCalendarEventCommand().execute(
        Plan(intent="calendar_move_event", parameters={"subject": "unbekannt", "time": "15:00"}))
    assert result.status == Status.NEEDS_CLARIFICATION
    assert "keinen Termin" in result.message
    assert w.updated == []


def test_move_event_ambiguous_asks_which():
    w = _FakeCalWrite([
        _ev("Meeting A", "2030-01-02T09:00:00", "2030-01-02T10:00:00", event_id="A"),
        _ev("Meeting B", "2030-01-03T11:00:00", "2030-01-03T12:00:00", event_id="B"),
    ])
    calendar.configure(config=None, write_client=w)
    result = calendar.MoveCalendarEventCommand().execute(
        Plan(intent="calendar_move_event", parameters={"subject": "meeting", "time": "15:00"}))
    assert result.status == Status.NEEDS_CLARIFICATION
    assert "Mehrere" in result.message
    assert w.updated == []


def test_cancel_event_deletes_after_confirmation():
    w = _FakeCalWrite([_ev("Zahnarzt", "2030-01-02T09:00:00", "2030-01-02T10:00:00")])
    calendar.configure(config=None, write_client=w)

    prev = calendar.CancelCalendarEventCommand().preview(
        Plan(intent="calendar_cancel_event", parameters={"subject": "zahnarzt"}))
    assert "sage" in prev.lower() and "löschen" in prev.lower()

    result = calendar.CancelCalendarEventCommand().execute(
        Plan(intent="calendar_cancel_event", parameters={"subject": "zahnarzt"}))

    assert result.status == Status.SUCCESS
    assert w.deleted == ["E1"]


def test_calendar_write_confirmation_diet_po_20260714():
    """PO 14.07. (ADR-068): Eintragen/Verschieben tun SOFORT und nennen den
    Rueckweg; nur das Absagen (extern sichtbar) fragt weiter."""
    assert calendar.CreateCalendarEventCommand.requires_confirmation is False
    assert calendar.MoveCalendarEventCommand.requires_confirmation is False
    assert calendar.CancelCalendarEventCommand.requires_confirmation is True

    w = _FakeCalWrite([_ev("Zahnarzt", "2030-01-02T09:00:00", "2030-01-02T10:00:00")])
    calendar.configure(config=None, write_client=w)
    moved = calendar.MoveCalendarEventCommand().execute(
        Plan(intent="calendar_move_event", parameters={"subject": "zahnarzt", "time": "15:00"}))
    assert "vorher" in moved.message           # Rueckweg: alter Zeitpunkt steht drin
    assert "zurückschieben" in moved.message


def test_cancel_event_not_found_asks():
    w = _FakeCalWrite([])
    calendar.configure(config=None, write_client=w)
    result = calendar.CancelCalendarEventCommand().execute(
        Plan(intent="calendar_cancel_event", parameters={"subject": "nix"}))
    assert result.status == Status.NEEDS_CLARIFICATION
    assert w.deleted == []
