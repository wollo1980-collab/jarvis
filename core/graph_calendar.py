"""
Outlook/Microsoft-365-Kalender-Connector (ADR-062 inkl. Nachtrag) - Jarvis
liest UND schreibt den echten Kalender des Nutzers ueber die Microsoft-Graph-
API (Scope Calendars.ReadWrite): Agenda lesen, Termine anlegen/verschieben/
absagen. In der Live-Verdrahtung ist Graph vor allem der SCHREIB-Weg; gelesen
wird meist ueber den ICS-Feed (core/ics_calendar.py, getrennte Clients).

Sicherheits-Rahmen: die Commands (commands/calendar.py) entscheiden ueber
Rueckfragen - seit der Bestaetigungs-Diaet (PO 14.07.2026) laufen anlegen/
verschieben sofort mit Undo-Hinweis, absagen fragt. Dieser Connector selbst
tut nur, was der Command anweist.

Auth: Microsoft-Identity-Refresh-Token-Flow, EINMALIG per
scripts/ms_calendar_auth_localhost.py eingerichtet (Loopback/PKCE - der
Geraete-Code-Weg aus ms_calendar_auth.py scheitert an Privatkonten). Zur
Laufzeit tauscht der Client den refresh_token gegen kurzlebige access_token -
kein weiterer Login. refresh_token ist ein Secret (Config, nie im Repo).

stdlib-only; die HTTP-Schicht (_http) ist injizierbar, damit Tests ohne
Netzwerk/echten Account laufen (gleiches Muster wie Spotify-/Wetter-Connector).
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

logger = logging.getLogger("jarvis.graph_calendar")

_TOKEN_URL_TMPL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_SCOPE = "https://graph.microsoft.com/Calendars.ReadWrite offline_access"
_TOKEN_REFRESH_MARGIN = 30.0


class GraphError(Exception):
    """Basisfehler des Connectors - der Command uebersetzt ihn in Klartext."""


class GraphAuthError(GraphError):
    """Token ungueltig/abgelaufen oder Rechte fehlen (Neu-Einrichtung noetig)."""


# (status_code, body_bytes) - die injizierbare HTTP-Schicht liefert genau das.
HttpFn = Callable[[str, str, dict, Optional[bytes]], "tuple[int, bytes]"]


def _default_http(method: str, url: str, headers: dict, body: Optional[bytes]) -> "tuple[int, bytes]":
    """Echte HTTP-Schicht (urllib). Liefert (status, bytes) auch bei 4xx/5xx,
    statt zu werfen - die Fachlogik entscheidet anhand des Status."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if hasattr(e, "read") else b""


