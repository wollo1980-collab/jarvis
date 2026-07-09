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


def _entry_line(entry) -> str:
    star = "⭐ " if entry.important else ""
    when = f" — {format_when(entry.when)}" if entry.when else ""
    return f"- {star}«{entry.text}»{when}"


class AddEntryCommand:
    name = "add_entry"
    description = (
        "Legt einen Eintrag an: Erinnerung, Aufgabe oder wichtigen Merkposten "
        "(z. B. 'erinnere mich morgen um 9 an den Zahnarzt', 'notiere: Milch "
        "kaufen', 'wichtiger Termin: am 12.07. Audit'). Einmalige, oft "
        "terminierte Dinge - KEINE dauerhaften Fakten (das ist remember_fact)."
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
        entry = _require_store().add(text, when=when, important=important)

        # Persona-Pass (PO-Freigabe 2026-07-09): Formulierungen im Film-Jarvis-
        # Ton - Fakten (Zeiten/Texte) bleiben exakt, nur der Rahmen spricht.
        prefix = "⭐ Als wichtig vermerkt, Sir" if important else "Notiert, Sir"
        when_part = f" — {format_when(entry.when)}" if entry.when else ""
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
        if not entries:
            return Result(
                status=Status.SUCCESS,
                message="Keine anstehenden Einträge, Sir — die Liste ist erfreulich leer.",
            )

        shown = entries[:_MAX_LIST_ENTRIES]
        lines = "\n".join(_entry_line(e) for e in shown)
        more = (
            f"\n… und {len(entries) - len(shown)} weitere."
            if len(entries) > len(shown)
            else ""
        )
        return Result(
            status=Status.SUCCESS,
            message=f"Deine Einträge, Sir:\n{lines}{more}",
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

        removed = _require_store().delete(needle)
        if removed is None:
            return Result(
                status=Status.FAILED,
                message=f"Dazu habe ich keinen Eintrag gefunden: {needle}",
            )
        return Result(
            status=Status.SUCCESS,
            message=f"🗑 Erledigt, Sir — «{removed.text}» ist gestrichen.",
        )


# Registrierungspunkt - commands/__init__.py liest diese Liste beim Start ein.
COMMANDS = [AddEntryCommand(), ListEntriesCommand(), DeleteEntryCommand()]
