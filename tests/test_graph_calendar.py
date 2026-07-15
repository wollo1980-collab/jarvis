"""Tests fuer core/graph_calendar.py (ADR-062) - die HTTP-Schicht ist
injiziert, kein Netz/echter Account. Muster wie test_spotify."""
from __future__ import annotations

import json

import pytest

from core.graph_calendar import GraphAuthError, GraphCalendarClient, GraphError

_TOKEN_OK = json.dumps({"access_token": "AT", "expires_in": 3600}).encode()


def _http(token_status=200, calendar_payload=None, calendar_status=200):
    """Baut eine HTTP-Attrappe: Token-Endpoint + calendarView."""
    def http(method, url, headers, body):
        if "oauth2" in url:
            return token_status, _TOKEN_OK if token_status == 200 else b'{"error":"invalid_grant"}'
        if "calendarView" in url:
            return calendar_status, json.dumps(calendar_payload or {"value": []}).encode()
        return 404, b""
    return http


def test_agenda_parses_events():
    payload = {"value": [
        {"subject": "Steuerberater",
         "start": {"dateTime": "2026-07-13T09:00:00.0000000"},
         "end": {"dateTime": "2026-07-13T10:00:00.0000000"},
         "location": {"displayName": "Büro"}, "isAllDay": False},
        {"subject": "", "start": {"dateTime": "2026-07-13T00:00:00.0"},
         "end": {"dateTime": "2026-07-14T00:00:00.0"}, "isAllDay": True},
    ]}
    client = GraphCalendarClient("cid", "rt", http=_http(calendar_payload=payload))

    events = client.agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00")

    assert len(events) == 2
    assert events[0]["subject"] == "Steuerberater"
    assert events[0]["start"].startswith("2026-07-13T09:00")
    assert events[0]["location"] == "Büro"
    assert events[1]["subject"] == "(ohne Titel)"   # leerer Titel -> Fallback
    assert events[1]["all_day"] is True


def test_token_failure_raises_auth_error():
    client = GraphCalendarClient("cid", "rt", http=_http(token_status=400))
    with pytest.raises(GraphAuthError):
        client.agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00")


def test_create_event_posts_json_and_returns_id():
    captured = {}

    def http(method, url, headers, body):
        if "oauth2" in url:
            return 200, _TOKEN_OK
        if url.endswith("/me/events") and method == "POST":
            captured["body"] = json.loads(body)
            captured["ct"] = headers.get("Content-Type")
            return 201, json.dumps({"id": "AAA", "subject": "Zahnarzt",
                                    "webLink": "https://x"}).encode()
        return 404, b""

    client = GraphCalendarClient("cid", "rt", http=http)
    res = client.create_event("Zahnarzt", "2026-07-13T14:00:00",
                              "2026-07-13T15:00:00", "Praxis", False)

    assert res["id"] == "AAA"
    assert captured["ct"] == "application/json"
    assert captured["body"]["subject"] == "Zahnarzt"
    assert captured["body"]["start"]["dateTime"] == "2026-07-13T14:00:00"
    assert captured["body"]["location"]["displayName"] == "Praxis"
    assert captured["body"]["isAllDay"] is False


def test_create_event_http_error_raises_grapherror():
    def http(method, url, headers, body):
        if "oauth2" in url:
            return 200, _TOKEN_OK
        return 403, b'{"error":"forbidden"}'

    client = GraphCalendarClient("cid", "rt", http=http)
    with pytest.raises(GraphError):
        client.create_event("X", "2026-07-13T14:00:00", "2026-07-13T15:00:00")


def test_agenda_includes_event_id():
    payload = {"value": [{"id": "XYZ", "subject": "A",
                          "start": {"dateTime": "2026-07-13T09:00:00"},
                          "end": {"dateTime": "2026-07-13T10:00:00"}, "isAllDay": False}]}
    client = GraphCalendarClient("cid", "rt", http=_http(calendar_payload=payload))

    events = client.agenda("2026-07-13T00:00:00", "2026-07-14T00:00:00")

    assert events[0]["id"] == "XYZ"


def test_update_event_patches_only_given_fields():
    captured = {}

    def http(method, url, headers, body):
        if "oauth2" in url:
            return 200, _TOKEN_OK
        if "/me/events/" in url and method == "PATCH":
            captured["url"] = url
            captured["body"] = json.loads(body)
            return 200, json.dumps({"id": "E1", "subject": "Zahnarzt"}).encode()
        return 404, b""

    client = GraphCalendarClient("cid", "rt", http=http)
    res = client.update_event("E1", start_iso="2026-07-13T15:00:00",
                              end_iso="2026-07-13T15:30:00")

    assert res["id"] == "E1"
    assert "E1" in captured["url"]
    assert captured["body"]["start"]["dateTime"] == "2026-07-13T15:00:00"
    assert "subject" not in captured["body"]   # nicht uebergeben -> nicht geschrieben


def test_delete_event_tolerates_404():
    seen = {}

    def http(method, url, headers, body):
        if "oauth2" in url:
            return 200, _TOKEN_OK
        seen["method"] = method
        return 404, b""   # schon weg -> als Erfolg behandeln

    client = GraphCalendarClient("cid", "rt", http=http)
    client.delete_event("E1")   # darf NICHT werfen
    assert seen["method"] == "DELETE"


def test_delete_event_real_error_raises():
    def http(method, url, headers, body):
        if "oauth2" in url:
            return 200, _TOKEN_OK
        return 403, b""

    client = GraphCalendarClient("cid", "rt", http=http)
    with pytest.raises(GraphError):
        client.delete_event("E1")


def test_access_token_is_cached_across_calls():
    calls = {"token": 0}

    def http(method, url, headers, body):
        if "oauth2" in url:
            calls["token"] += 1
            return 200, _TOKEN_OK
        return 200, b'{"value": []}'

    client = GraphCalendarClient("cid", "rt", http=http)
    client.agenda("a", "b")
    client.agenda("a", "b")

    assert calls["token"] == 1   # Token nur EINMAL geholt, dann gecacht
