"""
Selbstbewertungs-Befehl (ADR-066 Stein 3): „wie schlaegst du dich?".

Gibt die juengste Selbstbewertung aus dem Journal wieder (read-only). configure()
bekommt die GETEILTE SelfReviewJournal-Instanz der Runtime injiziert.
"""
from __future__ import annotations

import logging
from typing import Optional

from core.models import Plan, Result, Status
from memory.self_review import SelfReviewJournal

logger = logging.getLogger("jarvis.commands.selfreview")

_journal: Optional[SelfReviewJournal] = None
# Optionaler Rueckruf: erzeugt bei Bedarf SOFORT eine Selbstbewertung (statt auf
# den naechtlichen/Scheduler-Lauf zu warten) - so antwortet 'wie schlaegst du
# dich?' auch direkt nach einem Neustart. Von der Runtime injiziert.
_on_demand = None


def configure(journal: SelfReviewJournal, on_demand=None) -> None:
    global _journal, _on_demand
    _journal = journal
    _on_demand = on_demand


class SelfReviewCommand:
    name = "self_review"
    description = (
        "Sagt, wie gut Jarvis sich zuletzt geschlagen hat und wo er sich "
        "verbessern koennte ('wie schlaegst du dich?', 'wo hakt es bei dir?', "
        "'wie war deine Woche?', 'was koenntest du besser machen?'). Read-only, "
        "Stufe 0 - Jarvis' ehrliche Selbstbewertung, keine Aktion."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if _journal is None:
            return Result(status=Status.FAILED,
                          message="Die Selbstbewertung ist nicht verdrahtet, Sir.")
        text = _journal.latest().strip()
        if not text and _on_demand is not None:
            # Noch kein Journal (z. B. frisch nach Neustart) -> jetzt sofort eine
            # Bewertung erzeugen. Fail-safe.
            try:
                text = (_on_demand() or "").strip()
            except Exception:  # noqa: BLE001
                text = ""
        if not text:
            return Result(status=Status.SUCCESS, message=(
                "Ich habe mich noch nicht selbst bewertet, Sir — sobald ich ein paar "
                "Interaktionen gesehen habe, kann ich das."))
        # Markdown-Kopf ('# Selbstbewertung …') fuer die (Sprach-)Ausgabe abtrennen.
        body = "\n".join(line for line in text.splitlines() if not line.startswith("#")).strip()
        return Result(status=Status.SUCCESS,
                      message=body or text,
                      data={"chars": len(body)})


COMMANDS = [SelfReviewCommand()]
