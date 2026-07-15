"""
Meeting-Prep-Befehl (Plan C4): „bereite mein Meeting vor".

Die eigentliche Zusammenstellung (Kalender + Personen + verwandte Aufgaben) macht
die Runtime (sie hat alle Speicher); der Befehl ruft die injizierte Funktion.
Read-only, Stufe 0.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.meeting")

_prep_fn: Optional[Callable[[str], str]] = None


def configure(prep_fn: Callable[[str], str]) -> None:
    global _prep_fn
    _prep_fn = prep_fn


class PrepareMeetingCommand:
    name = "prepare_meeting"
    description = (
        "Bereitet einen anstehenden Termin/ein Meeting vor (z. B. 'bereite mein "
        "naechstes Meeting vor', 'was muss ich zum Termin mit Anna wissen', "
        "'meeting-prep') - buendelt Termin + bekannte Person + verwandte offene "
        "Aufgaben. parameters.query = optional, worum/mit wem es geht. Nur lesend."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if _prep_fn is None:
            return Result(status=Status.FAILED,
                          message="Die Meeting-Vorbereitung ist nicht verdrahtet, Sir.")
        query = str((plan.parameters or {}).get("query") or plan.target or "").strip()
        try:
            text = _prep_fn(query)
        except Exception:  # noqa: BLE001 - fail-safe
            logger.exception("Meeting-Prep fehlgeschlagen.")
            return Result(status=Status.FAILED,
                          message="Ich konnte den Termin nicht vorbereiten, Sir (Details im Log).")
        return Result(status=Status.SUCCESS, message=text or "Ich sehe keinen Termin, Sir.")


COMMANDS = [PrepareMeetingCommand()]
