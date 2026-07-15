"""
ICS-Kalender-Connector (ADR-062, read-first) - Fallback zum Graph-Connector.

Warum: Microsofts App-Registrierung/OAuth ist mit PRIVATEN Microsoft-Konten
sehr zaeh (Geraete-Code laeuft nicht durch, Auth-Code landet auf Fehlerseiten).
Outlook.com kann einen Kalender stattdessen als veroeffentlichten ICS-Feed
bereitstellen - eine schlichte, read-only Abo-Adresse. Jarvis liest sie und
beantwortet daraus "was habe ich morgen?" - ganz ohne OAuth.

READ-FIRST: nur lesen. Der Feed IST nur-lesbar; Anlegen bleibt (spaeter) dem
Graph-Weg vorbehalten. Der Feed-Inhalt ist DATEN, nie Anweisung (ADR-061 I2).

Gleiche Schnittstelle wie GraphCalendarClient (`agenda(start_iso, end_iso)` ->
Liste {subject, start, end, location, all_day}), damit commands/calendar.py den
Connector wahlweise nutzen kann. stdlib-only; die Abruf-Schicht (`fetcher`) ist
injizierbar, damit Tests ohne Netz laufen.
"""
from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Callable, Optional

from core.graph_calendar import GraphError

logger = logging.getLogger("jarvis.ics_calendar")

_USER_AGENT = "Mozilla/5.0 (compatible; Jarvis/1.0; +https://local.invalid)"
_CACHE_SECONDS = 120.0          # Feed hoechstens alle 2 Min neu holen (er hinkt ohnehin nach)
_MAX_OCCURRENCE_ITERS = 2000    # harte Obergrenze gegen Endlos-Wiederholungen
_WEEKDAY_CODES = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}

# Fetcher: URL -> ICS-Rohtext. Wirft bei Netzfehler (der Client uebersetzt das).
FetchFn = Callable[[str], str]


def _default_fetch(url: str) -> str:
    """Holt den ICS-Feed (read-only). Wirft GraphError bei Netzproblemen, damit
    commands/calendar.py denselben Fehlerzweig wie beim Graph-Weg nutzt."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read(4_000_000)
            charset = "utf-8"
            get_charset = getattr(resp.headers, "get_content_charset", None)
            if callable(get_charset):
                charset = get_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
    except (urllib.error.URLError, OSError) as e:
        raise GraphError(f"ICS-Feed nicht erreichbar: {e}") from e


# --- ICS-Parsing (klein gehalten, nur was Jarvis braucht) -------------------

def _unfold(text: str) -> list[str]:
    """RFC5545-Zeilenentfaltung: Fortsetzungszeilen beginnen mit Space/Tab."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n ", "").replace("\n\t", "")
    return text.split("\n")


def _split_prop(line: str) -> "tuple[str, dict, str]":
    """'DTSTART;TZID=...:20260706T063000' -> ('DTSTART', {'TZID': '...'}, wert)."""
    head, _, value = line.partition(":")
    parts = head.split(";")
    name = parts[0].upper()
    params: dict[str, str] = {}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        params[k.upper()] = v
    return name, params, value.strip()


def _berlin_offset(dt: datetime) -> timedelta:
    """Grobe Europe/Berlin-Verschiebung (Sommerzeit ~Apr-Okt = +2, sonst +1).
    Bewusst ohne zoneinfo (auf Windows oft ohne IANA-Datenbank). Nur fuer die
    seltenen UTC-'Z'-Werte noetig; getaktete Termine kommen als lokale Wandzeit."""
    return timedelta(hours=2 if 4 <= dt.month <= 10 else 1)


def _parse_dt(params: dict, value: str) -> "tuple[Optional[datetime], bool]":
    """ICS-Datum/Zeit -> (naive lokale datetime, all_day?). None bei Unparsebarem."""
    value = value.strip()
    if not value:
        return None, False
    if params.get("VALUE") == "DATE" or (len(value) == 8 and value.isdigit()):
        try:
            return datetime.strptime(value[:8], "%Y%m%d"), True
        except ValueError:
            return None, True
    is_utc = value.endswith("Z")
    core = value[:-1] if is_utc else value
    try:
        dt = datetime.strptime(core[:15], "%Y%m%dT%H%M%S")
    except ValueError:
        return None, False
    if is_utc:                       # UTC -> lokale Wandzeit (Berlin)
        dt = dt + _berlin_offset(dt)
    return dt, False


