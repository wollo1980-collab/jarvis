"""
Personen-Befehl (ADR-066 Stein 1): „merk dir, wer jemand ist".

configure() bekommt die GETEILTE PeopleStore-Instanz der Runtime injiziert
(gleiches Muster wie entries/lists). Nur Speichern - das Hervorholen des
Personen-Kontexts macht die Runtime pro Anfrage.
"""
from __future__ import annotations

import logging
from typing import Optional

from core.models import Plan, Result, Status
from memory.people import PeopleStore

logger = logging.getLogger("jarvis.commands.people")

_store: Optional[PeopleStore] = None


def configure(store: PeopleStore) -> None:
    global _store
    _store = store


class RememberPersonCommand:
    name = "remember_person"
    description = (
        "Merkt sich eine PERSON und ihre Rolle/Beziehung dauerhaft (z. B. 'merk "
        "dir, dass Anna meine Steuerberaterin ist', 'Tom leitet Projekt X', 'meine "
        "Frau heisst Lisa'). parameters.name = Name der Person, parameters.note = "
        "wer sie ist / Rolle / Beziehung (ohne Trigger-Worte). Abgrenzung: "
        "remember_fact sind Fakten ueber DICH, remember_person sind Menschen in "
        "deinem Umfeld. Read/write eigenes Gedaechtnis, Stufe 0."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if _store is None:
            return Result(status=Status.FAILED,
                          message="Das Personen-Gedaechtnis ist nicht verdrahtet, Sir.")
        p = plan.parameters or {}
        name = str(p.get("name") or "").strip()
        note = str(p.get("note") or p.get("role") or "").strip()
        if not name or not note:
            return Result(status=Status.NEEDS_CLARIFICATION,
                          message="Wen soll ich mir merken, Sir - und wer ist die Person?")
        _store.remember(name, note)
        return Result(status=Status.SUCCESS,
                      message=f"Gemerkt, Sir: {name} — {note}.",
                      data={"name": name})


class WhoIsCommand:
    name = "who_is"
    description = (
        "Beantwortet 'wer ist X?', 'was weisst du ueber X?', 'kennst du X?' aus "
        "dem Personen-Gedaechtnis. parameters.name = Name der Person. Read-only, "
        "Stufe 0. Abgrenzung: fuer Fakten ueber DICH ist es list_facts, fuer "
        "Personen deines Umfelds who_is."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if _store is None:
            return Result(status=Status.FAILED,
                          message="Das Personen-Gedaechtnis ist nicht verdrahtet, Sir.")
        name = str((plan.parameters or {}).get("name") or plan.target or "").strip()
        if not name:
            return Result(status=Status.NEEDS_CLARIFICATION, message="Über wen, Sir?")
        person = _store.get(name)
        if not person or not person.get("notes"):
            return Result(status=Status.SUCCESS,
                          message=f"Zu {name} habe ich noch nichts gemerkt, Sir.")
        return Result(status=Status.SUCCESS,
                      message=f"{person['name']}: {'; '.join(person['notes'])}.",
                      data={"name": person["name"]})


COMMANDS = [RememberPersonCommand(), WhoIsCommand()]