class GraphCalendarClient:
    """Duenner Client um die paar Kalender-Lese-Endpunkte, die Jarvis braucht.
    access_token wird gecacht und rechtzeitig erneuert. tenant='common' fuer
    persoenliche + Arbeits-Konten (bzw. 'consumers'/eine Tenant-ID)."""

    def __init__(
        self,
        client_id: str,
        refresh_token: str,
        tenant: str = "common",
        timezone: str = "Europe/Berlin",
        http: Optional[HttpFn] = None,
    ):
        self._cid = client_id
        self._rt = refresh_token
        self._tenant = tenant or "common"
        self._tz = timezone or "Europe/Berlin"
        self._http: HttpFn = http or _default_http
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    # --- Auth ---------------------------------------------------------------

    def _access_token(self) -> str:
        if self._token and time.monotonic() < self._token_expiry - _TOKEN_REFRESH_MARGIN:
            return self._token
        body = urllib.parse.urlencode({
            "client_id": self._cid,
            "grant_type": "refresh_token",
            "refresh_token": self._rt,
            "scope": _SCOPE,
        }).encode()
        status, data = self._http(
            "POST", _TOKEN_URL_TMPL.format(tenant=self._tenant),
            {"Content-Type": "application/x-www-form-urlencoded"}, body,
        )
        if status != 200:
            raise GraphAuthError(
                f"Token-Erneuerung fehlgeschlagen (HTTP {status}) - Kalender neu einrichten?"
            )
        payload = json.loads(data or b"{}") or {}
        token = payload.get("access_token")
        if not token:
            raise GraphAuthError("Microsoft lieferte keinen access_token.")
        # Ein evtl. rotierter refresh_token wird uebernommen (MS rotiert sie).
        if payload.get("refresh_token"):
            self._rt = payload["refresh_token"]
        self._token = token
        self._token_expiry = time.monotonic() + float(payload.get("expires_in", 3600))
        return token

    # --- Low-level API ------------------------------------------------------

    def _api(self, method: str, path: str, params: Optional[dict] = None) -> "tuple[int, bytes]":
        token = self._access_token()
        url = _GRAPH_BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        status, data = self._http(
            method, url,
            {"Authorization": f"Bearer {token}",
             "Prefer": f'outlook.timezone="{self._tz}"'},
            None,
        )
        if status == 401:
            raise GraphAuthError("Kalender-Token abgelehnt (401) - neu einrichten?")
        if status >= 400:
            raise GraphError(f"Kalender-Fehler (HTTP {status}).")
        return status, data

    # --- Kalender lesen -----------------------------------------------------

    def agenda(self, start_iso: str, end_iso: str) -> list[dict]:
        """Termine im Fenster [start_iso, end_iso) (lokale ISO-Zeit ohne Zone,
        z. B. '2026-07-13T00:00:00'). Liefert je Termin {subject, start, end,
        location, all_day}, aufsteigend nach Start."""
        status, data = self._api("GET", "/me/calendarView", params={
            "startDateTime": start_iso,
            "endDateTime": end_iso,
            "$orderby": "start/dateTime",
            "$top": "50",
            "$select": "id,subject,start,end,location,isAllDay",
        })
        items = (json.loads(data or b"{}") or {}).get("value", []) if data else []
        events: list[dict] = []
        for it in items:
            events.append({
                "id": it.get("id", ""),
                "subject": (it.get("subject") or "").strip() or "(ohne Titel)",
                "start": (it.get("start") or {}).get("dateTime", ""),
                "end": (it.get("end") or {}).get("dateTime", ""),
                "location": (it.get("location") or {}).get("displayName", "") or "",
                "all_day": bool(it.get("isAllDay")),
            })
        return events

    # --- Kalender schreiben (Sicherheitsstufe 2, immer nach Bestaetigung) ----

    def create_event(self, subject: str, start_iso: str, end_iso: str,
                     location: str = "", all_day: bool = False) -> dict:
        """Legt EINEN Termin an (POST /me/events). start_iso/end_iso sind lokale
        ISO-Zeit ohne Zone (z. B. '2026-07-13T14:00:00'); die Zone kommt aus
        self._tz. Wird NUR nach PO-Bestaetigung aufgerufen (der Command traegt
        requires_confirmation). Liefert {id, subject, web_link}."""
        token = self._access_token()
        payload: dict = {
            "subject": (subject or "").strip() or "(ohne Titel)",
            "start": {"dateTime": start_iso, "timeZone": self._tz},
            "end": {"dateTime": end_iso, "timeZone": self._tz},
            "isAllDay": bool(all_day),
        }
        if location.strip():
            payload["location"] = {"displayName": location.strip()}
        status, data = self._http(
            "POST", _GRAPH_BASE + "/me/events",
            {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json.dumps(payload).encode(),
        )
        if status == 401:
            raise GraphAuthError("Kalender-Token abgelehnt (401) - neu einrichten?")
        if status >= 400:
            raise GraphError(f"Termin anlegen fehlgeschlagen (HTTP {status}).")
        obj = json.loads(data or b"{}") or {}
        return {"id": obj.get("id", ""), "subject": obj.get("subject", ""),
                "web_link": obj.get("webLink", "")}

    def update_event(self, event_id: str, start_iso: Optional[str] = None,
                     end_iso: Optional[str] = None, subject: Optional[str] = None,
                     location: Optional[str] = None) -> dict:
        """Aendert Felder eines Termins (PATCH /me/events/{id}). Nur uebergebene
        Felder werden geschrieben. Wird NUR nach Bestaetigung aufgerufen."""
        if not event_id:
            raise GraphError("Kein Termin-Bezug (id) zum Aendern.")
        token = self._access_token()
        payload: dict = {}
        if start_iso is not None:
            payload["start"] = {"dateTime": start_iso, "timeZone": self._tz}
        if end_iso is not None:
            payload["end"] = {"dateTime": end_iso, "timeZone": self._tz}
        if subject is not None:
            payload["subject"] = subject
        if location is not None:
            payload["location"] = {"displayName": location}
        status, data = self._http(
            "PATCH", f"{_GRAPH_BASE}/me/events/{urllib.parse.quote(event_id)}",
            {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json.dumps(payload).encode(),
        )
        if status == 401:
            raise GraphAuthError("Kalender-Token abgelehnt (401) - neu einrichten?")
        if status >= 400:
            raise GraphError(f"Termin aendern fehlgeschlagen (HTTP {status}).")
        obj = json.loads(data or b"{}") or {}
        return {"id": obj.get("id", ""), "subject": obj.get("subject", "")}

    def delete_event(self, event_id: str) -> None:
        """Loescht einen Termin (DELETE /me/events/{id}). NUR nach Bestaetigung."""
        if not event_id:
            raise GraphError("Kein Termin-Bezug (id) zum Loeschen.")
        token = self._access_token()
        status, _ = self._http(
            "DELETE", f"{_GRAPH_BASE}/me/events/{urllib.parse.quote(event_id)}",
            {"Authorization": f"Bearer {token}"}, None,
        )
        if status == 401:
            raise GraphAuthError("Kalender-Token abgelehnt (401) - neu einrichten?")
        if status >= 400 and status != 404:   # 404 = schon weg -> als Erfolg behandeln
            raise GraphError(f"Termin absagen fehlgeschlagen (HTTP {status}).")