def _parse_rrule(value: str) -> dict:
    out: dict = {}
    for part in value.split(";"):
        k, _, v = part.partition("=")
        out[k.upper()] = v
    return out


def _step(occ: datetime, freq: str, interval: int) -> datetime:
    if freq == "DAILY":
        return occ + timedelta(days=interval)
    if freq == "WEEKLY":
        return occ + timedelta(weeks=interval)
    if freq == "MONTHLY":
        month = occ.month - 1 + interval
        year = occ.year + month // 12
        month = month % 12 + 1
        day = min(occ.day, 28)       # simpel & sicher (kein 31.-Ueberlauf)
        return occ.replace(year=year, month=month, day=day)
    if freq == "YEARLY":
        try:
            return occ.replace(year=occ.year + interval)
        except ValueError:           # 29.02.
            return occ.replace(year=occ.year + interval, day=28)
    return occ + timedelta(days=interval)


def _occurrences(
    dtstart: datetime, duration: timedelta, rrule: Optional[dict],
    win_start: datetime, win_end: datetime,
) -> list["tuple[datetime, datetime]"]:
    """Alle (start, end)-Vorkommen, die das Fenster [win_start, win_end)
    schneiden - inkl. einfacher Wiederholungen (DAILY/WEEKLY/MONTHLY/YEARLY,
    INTERVAL/COUNT/UNTIL, BYDAY bei WEEKLY)."""
    if not rrule:
        if dtstart < win_end and dtstart + duration > win_start:
            return [(dtstart, dtstart + duration)]
        return []

    freq = rrule.get("FREQ", "").upper()
    interval = max(1, int(rrule.get("INTERVAL", "1") or "1"))
    count = int(rrule["COUNT"]) if rrule.get("COUNT", "").isdigit() else None
    until, _ = _parse_dt({}, rrule.get("UNTIL", "")) if rrule.get("UNTIL") else (None, False)
    byday = [_WEEKDAY_CODES[c] for c in rrule.get("BYDAY", "").split(",") if c in _WEEKDAY_CODES]

    results: list["tuple[datetime, datetime]"] = []
    emitted = 0

    if freq == "WEEKLY" and byday:
        week0 = dtstart - timedelta(days=dtstart.weekday())
        if count is None and win_start > week0:          # zum Fenster vorspulen
            weeks = ((win_start - week0).days // 7) // interval
            week0 = week0 + timedelta(weeks=weeks * interval)
        iters = 0
        while iters < _MAX_OCCURRENCE_ITERS:
            iters += 1
            week_start = week0 + timedelta(weeks=iters - 1) if interval == 1 else \
                week0 + timedelta(weeks=(iters - 1) * interval)
            if week_start > win_end + timedelta(days=7):
                break
            for wd in sorted(byday):
                occ = (week_start + timedelta(days=wd)).replace(
                    hour=dtstart.hour, minute=dtstart.minute, second=dtstart.second)
                if occ < dtstart:
                    continue
                if until and occ > until:
                    return results
                if count is not None and emitted >= count:
                    return results
                emitted += 1
                if occ < win_end and occ + duration > win_start:
                    results.append((occ, occ + duration))
        return results

    occ = dtstart
    if count is None and freq in ("DAILY", "WEEKLY") and occ < win_start:
        step_days = interval * (7 if freq == "WEEKLY" else 1)
        jumps = (win_start - occ).days // step_days
        if jumps > 0:
            occ = occ + timedelta(days=jumps * step_days)
    iters = 0
    while iters < _MAX_OCCURRENCE_ITERS:
        iters += 1
        if until and occ > until:
            break
        if count is not None and emitted >= count:
            break
        emitted += 1
        if occ < win_end and occ + duration > win_start:
            results.append((occ, occ + duration))
        if occ >= win_end:
            break
        occ = _step(occ, freq, interval)
    return results


def _parse_events(text: str) -> list[dict]:
    """ICS-Rohtext -> Roh-Termine [{summary, location, dtstart, dtend, all_day,
    rrule}]. Reihenfolge wie im Feed."""
    events: list[dict] = []
    cur: Optional[dict] = None
    for line in _unfold(text):
        if line.startswith("BEGIN:VEVENT"):
            cur = {"summary": "", "location": "", "dtstart": None, "dtend": None,
                   "all_day": False, "rrule": None}
            continue
        if line.startswith("END:VEVENT"):
            if cur and cur["dtstart"] is not None:
                events.append(cur)
            cur = None
            continue
        if cur is None or ":" not in line:
            continue
        name, params, value = _split_prop(line)
        if name == "SUMMARY":
            cur["summary"] = value
        elif name == "LOCATION":
            cur["location"] = value
        elif name == "DTSTART":
            dt, allday = _parse_dt(params, value)
            cur["dtstart"], cur["all_day"] = dt, cur["all_day"] or allday
        elif name == "DTEND":
            dt, allday = _parse_dt(params, value)
            cur["dtend"], cur["all_day"] = dt, cur["all_day"] or allday
        elif name == "RRULE":
            cur["rrule"] = _parse_rrule(value)
        elif name == "X-MICROSOFT-CDO-ALLDAYEVENT" and value.upper() == "TRUE":
            cur["all_day"] = True
    return events


class IcsCalendarClient:
    """Liest einen veroeffentlichten Outlook-ICS-Feed. Gleiche Schnittstelle wie
    GraphCalendarClient, damit der Command beide gleich nutzt. Kleiner Cache, weil
    der Feed ohnehin nur periodisch aktualisiert wird."""

    def __init__(self, ics_url: str, fetcher: Optional[FetchFn] = None,
                 cache_seconds: float = _CACHE_SECONDS):
        self._url = ics_url
        self._fetch: FetchFn = fetcher or _default_fetch
        self._cache_seconds = cache_seconds
        self._cache_text: Optional[str] = None
        self._cache_time = 0.0

    def _raw(self) -> str:
        now = time.monotonic()
        if self._cache_text is not None and now - self._cache_time < self._cache_seconds:
            return self._cache_text
        text = self._fetch(self._url)
        self._cache_text = text
        self._cache_time = now
        return text

    def agenda(self, start_iso: str, end_iso: str) -> list[dict]:
        """Termine im Fenster [start_iso, end_iso) (lokale ISO-Zeit ohne Zone).
        Liefert je Termin {subject, start, end, location, all_day}, nach Start."""
        try:
            win_start = datetime.fromisoformat(start_iso[:19])
            win_end = datetime.fromisoformat(end_iso[:19])
        except ValueError as e:
            raise GraphError(f"Ungueltiges Kalender-Fenster: {e}") from e

        out: list[dict] = []
        for ev in _parse_events(self._raw()):
            dtstart: datetime = ev["dtstart"]
            dtend: Optional[datetime] = ev["dtend"]
            if ev["all_day"]:
                # Ganztags: DTEND ist exklusiv (Folgetag 0 Uhr); mind. ein Tag.
                span_end = dtend or (dtstart + timedelta(days=1))
                if dtstart < win_end and span_end > win_start:
                    out.append({
                        "subject": ev["summary"].strip() or "(ohne Titel)",
                        "start": dtstart.strftime("%Y-%m-%dT00:00:00"),
                        "end": span_end.strftime("%Y-%m-%dT00:00:00"),
                        "location": ev["location"].strip(),
                        "all_day": True,
                        "_sort": dtstart,
                    })
                continue
            duration = (dtend - dtstart) if (dtend and dtend > dtstart) else timedelta(hours=1)
            for occ_start, occ_end in _occurrences(dtstart, duration, ev["rrule"], win_start, win_end):
                out.append({
                    "subject": ev["summary"].strip() or "(ohne Titel)",
                    "start": occ_start.strftime("%Y-%m-%dT%H:%M:%S"),
                    "end": occ_end.strftime("%Y-%m-%dT%H:%M:%S"),
                    "location": ev["location"].strip(),
                    "all_day": False,
                    "_sort": occ_start,
                })
        out.sort(key=lambda e: e["_sort"])
        for e in out:
            e.pop("_sort", None)
        return out
