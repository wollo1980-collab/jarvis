"""
Proaktive Vorbereitung (ADR-063) - "der COO denkt voraus".

Jarvis schaut selbst im Kalender voraus und BIETET EINMAL an, rechtzeitig an
einen anstehenden Termin zu erinnern - z. B. abends fuer den naechsten Tag:
"Morgen 9:00 «Steuerberater». Soll ich dich um 8:00 daran erinnern? (ja/nein)".

DNA: Vorschlag statt Aktion. Dieses Modul ENTSCHEIDET nur, WAS angeboten wird -
es handelt NIE. Das Anlegen der Erinnerung passiert erst nach einem "ja" des
Nutzers, ueber die bestehende, kanalgebundene Angebots-Schiene (ADR-051), und
auch dann nur als schlichter Erinnerungs-Eintrag.

Bewusst deterministisch (kein LLM): die Vorausschau soll zuverlaessig und
testbar sein; der Mehrwert liegt in der Proaktivitaet, nicht in bluemiger
Sprache. Eine LLM-Formulierung kann spaeter als Verfeinerung dazukommen.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Optional

_DEFAULT_LEAD_MINUTES = 60


@dataclass
class PrepSuggestion:
    """Ein fertiger Vorbereitungs-Vorschlag: der Anstoss-Text (ja/nein-Frage)
    plus die konkrete Erinnerung, die ein 'ja' anlegt."""

    subject: str
    event_time: str          # "09:00" - Startzeit des Termins
    reminder_text: str       # Text der Erinnerung, z. B. "Steuerberater um 09:00"
    reminder_when_iso: str   # ISO-Zeit der Erinnerung, z. B. "2026-07-13T08:00:00"
    reminder_time: str       # "08:00"
    nudge: str               # vollstaendige ja/nein-Frage an den Nutzer

    def to_dict(self) -> dict:
        return asdict(self)


def notable_event(events: list[dict]) -> Optional[dict]:
    """Der erste getaktete Termin (Ganztags-/Routine-Eintraege ueberspringen).
    events kommen bereits nach Startzeit sortiert vom Kalender-Client."""
    for ev in events:
        if ev.get("all_day"):
            continue
        try:
            datetime.fromisoformat(str(ev.get("start", ""))[:19])
        except (ValueError, TypeError):
            continue
        return ev
    return None


def plan_preparation(
    events: list[dict],
    now: datetime,
    lead_minutes: int = _DEFAULT_LEAD_MINUTES,
    day_label: str = "Morgen",
    people: Optional[list[dict]] = None,
    related_tasks: Optional[list[str]] = None,
) -> Optional[PrepSuggestion]:
    """Baut aus den Terminen EINES Tages hoechstens EINEN Vorschlag: den ersten
    getakteten Termin, dazu eine Erinnerung `lead_minutes` davor. None, wenn es
    keinen getakteten Termin gibt oder die Vorwarnzeit schon vorbei waere.

    ADR-066 Stein 2 (Punkte verbinden): `people` (im Titel erkannte bekannte
    Personen) und `related_tasks` (dazu passende offene Aufgaben) reichern den
    Anstoss an - der COO denkt ueber den einzelnen Termin hinaus."""
    ev = notable_event(events)
    if ev is None:
        return None
    start = datetime.fromisoformat(str(ev["start"])[:19])
    reminder = start - timedelta(minutes=lead_minutes)
    if reminder <= now:
        return None
    subject = (str(ev.get("subject") or "").strip() or "ein Termin")
    event_time = start.strftime("%H:%M")
    reminder_time = reminder.strftime("%H:%M")
    who = ""
    if people:
        named = [f"{p.get('name', '?')} ({'; '.join(p.get('notes', []))})"
                 for p in people if p.get("notes")]
        if named:
            who = " – mit " + ", ".join(named)
    tasks = ""
    if related_tasks:
        tasks = " Dazu ist bei dir noch offen: " + "; ".join(related_tasks) + "."
    nudge = (
        f"Kleiner Blick voraus, Sir: {day_label} um {event_time} steht «{subject}» an{who}.{tasks} "
        f"Soll ich dich um {reminder_time} rechtzeitig daran erinnern? (ja/nein)"
    )
    return PrepSuggestion(
        subject=subject,
        event_time=event_time,
        reminder_text=f"{subject} um {event_time}",
        reminder_when_iso=reminder.strftime("%Y-%m-%dT%H:%M:%S"),
        reminder_time=reminder_time,
        nudge=nudge,
    )
