"""
Commands fuer Eintraege (A1, Welle 1) - Erinnerungen/Aufgaben/wichtige
Merkposten anlegen, auflisten, loeschen. Datenlayer: memory/entries.py.

Der Planner liefert die Zeit bereits als ISO 8601 in parameters.when (er
kennt seit A1 das aktuelle Datum und rechnet "morgen um 9" selbst um);
dieser Command parst KEINE natuerliche Sprache. Das Echo nennt die
verstandene Zeit lesbar zurueck - der Nutzer sieht sofort, ob Verhoerer
oder Datumsfehler passiert sind (Vertrauens-/Korrektur-UX, PIS-Prinzip).

Sicherheitsstufe 0/1: reiner eigener Datenlayer, keine Systemaktion -
keine Bestaetigung noetig (Muster wie remember_fact). configure() wie
commands/memory.py (Registry instanziiert vor Config.load()).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.models import Plan, Result, Status
from memory.entries import EntryStore, format_when

_store: Optional[EntryStore] = None

_MAX_LIST_ENTRIES = 30


def configure(memory_dir: Path) -> EntryStore:
    """Von main.py/jarvis_runtime.py einmal beim Start aufgerufen. Tests
    rufen dies mit tmp_path auf. Gibt die Store-Instanz zurueck, damit die
    Runtime DENSELBEN Store fuer den Scheduler nutzt (A2) - zwei Instanzen
    haetten getrennte Locks."""
    global _store
    _store = EntryStore(memory_dir)
    return _store


def _require_store() -> EntryStore:
    if _store is None:
        raise RuntimeError(
            "Eintraege nicht konfiguriert - commands.entries.configure() "
            "muss beim Start aufgerufen werden (siehe main.py)."
        )
    return _store


# Antwort-Varianten (Persona-Lebendigkeit, PO-Befund 2026-07-10) - Tests
# pruefen gegen die Pools, nicht gegen einen festen Satz.
_ADD_PREFIXES = ("Notiert, Sir", "Vermerkt, Sir", "Steht auf der Liste, Sir")
_IMPORTANT_PREFIXES = ("⭐ Als wichtig vermerkt, Sir", "⭐ Mit Stern notiert, Sir")
_DELETE_PREFIXES = ("🗑 Erledigt, Sir", "🗑 Gestrichen, Sir", "🗑 Ist vom Tisch, Sir")


# Anzeige-Namen der Wiederholung (ADR-052).
_REPEAT_LABELS = {"taeglich": "täglich", "woechentlich": "wöchentlich"}


def _repeat_hint(entry) -> str:
    label = _REPEAT_LABELS.get(getattr(entry, "repeat", ""), "")
    return f" ↻ {label}" if label else ""


def _todays_calendar_block() -> str:
    """Heute noch KOMMENDE Kalender-Termine als Anhang fuer den Tages-Blick
    ('Was steht an?'). Vergangene Termine bewusst draussen (eine Wahrheit:
    was vorbei ist, 'steht' nicht mehr an). Fail-open: kein Kalender/Fehler
    -> leerer String, die Eintragsliste bleibt unangetastet."""
    try:
        from datetime import datetime

        from commands.calendar import _event_time, read_agenda

        now = datetime.now()
        upcoming = []
        for ev in read_agenda(now.replace(hour=0, minute=0, second=0, microsecond=0)):
            if ev.get("all_day"):
                upcoming.append(ev)
                continue
            try:
                if datetime.fromisoformat(str(ev.get("start", ""))[:19]) >= now:
                    upcoming.append(ev)
            except ValueError:
                continue
        if not upcoming:
            return ""
        lines = "\n".join(
            f"• {_event_time(ev)} {ev.get('subject', '')}"
            + (f" ({ev['location']})" if ev.get("location") else "")
            for ev in upcoming[:6]
        )
        return f"\n\n🗓 Heute noch im Kalender:\n{lines}"
    except Exception:  # noqa: BLE001 - Kalender ist Beiwerk dieses Befehls
        return ""


def _entry_line(number: int, entry) -> str:
    # Nummeriert statt Spiegelstrich (PO-Reibung 2026-07-10 "Loeschen ist
    # umstaendlich"): "loesch Nummer 2" greift auf diese Anzeige zurueck.
    # mark_past (Kundenreview 13.07., 'Eine gemeinsame Wahrheit'): ein
    # wichtiger 09:00-Termin bleibt zwar in der Liste (PO-Default), heisst
    # abends aber 'war fällig heute um 09:00' - nie mehr wie anstehend.
    star = "⭐ " if entry.important else ""
    when = f" — {format_when(entry.when, mark_past=True)}" if entry.when else ""
    return f"{number}. {star}«{entry.text}»{when}{_repeat_hint(entry)}"


class AddEntryCommand:
    name = "add_entry"
    description = (
        "Legt einen Eintrag an: Erinnerung, Aufgabe oder wichtigen Merkposten "
        "(z. B. 'erinnere mich morgen um 9 an den Zahnarzt', 'notiere: Milch "
        "kaufen', 'wichtiger Termin: am 12.07. Audit'). Einmalige, oft "
        "terminierte Dinge - KEINE dauerhaften Fakten (das ist remember_fact). "
        "parameters.text = der Wortlaut der Aufgabe OHNE Trigger-Worte (nicht in "
        "target); parameters.when = der Zeitpunkt als EIN ISO-8601-String (z. B. "
        "'2026-07-12T15:00'), weglassen wenn keine Zeit genannt ist (NICHT nach "
        "day/time trennen); parameters.important = true bei 'wichtig'/'wichtiger "
        "Termin'; parameters.repeat = 'taeglich' oder 'woechentlich' bei "
        "Wiederholung (when ist dann der naechste Termin)."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        text = (plan.parameters.get("text") or plan.target or "").strip()
        if not text:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Was genau darf ich notieren, Sir?",
            )

        when = str(plan.parameters.get("when") or "").strip()
        important = bool(plan.parameters.get("important", False))
        repeat = str(plan.parameters.get("repeat") or "").strip()
        entry = _require_store().add(text, when=when, important=important, repeat=repeat)

        # Persona-Pass (PO-Freigabe 2026-07-09) + Varianten (Lebendigkeit,
        # PO-Befund 2026-07-10): Fakten bleiben exakt, nur der Rahmen atmet.
        from core.phrases import pick

        prefix = pick(*_IMPORTANT_PREFIXES) if important else pick(*_ADD_PREFIXES)
        when_part = f" — {format_when(entry.when)}" if entry.when else ""
        # Wiederholung (ADR-052): das Echo nennt Rhythmus + naechsten Termin,
        # damit ein Planner-Fehlgriff ("taeglich" nicht erkannt) sofort auffaellt.
        if entry.repeat:
            when_part = f" — ↻ {_REPEAT_LABELS[entry.repeat]}, nächste: {format_when(entry.when)}"
        return Result(
            status=Status.SUCCESS,
            message=f"{prefix}: «{entry.text}»{when_part}",
            data={"id": entry.id},
        )


class ListEntriesCommand:
    name = "list_entries"
    description = (
        "Listet offene Eintraege (Erinnerungen/Aufgaben/wichtige Merkposten) - "
        "z. B. 'was steht an?', 'zeig meine Erinnerungen', 'zeig wichtige "
        "Termine'. Optional Stichwort- und Wichtig-Filter."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        keyword = str(plan.parameters.get("keyword") or plan.target or "").strip() or None
        important_only = bool(plan.parameters.get("important_only", False))
        include_past = bool(plan.parameters.get("include_past", False))

        entries = _require_store().list_open(
            keyword=keyword, important_only=important_only, include_past=include_past
        )
        # Tages-Blick (2. Kundenreview Rang 6, PO-Go 13.07. nachts): 'Was
        # steht an?' zeigt auch die HEUTE noch kommenden Kalender-Termine -
        # vorher fehlten sie hier komplett (die tiefere Wurzel hinter 'zwei
        # Wahrheiten'). Nur im ungefilterten Ruf; fail-open ohne Kalender.
        calendar_block = "" if (keyword or important_only) else _todays_calendar_block()

        if not entries:
            base = "Keine anstehenden Einträge, Sir — die Liste ist erfreulich leer."
            if calendar_block:
                base = "Keine offenen Einträge, Sir." + calendar_block
            return Result(status=Status.SUCCESS, message=base)

        shown = entries[:_MAX_LIST_ENTRIES]
        lines = "\n".join(_entry_line(i, e) for i, e in enumerate(shown, start=1))
        more = (
            f"\n… und {len(entries) - len(shown)} weitere."
            if len(entries) > len(shown)
            else ""
        )
        return Result(
            status=Status.SUCCESS,
            message=f"Deine Einträge, Sir:\n{lines}{more}{calendar_block}",
            data={"count": len(entries)},
        )


class DeleteEntryCommand:
    name = "delete_entry"
    description = (
        "Loescht einen Eintrag wieder (z. B. 'loesch die Zahnarzt-Erinnerung', "
        "'streich Milch kaufen von der Liste')."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        needle = (plan.parameters.get("text") or plan.target or "").strip()
        if not needle:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Welchen Eintrag darf ich streichen, Sir?",
            )

        # exact (Nacht-Audit-Fix B): die stillen UI-Endpunkte kennen den
        # vollstaendigen Text und verlangen den exakten Treffer - der
        # Sprach-/Chat-Weg bleibt beim toleranten Teilstring.
        removed = _require_store().delete(needle, exact=bool(plan.parameters.get("exact")))
        if removed is None:
            return Result(
                status=Status.FAILED,
                message=f"Dazu habe ich keinen Eintrag gefunden: {needle}",
            )
        from core.phrases import pick

        # Undo-Hinweis (Bestaetigungs-Diaet 14.07.): nichts verschwindet mehr
        # hart, der Papierkorb faengt es - wie beim Fakten-Loeschen.
        return Result(
            status=Status.SUCCESS,
            message=(
                f"{pick(*_DELETE_PREFIXES)} — «{removed.text}» ist gestrichen. "
                f"(Falls das ein Versehen war: «stell den Eintrag wieder her».)"
            ),
        )


class RestoreEntryCommand:
    name = "restore_entry"
    description = (
        "Holt einen geloeschten Eintrag aus dem Papierkorb zurueck (z. B. "
        "'stell den Eintrag wieder her', 'die Erinnerung war ein Versehen'). "
        "target = Suchtext; ohne target kommt der ZULETZT geloeschte Eintrag "
        "zurueck."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        text = (plan.target or plan.parameters.get("text") or "").strip()
        entry = _require_store().restore(text)
        if entry is None:
            return Result(
                status=Status.FAILED,
                message=(
                    "Im Papierkorb liegt dazu nichts, Sir"
                    + (f" (gesucht: {text})" if text else "")
                    + " — dann gibt es auch nichts wiederherzustellen."
                ),
            )
        when_part = f" — {format_when(entry.when, mark_past=True)}" if entry.when else ""
        return Result(
            status=Status.SUCCESS,
            message=f"Wiederhergestellt, Sir — steht wieder drin: «{entry.text}»{when_part}",
            data={"id": entry.id},
        )


class UpdateEntryCommand:
    name = "update_entry"
    description = (
        "Aendert einen BESTEHENDEN Eintrag/Termin - verschiebt die Zeit und/oder "
        "das Wichtig-Flag (z. B. 'aktualisiere den Termin bei der Mutter auf "
        "14:45', 'verschieb den Zahnarzt auf morgen 11 Uhr', 'der Anruf ist doch "
        "erst um 15 Uhr'). target = der Text des BESTEHENDEN Eintrags (Teilstring "
        "genuegt, ohne Trigger-Worte); parameters.when = der NEUE Zeitpunkt als "
        "EIN ISO-8601-String (z. B. '2026-07-12T14:45'); parameters.important = "
        "true/false optional. NICHT fuer NEUE Eintraege (das ist add_entry), "
        "nicht fuers Loeschen (delete_entry)."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        target = (plan.parameters.get("text") or plan.target or "").strip()
        when = str(plan.parameters.get("when") or "").strip()
        important = plan.parameters.get("important")
        if not target:
            return Result(status=Status.NEEDS_CLARIFICATION,
                          message="Welchen Termin darf ich ändern, Sir?")
        if not when and important is None:
            return Result(status=Status.NEEDS_CLARIFICATION,
                          message="Worauf soll ich den Termin ändern, Sir? (die neue Zeit)")
        updated = _require_store().update(
            target,
            when=when or None,
            important=bool(important) if important is not None else None,
        )
        if updated is None:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=f"Ich finde keinen Eintrag «{target}», Sir. Soll ich ihn neu anlegen?",
            )
        when_part = f" — {format_when(updated.when)}" if updated.when else ""
        star = "⭐ " if updated.important else ""
        return Result(
            status=Status.SUCCESS,
            message=f"Geändert, Sir: {star}«{updated.text}»{when_part}",
            data={"id": updated.id},
        )


# Registrierungspunkt - commands/__init__.py liest diese Liste beim Start ein.
COMMANDS = [AddEntryCommand(), ListEntriesCommand(), DeleteEntryCommand(),
            RestoreEntryCommand(), UpdateEntryCommand()]
