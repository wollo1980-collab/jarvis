"""Tests fuer core/ics_calendar.py - ICS-Feed-Leser (OAuth-freier Kalender-Weg,
ADR-062). Der Feed wird injiziert; kein Netz."""
from __future__ import annotations

from datetime import datetime

import pytest

from core.graph_calendar import GraphError
from core.ics_calendar import IcsCalendarClient

_HEAD = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\nX-WR-CALNAME:Kalender\r\n"
_FOOT = "END:VCALENDAR\r\n"


def _feed(*vevents: str) -> str:
    return _HEAD + "".join(vevents) + _FOOT


def _timed(uid: str, start: str, end: str, summary: str, location: str = "", rrule: str = "") -> str:
    ev = (f"BEGIN:VEVENT\r\nUID:{uid}\r\n"
          f"DTSTART;TZID=W. Europe Standard Time:{start}\r\n"
          f"DTEND;TZID=W. Europe Standard Time:{end}\r\n"
          f"SUMMARY:{summary}\r\n")
    if location:
        ev += f"LOCATION:{location}\r\n"
    if rrule:
        ev += f"RRULE:{rrule}\r\n"
    ev += "END:VEVENT\r\n"
    return ev


def _client(text: str) -> IcsCalendarClient:
    return IcsCalendarClient(ics_url="https://x.test/cal.ics", fetcher=lambda url: text)


# --- Grundfaelle ------------------------------------------------------------

def test_timed_event_in_window_is_returned():
    feed = _feed(_timed("1", "20260713T100000", "20260713T110000", "Test Jarvis", "Buero"))
    events = _client(feed).agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00")

    assert len(events) == 1
    ev = events[0]
    assert ev["subject"] == "Test Jarvis"
    assert ev["start"] == "2026-07-13T10:00:00"   # lokale Wandzeit unveraendert
    assert ev["location"] == "Buero"
    assert ev["all_day"] is False


def test_event_outside_window_is_excluded():
    feed = _feed(_timed("1", "20260720T100000", "20260720T110000", "Naechste Woche"))
    events = _client(feed).agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00")

    assert events == []


def test_all_day_event_is_marked_and_included():
    ev = ("BEGIN:VEVENT\r\nUID:2\r\nDTSTART;VALUE=DATE:20260713\r\n"
          "DTEND;VALUE=DATE:20260714\r\nSUMMARY:Urlaub\r\n"
          "X-MICROSOFT-CDO-ALLDAYEVENT:TRUE\r\nEND:VEVENT\r\n")
    events = _client(_feed(ev)).agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00")

    assert len(events) == 1
    assert events[0]["all_day"] is True
    assert events[0]["subject"] == "Urlaub"


def test_events_are_sorted_by_start():
    feed = _feed(
        _timed("1", "20260713T150000", "20260713T160000", "Spaeter"),
        _timed("2", "20260713T090000", "20260713T093000", "Frueher"),
    )
    events = _client(feed).agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00")

    assert [e["subject"] for e in events] == ["Frueher", "Spaeter"]


# --- Wiederholungen ---------------------------------------------------------

def test_weekly_recurrence_hits_later_week():
    # startet Montag 06.07., woechentlich -> auch am 13.07. (gleicher Wochentag)
    feed = _feed(_timed("1", "20260706T090000", "20260706T093000", "Standup",
                        rrule="FREQ=WEEKLY"))
    events = _client(feed).agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00")

    assert len(events) == 1
    assert events[0]["start"] == "2026-07-13T09:00:00"


def test_weekly_byday_recurrence():
    day = datetime(2026, 7, 13)                 # Zielfenster
    code = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")[day.weekday()]
    start = datetime(2026, 6, 29, 8, 0)         # zwei Wochen vorher, gleicher Wochentag-Bereich
    feed = _feed(_timed("1", start.strftime("%Y%m%dT%H%M%S"),
                        start.strftime("%Y%m%dT%H3000"), "Weekly",
                        rrule=f"FREQ=WEEKLY;BYDAY={code}"))
    events = _client(feed).agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00")

    assert len(events) == 1
    assert events[0]["start"] == "2026-07-13T08:00:00"


def test_recurrence_count_limit_is_respected():
    # nur 2 Vorkommen (06.07., 07.07.) - der 13.07. liegt danach -> nichts
    feed = _feed(_timed("1", "20260706T090000", "20260706T093000", "Kurz",
                        rrule="FREQ=DAILY;COUNT=2"))
    events = _client(feed).agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00")

    assert events == []


# --- Zeitzone, Robustheit ---------------------------------------------------

def test_utc_z_time_is_shifted_to_local():
    ev = ("BEGIN:VEVENT\r\nUID:3\r\nDTSTART:20260713T080000Z\r\n"
          "DTEND:20260713T090000Z\r\nSUMMARY:UTC-Termin\r\nEND:VEVENT\r\n")
    events = _client(_feed(ev)).agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00")

    assert len(events) == 1
    assert events[0]["start"] == "2026-07-13T10:00:00"   # Juli: UTC+2


def test_empty_feed_returns_no_events():
    assert _client(_feed()).agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00") == []


def test_folded_lines_are_unfolded():
    ev = ("BEGIN:VEVENT\r\nUID:4\r\n"
          "DTSTART;TZID=W. Europe Standard Time:20260713T100000\r\n"
          "DTEND;TZID=W. Europe Standard Time:20260713T110000\r\n"
          "SUMMARY:Sehr langer Titel der\r\n  umgebrochen wurde\r\nEND:VEVENT\r\n")
    events = _client(_feed(ev)).agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00")

    assert events[0]["subject"] == "Sehr langer Titel der umgebrochen wurde"


def test_fetch_failure_raises_grapherror():
    def boom(url: str) -> str:
        raise GraphError("Feed weg")

    client = IcsCalendarClient(ics_url="https://x.test/cal.ics", fetcher=boom)
    with pytest.raises(GraphError):
        client.agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00")


def test_feed_is_cached_between_calls():
    calls = {"n": 0}

    def counting(url: str) -> str:
        calls["n"] += 1
        return _feed(_timed("1", "20260713T100000", "20260713T110000", "X"))

    client = IcsCalendarClient(ics_url="https://x.test/cal.ics", fetcher=counting)
    client.agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00")
    client.agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00")

    assert calls["n"] == 1   # zweiter Aufruf aus dem Cache


# --- Command waehlt ICS, wenn URL gesetzt -----------------------------------

def test_configure_prefers_ics_when_url_set():
    import commands.calendar as cal

    class _Cfg:
        ms_calendar_ics_url = "https://x.test/cal.ics"
        ms_calendar_client_id = ""
        ms_calendar_refresh_token = ""

    cal.configure(_Cfg())
    assert isinstance(cal._client, IcsCalendarClient)
    cal.configure(None)   # aufraeumen: Kalender wieder aus
