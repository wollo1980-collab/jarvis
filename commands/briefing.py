"""
Morgen-Briefing (Ziellinie v1.5 Punkt 3, Nachtplan 11.07.2026) - "Briefing"
/ "wie sieht mein Tag aus?" komponiert EINEN sprechtauglichen Ueberblick
aus den echten Quellen des Tages: Eintraege (heute faellig + naechste,
inkl. Wiederholungs-Marker), Wetter (kurz), Listen-Stand, Top-3-Lage.

Grundsaetze:
- Jede Quelle ist fail-safe: faellt sie aus (kein Netz, kein Ort
  konfiguriert), entfaellt ihr Abschnitt - das Briefing kommt trotzdem.
- Nur auf ZURUF (Stufe 0, read-only). Eine zeitgesteuerte Selbst-
  Ausloesung waere eine neue proaktive Aktion -> PO-Entscheidung, bewusst
  nicht Teil dieser Scheibe.
- Sprechtauglich: kurze Saetze, Aufzaehlung als "1." (make_speakable der
  Sprachkanaele macht daraus Ordinale), kein Markdown.

configure() bekommt DIE Store-Instanzen der Runtime injiziert (nicht neue
- zwei EntryStore-Instanzen haetten getrennte Locks, siehe A2-Verdrahtung).
get_forecast/fetch_headlines werden auf Modulebene importiert, damit Tests
sie monkeypatchen koennen (Muster commands/weather.py).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from core.models import Plan, Result, Status
from core.news_reader import fetch_headlines
from core.phrases import pick
from core.weather import get_forecast
from memory.entries import format_when, is_past

logger = logging.getLogger("jarvis.commands.briefing")

_entry_store = None
_list_store = None
_weather_location: str = ""
_news_feeds: list = []
_timeout: float = 10.0

_MAX_ENTRIES = 4
_MAX_LISTS = 3
_MAX_HEADLINES = 3
_MAX_CALENDAR = 4

_OPENERS = (
    "Dein Briefing, Sir:",
    "Der Ueberblick, Sir:",
    "Die Lage des Tages, Sir:",
)
_REPEAT_LABELS = {"taeglich": "täglich", "woechentlich": "wöchentlich"}


def configure(entry_store, list_store, weather_location: str, news_feeds, timeout_seconds: float = 10.0) -> None:
    """Von main.py/jarvis_runtime.py beim Start mit den GETEILTEN Store-
    Instanzen aufgerufen; Tests injizieren Fakes."""
    global _entry_store, _list_store, _weather_location, _news_feeds, _timeout
    _entry_store = entry_store
    _list_store = list_store
    _weather_location = (weather_location or "").strip()
    _news_feeds = list(news_feeds or [])
    _timeout = timeout_seconds


def _entries_section() -> Optional[str]:
    if _entry_store is None:
        return None
    try:
        entries = _entry_store.list_open()
    except Exception:  # noqa: BLE001 - Briefing kommt auch ohne Eintraege
        logger.exception("Briefing: Eintraege nicht lesbar.")
        return None
    today = datetime.now().date().isoformat()
    # Nacht-Audit-Fix D: list_open() liefert auch VERGANGENE wichtige
    # Merkposten (bewusst, zum Nachschlagen) - fuers Briefing zaehlt aber
    # nur Offenes: sonst wird ein Jahre alter ⭐-Merkposten als
    # "Als Naechstes" praesentiert.
    dated = [e for e in entries if e.when and not is_past(e.when)]
    today_or_next = [e for e in dated if e.when[:10] == today] or dated[:1]
    undated = sum(1 for e in entries if not e.when)
    lines = []
    for e in today_or_next[:_MAX_ENTRIES]:
        rep = f" ({_REPEAT_LABELS[e.repeat]})" if e.repeat in _REPEAT_LABELS else ""
        star = "wichtig: " if e.important else ""
        lines.append(f"{star}{e.text} {format_when(e.when)}{rep}")
    parts = []
    if lines:
        label = "Heute" if today_or_next and today_or_next[0].when[:10] == today else "Als Naechstes"
        parts.append(f"{label}: " + "; ".join(lines) + ".")
    if undated:
        parts.append(f"Dazu {undated} Merkposten ohne Termin.")
    if not parts:
        parts.append("Keine Termine, nichts Dringendes - der Tag gehoert dir.")
    return " ".join(parts)


def _calendar_section() -> Optional[str]:
    """Heutige Termine aus dem ECHTEN (Outlook-)Kalender - bewusst getrennt von
    Jarvis' eigenen Erinnerungen (_entries_section). Fail-safe: kein Kalender
    konfiguriert oder Fehler -> Abschnitt entfaellt, das Briefing kommt trotzdem."""
    try:
        from commands.calendar import read_agenda
        events = read_agenda(datetime.now())
    except Exception:  # noqa: BLE001 - Briefing kommt auch ohne Kalender
        logger.info("Briefing: Kalender nicht lesbar - Abschnitt entfaellt.")
        return None
    if not events:
        return None
    parts = []
    for ev in events[:_MAX_CALENDAR]:
        if ev.get("all_day"):
            when = "ganztägig"
        else:
            try:
                when = datetime.fromisoformat(str(ev["start"])[:19]).strftime("%H:%M")
            except (ValueError, KeyError, TypeError):
                when = "?"
        loc = f" ({ev['location']})" if ev.get("location") else ""
        parts.append(f"{when} {ev.get('subject') or 'Termin'}{loc}")
    return "Im Kalender heute: " + "; ".join(parts) + "."


def _weather_section() -> Optional[str]:
    if not _weather_location:
        return None
    try:
        forecast = get_forecast(_weather_location, day_offset=0, timeout=_timeout)
    except Exception:  # noqa: BLE001 - kein Netz/Ort = kein Wetter-Absatz
        logger.info("Briefing: Wetter nicht abrufbar - Abschnitt entfaellt.")
        return None
    if forecast.current_temp is not None:
        text = f"Wetter: jetzt {forecast.current_temp:.0f} Grad, {forecast.condition}"
        afternoon = next((s for s in forecast.segments if s.label.lower().startswith("nachmittag")), None)
        if afternoon is not None:
            text += f", nachmittags bis {afternoon.temp:.0f}"
        rain = [s for s in forecast.segments if s.rain_probability is not None and s.rain_probability >= 20]
        if rain:
            text += f"; Regen moeglich am {rain[0].label}"
        return text + "."
    return (
        f"Wetter: {forecast.condition}, "
        f"{forecast.temp_min:.0f} bis {forecast.temp_max:.0f} Grad."
    )


def _lists_section() -> Optional[str]:
    if _list_store is None:
        return None
    try:
        overview = _list_store.overview()
    except Exception:  # noqa: BLE001
        logger.exception("Briefing: Listen nicht lesbar.")
        return None
    if not overview:
        return None
    from memory.lists import display_name

    shown = overview[:_MAX_LISTS]
    parts = [f"{display_name(name)} mit {count} Posten" for name, count in shown]
    return "Deine Listen: " + ", ".join(parts) + "."


def _news_section() -> Optional[str]:
    if not _news_feeds:
        return None
    try:
        headlines = fetch_headlines(_news_feeds, limit=_MAX_HEADLINES)
    except Exception:  # noqa: BLE001 - offline = keine Lage, kein Drama
        logger.info("Briefing: Schlagzeilen nicht abrufbar - Abschnitt entfaellt.")
        return None
    if not headlines:
        return None
    lines = [f"{i}. {h.title}" for i, h in enumerate(headlines, start=1)]
    return "Die Lage: " + " ".join(lines)


class GetBriefingCommand:
    name = "get_briefing"
    description = (
        "Traegt das Tages-Briefing vor - EIN Ueberblick aus Erinnerungen/"
        "Terminen, Wetter, Listen und Top-Schlagzeilen (z. B. 'Briefing', "
        "'wie sieht mein Tag aus?', 'starte den Tag'). Read-only, Stufe 0. "
        "Abgrenzung: 'was steht an?' (nur Eintraege) bleibt list_entries, "
        "reine Nachrichten bleiben get_news, reines Wetter get_weather."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        sections = [
            _entries_section(),
            _calendar_section(),
            _weather_section(),
            _lists_section(),
            _news_section(),
        ]
        body = "\n".join(s for s in sections if s)
        if not body:
            return Result(
                status=Status.SUCCESS,
                message="Es gibt schlicht nichts zu berichten, Sir - ein seltener Luxus.",
            )
        # A3 (ADR-065): die gesammelten Abschnitte als DATEN mitgeben - ist der
        # Composer im Kern aktiv, webt er daraus EIN fluessiges, gesprochenes
        # Morgen-Briefing (statt der Abschnitts-Aneinanderreihung). Die `message`
        # bleibt das bewaehrte Template als Fallback (Composer aus/fehlgeschlagen).
        compose_context = (
            "Baue aus diesen Tages-Bausteinen EIN fluessiges, gesprochenes "
            "Morgen-Briefing (kurz, warm, nicht die Abschnitts-Namen aufzaehlen). "
            "Erwaehne dabei ALLE Termine und Aufgaben - lass keinen weg:\n"
            + body
        )
        return Result(
            status=Status.SUCCESS,
            message=f"{pick(*_OPENERS)}\n{body}",
            data={"sections": sum(1 for s in sections if s), "compose_context": compose_context},
        )


# Registrierungspunkt - commands/__init__.py liest diese Liste beim Start ein.
COMMANDS = [GetBriefingCommand()]
