"""
Kalender-Befehle (ADR-062 inkl. Nachtrag) - LESEN ueber ICS-Feed oder Graph,
SCHREIBEN (eintragen/verschieben/absagen) ueber Graph. Fail-safe:
ohne konfigurierten Zugang meldet der Befehl freundlich, dass der Kalender
noch nicht eingerichtet ist (kein Absturz).

Bestaetigungs-Diaet (PO 14.07.2026): eintragen/verschieben laufen SOFORT und
nennen den Rueckweg in der Antwort (Undo statt Rueckfrage, ADR-068); nur das
ABSAGEN fragt nach, weil es nach aussen sichtbar ist.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from core.graph_calendar import GraphAuthError, GraphCalendarClient, GraphError
from core.ics_calendar import IcsCalendarClient
from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.calendar")

# Lese-Client: Graph ODER ICS (beide teilen agenda(), daher Duck-Typing).
_client: Optional[object] = None
# Schreib-Client: NUR Graph (ICS ist read-only). Unabhaengig vom Lese-Weg -
# so kann man ueber ICS lesen und trotzdem ueber Graph schreiben.
_write_client: Optional[GraphCalendarClient] = None
_WEEKDAYS = {"montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
             "freitag": 4, "samstag": 5, "sonntag": 6}
_WEEKDAY_NAMES = ("Montag", "Dienstag", "Mittwoch", "Donnerstag",
                  "Freitag", "Samstag", "Sonntag")


def read_agenda(day: datetime) -> list[dict]:
    """Roh-Termine EINES Tages (fuer die proaktive Vorausschau, ADR-063).
    Leer, wenn kein Kalender konfiguriert oder ein Fehler auftritt - wirft NIE
    (die Vorausschau darf den Scheduler nie stoeren)."""
    if _client is None:
        return []
    start = day.strftime("%Y-%m-%dT00:00:00")
    end = (day + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")
    try:
        return _client.agenda(start, end)
    except Exception:  # noqa: BLE001 - fail-safe: lieber leer als Absturz
        logger.info("Vorausschau: Kalender nicht lesbar (fail-safe leer).")
        return []


def _graph_from_config(config) -> Optional[GraphCalendarClient]:
    """Graph-Client aus (client_id + refresh_token), sonst None."""
    cid = getattr(config, "ms_calendar_client_id", "") if config else ""
    rt = getattr(config, "ms_calendar_refresh_token", "") if config else ""
    if cid and rt:
        return GraphCalendarClient(
            client_id=cid, refresh_token=rt,
            tenant=getattr(config, "ms_calendar_tenant", "common") or "common",
        )
    return None


def configure(config, client: Optional[object] = None,
              write_client: Optional[GraphCalendarClient] = None) -> None:
    """Baut Lese- und Schreib-Client, wenn Zugang konfiguriert ist; sonst AUS.

    Lesen: Vorrang hat der veroeffentlichte ICS-Feed (ms_calendar_ics_url) -
    der einfache, OAuth-freie Weg fuer private Outlook-Konten; sonst Graph.
    Schreiben: NUR Graph (client_id + refresh_token) - ICS kann nicht schreiben.
    `client`/`write_client` erlauben Injektion im Test."""
    global _client, _write_client

    _write_client = write_client if write_client is not None else _graph_from_config(config)

    if client is not None:
        _client = client
        return
    ics_url = getattr(config, "ms_calendar_ics_url", "") if config else ""
    if ics_url:
        _client = IcsCalendarClient(ics_url=ics_url)
        return
    _client = _graph_from_config(config)


def _resolve_day(raw: str) -> datetime:
    """'heute'/'morgen'/'uebermorgen'/Wochentag/ISO-Datum -> Datum um 0 Uhr.
    Default: heute. Fail-safe (Unparsebares -> heute)."""
    s = (raw or "").strip().lower()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if not s or "heute" in s:
        return today
    if "übermorgen" in s or "uebermorgen" in s:
        return today + timedelta(days=2)
    if "morgen" in s:
        return today + timedelta(days=1)
    for name, wd in _WEEKDAYS.items():
        if name in s:
            return today + timedelta(days=((wd - today.weekday()) % 7) or 7)
    try:
        return datetime.fromisoformat(s[:10]).replace(hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        return today


def _day_label(day: datetime) -> str:
    delta = (day.date() - datetime.now().date()).days
    if delta == 0:
        return "Heute"
    if delta == 1:
        return "Morgen"
    if delta == 2:
        return "Übermorgen"
    if 2 < delta <= 6:
        return f"Am {_WEEKDAY_NAMES[day.weekday()]}"
    return f"Am {day.strftime('%d.%m.%Y')}"


def _event_time(ev: dict) -> str:
    if ev.get("all_day"):
        return "ganztägig"
    try:
        return datetime.fromisoformat(ev["start"][:19]).strftime("%H:%M")
    except (ValueError, KeyError, TypeError):
        return "?"


def _parse_time(raw: str) -> Optional["tuple[int, int]"]:
    """'14', '14:00', '14 Uhr', '9:30' -> (Stunde, Minute). None = ohne Zeit."""
    s = (raw or "").strip().lower().replace("uhr", "").replace(".", ":").strip()
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?$", s)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour, minute
    return None


def _build_event(plan: Plan) -> "tuple[Optional[dict], Optional[str]]":
    """Baut aus dem Plan die Termin-Felder ODER eine Klartext-Rueckfrage.
    Ohne Uhrzeit -> ganztaegig; mit Uhrzeit -> 1 Stunde (Standard)."""
    p = plan.parameters or {}
    subject = str(p.get("subject") or p.get("title") or plan.target or "").strip()
    if not subject:
        return None, "Wie soll der Termin heißen, Sir?"
    day = _resolve_day(str(p.get("day") or ""))
    location = str(p.get("location") or "").strip()
    hm = _parse_time(str(p.get("time") or ""))
    if hm is None:
        start_iso = day.strftime("%Y-%m-%dT00:00:00")
        end_iso = (day + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")
        all_day, time_label = True, "ganztägig"
    else:
        start = day.replace(hour=hm[0], minute=hm[1])
        start_iso = start.strftime("%Y-%m-%dT%H:%M:%S")
        end_iso = (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        all_day, time_label = False, f"{hm[0]:02d}:{hm[1]:02d}"
    return {
        "subject": subject, "start_iso": start_iso, "end_iso": end_iso,
        "location": location, "all_day": all_day,
        "label": _day_label(day), "time_label": time_label,
    }, None


class CalendarAgendaCommand:
    name = "calendar_agenda"
    description = (
        "Zeigt Termine aus dem (Outlook-)Kalender fuer EINEN Tag - 'was habe ich "
        "morgen?', 'was steht heute im Kalender?', 'welche Termine am Freitag?', "
        "'zeig meinen Kalender'. parameters.day = 'heute'/'morgen'/'uebermorgen', "
        "ein Wochentag oder ein ISO-Datum (Standard heute). NUR LESEN - legt "
        "nichts an. Abgrenzung: list_entries sind Jarvis' eigene Erinnerungen, "
        "calendar_agenda ist der echte Outlook-Kalender."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if _client is None:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=("Der Kalender ist noch nicht eingerichtet, Sir - dazu einmal "
                         "die Microsoft-Anbindung hinterlegen (siehe README: Kalender)."),
            )
        day = _resolve_day(str(plan.parameters.get("day") or plan.target or ""))
        start = day.strftime("%Y-%m-%dT00:00:00")
        end = (day + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")
        try:
            events = _client.agenda(start, end)
        except GraphAuthError:
            return Result(status=Status.FAILED, message=(
                "Der Kalender-Zugang ist abgelaufen, Sir - einmal neu anmelden "
                "(scripts/ms_calendar_auth.py)."))
        except GraphError:
            return Result(status=Status.FAILED,
                          message="Der Kalender ist gerade nicht erreichbar, Sir.")

        label = _day_label(day)
        if not events:
            return Result(status=Status.SUCCESS,
                          message=f"{label} steht nichts im Kalender, Sir — der Tag gehört dir.")
        lines = []
        for ev in events:
            loc = f" ({ev['location']})" if ev.get("location") else ""
            lines.append(f"• {_event_time(ev)} {ev['subject']}{loc}")
        return Result(
            status=Status.SUCCESS,
            message=f"{label} im Kalender, Sir:\n" + "\n".join(lines),
            data={"count": len(events)},
        )


def _event_when_label(ev: dict) -> str:
    """'Heute 09:00' / 'Am Freitag (ganztägig)' fuer Vorschau/Antwort."""
    try:
        dt = datetime.fromisoformat(str(ev["start"])[:19])
    except (ValueError, KeyError, TypeError):
        return "?"
    if ev.get("all_day"):
        return f"{_day_label(dt)} (ganztägig)"
    return f"{_day_label(dt)} {dt.strftime('%H:%M')}"


def _find_events(query: str, days_ahead: int = 14) -> list[dict]:
    """Sucht ueber den Graph-Schreib-Client (der liefert Termin-ids) kuenftige
    Termine, deren Titel `query` als Teilstring enthaelt. Fail-safe leer."""
    if _write_client is None:
        return []
    q = (query or "").strip().lower()
    if not q:
        return []
    now = datetime.now()
    start = now.strftime("%Y-%m-%dT00:00:00")
    end = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%dT00:00:00")
    try:
        events = _write_client.agenda(start, end)
    except Exception:  # noqa: BLE001 - fail-safe
        return []
    return [e for e in events if q in (e.get("subject") or "").lower()]


def _resolve_target(plan: Plan) -> "tuple[Optional[dict], Optional[str]]":
    """Findet den gemeinten Termin ODER liefert eine Klartext-Rueckfrage
    (nicht eingerichtet / nichts gefunden / mehrdeutig)."""
    if _write_client is None:
        return None, "Der Kalender ist zum Ändern noch nicht eingerichtet, Sir."
    p = plan.parameters or {}
    query = str(p.get("subject") or p.get("query") or plan.target or "").strip()
    if not query:
        return None, "Welchen Termin meinst du, Sir?"
    matches = _find_events(query)
    if not matches:
        return None, f"Ich finde in den nächsten zwei Wochen keinen Termin «{query}», Sir."
    if len(matches) > 1:
        opts = "; ".join(f"«{m['subject']}» ({_event_when_label(m)})" for m in matches[:4])
        return None, f"Mehrere Termine passen auf «{query}», Sir: {opts}. Welchen genau?"
    return matches[0], None


class CreateCalendarEventCommand:
    name = "calendar_add_event"
    description = (
        "Traegt einen NEUEN Termin in den echten (Outlook-)Kalender ein - "
        "'trag mir morgen 14 Uhr Zahnarzt ein', 'mach mir Freitag 9 Uhr Meeting', "
        "'setz mir Dienstag Urlaub in den Kalender'. parameters.subject = Titel "
        "des Termins, parameters.day = 'heute'/'morgen'/'uebermorgen', ein "
        "Wochentag oder ISO-Datum, parameters.time = 'HH:MM' (optional; ohne Zeit "
        "= ganztaegig), parameters.location = Ort (optional). Traegt SOFORT ein "
        "und nennt den Rueckweg - umkehrbar per Verschieben/Absagen (ADR-068, "
        "PO 14.07.). Abgrenzung: add_entry ist Jarvis' eigene Erinnerung, "
        "calendar_add_event ist der echte Outlook-Kalender."
    )
    requires_confirmation = False

    def preview(self, plan: Plan) -> Optional[str]:
        """Bestaetigungs-Vorschau (ADR-023): der PO bestaetigt einen KONKRETEN
        Termin, keine Blackbox. Fehler werden zur ehrlichen 'sag Nein'-Empfehlung."""
        if _write_client is None:
            return ("Der Kalender ist zum Eintragen noch nicht eingerichtet, Sir - "
                    "am besten mit Nein antworten.")
        event, err = _build_event(plan)
        if err:
            return f"{err} (mit Nein antworten und es mir nochmal sagen)"
        loc = f" ({event['location']})" if event["location"] else ""
        return (f"Ich trage in den Outlook-Kalender ein: {event['subject']} — "
                f"{event['label']} {event['time_label']}{loc}. Eintragen?")

    def execute(self, plan: Plan) -> Result:
        if _write_client is None:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=("Der Kalender ist zum Eintragen noch nicht eingerichtet, Sir - "
                         "dazu einmal die Microsoft-Schreibanbindung hinterlegen."))
        event, err = _build_event(plan)
        if err:
            return Result(status=Status.NEEDS_CLARIFICATION, message=err)
        try:
            _write_client.create_event(
                event["subject"], event["start_iso"], event["end_iso"],
                event["location"], event["all_day"])
        except GraphAuthError:
            return Result(status=Status.FAILED, message=(
                "Der Kalender-Zugang ist abgelaufen, Sir - einmal neu anmelden "
                "(scripts/ms_calendar_auth_localhost.py)."))
        except GraphError:
            return Result(status=Status.FAILED,
                          message="Ich konnte den Termin gerade nicht anlegen, Sir.")
        loc = f" ({event['location']})" if event["location"] else ""
        # Undo statt Rueckfrage (ADR-068, PO 14.07.): sofort tun, Rueckweg nennen.
        return Result(
            status=Status.SUCCESS,
            message=(f"Eingetragen, Sir: {event['subject']} — {event['label']} "
                     f"{event['time_label']}{loc}. (Passt es nicht: "
                     f"«verschieb {event['subject']}» oder «sag {event['subject']} ab».)"),
            data={"subject": event["subject"]},
        )


class MoveCalendarEventCommand:
    name = "calendar_move_event"
    description = (
        "Verschiebt einen bestehenden Termin im (Outlook-)Kalender auf eine neue "
        "Zeit - 'verschieb den Zahnarzt auf 15 Uhr', 'mach das Meeting auf morgen "
        "10 Uhr'. parameters.subject = Stichwort des Termins, parameters.time = neue "
        "Uhrzeit 'HH:MM' (noetig), parameters.day = neuer Tag (optional, sonst "
        "gleicher Tag). Verschiebt SOFORT und nennt den Rueckweg - umkehrbar "
        "durch Zurueckschieben (ADR-068, PO 14.07.)."
    )
    requires_confirmation = False

    def _plan_move(self, plan: Plan) -> "tuple[Optional[dict], Optional[str]]":
        event, err = _resolve_target(plan)
        if err:
            return None, err
        hm = _parse_time(str((plan.parameters or {}).get("time") or ""))
        if hm is None:
            return None, "Auf welche Uhrzeit soll ich verschieben, Sir?"
        try:
            old_start = datetime.fromisoformat(str(event["start"])[:19])
            old_end = datetime.fromisoformat(str(event["end"])[:19])
        except (ValueError, KeyError, TypeError):
            return None, "Der Termin hat keine lesbare Zeit, Sir."
        duration = old_end - old_start if old_end > old_start else timedelta(hours=1)
        day_param = str((plan.parameters or {}).get("day") or "").strip()
        base_day = _resolve_day(day_param) if day_param else old_start
        new_start = base_day.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        return {
            "event": event, "new_start": new_start, "new_end": new_start + duration,
            "old_label": _event_when_label(event),
            "new_label": f"{_day_label(new_start)} {new_start.strftime('%H:%M')}",
        }, None

    def preview(self, plan: Plan) -> Optional[str]:
        info, err = self._plan_move(plan)
        if err:
            return f"{err} (am besten mit Nein antworten)"
        return (f"Ich verschiebe «{info['event']['subject']}» von {info['old_label']} "
                f"auf {info['new_label']}. Verschieben?")

    def execute(self, plan: Plan) -> Result:
        info, err = self._plan_move(plan)
        if err:
            return Result(status=Status.NEEDS_CLARIFICATION, message=err)
        try:
            _write_client.update_event(
                info["event"]["id"],
                start_iso=info["new_start"].strftime("%Y-%m-%dT%H:%M:%S"),
                end_iso=info["new_end"].strftime("%Y-%m-%dT%H:%M:%S"))
        except GraphAuthError:
            return Result(status=Status.FAILED, message=(
                "Der Kalender-Zugang ist abgelaufen, Sir - einmal neu anmelden."))
        except GraphError:
            return Result(status=Status.FAILED,
                          message="Ich konnte den Termin gerade nicht verschieben, Sir.")
        # Undo statt Rueckfrage (ADR-068): der alte Zeitpunkt steht in der
        # Antwort - der Rueckweg ist damit ein Satz.
        return Result(
            status=Status.SUCCESS,
            message=(f"Verschoben, Sir: «{info['event']['subject']}» ist jetzt "
                     f"{info['new_label']} (vorher {info['old_label']} — sag es, "
                     f"falls ich zurückschieben soll)."),
            data={"subject": info["event"]["subject"]})


class CancelCalendarEventCommand:
    name = "calendar_cancel_event"
    description = (
        "Sagt einen bestehenden Termin im (Outlook-)Kalender ab bzw. loescht ihn - "
        "'sag den Zahnarzt ab', 'loesch das Meeting morgen', 'streich den Termin um "
        "15 Uhr'. parameters.subject = Stichwort des Termins. LOESCHT aus dem "
        "Kalender - Sicherheitsstufe 2, wird immer erst bestaetigt."
    )
    requires_confirmation = True

    def preview(self, plan: Plan) -> Optional[str]:
        event, err = _resolve_target(plan)
        if err:
            return f"{err} (am besten mit Nein antworten)"
        return f"Ich sage «{event['subject']}» ({_event_when_label(event)}) ab. Wirklich löschen?"

    def execute(self, plan: Plan) -> Result:
        event, err = _resolve_target(plan)
        if err:
            return Result(status=Status.NEEDS_CLARIFICATION, message=err)
        label = _event_when_label(event)
        try:
            _write_client.delete_event(event["id"])
        except GraphAuthError:
            return Result(status=Status.FAILED, message=(
                "Der Kalender-Zugang ist abgelaufen, Sir - einmal neu anmelden."))
        except GraphError:
            return Result(status=Status.FAILED,
                          message="Ich konnte den Termin gerade nicht absagen, Sir.")
        return Result(
            status=Status.SUCCESS,
            message=f"Abgesagt, Sir: «{event['subject']}» ({label}) ist aus dem Kalender.",
            data={"subject": event["subject"]})


COMMANDS = [
    CalendarAgendaCommand(),
    CreateCalendarEventCommand(),
    MoveCalendarEventCommand(),
    CancelCalendarEventCommand(),
]
