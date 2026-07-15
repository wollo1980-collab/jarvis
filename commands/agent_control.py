"""
Agenten-Stopp auf Zuruf (Telegram-Ausbau c1, 13.07.2026).

Der Stopp-Knopf des Bau-/Analyse-Agenten (ADR-056 Scheibe 2, runtime.
cancel_delegation) war bisher NUR im Dashboard erreichbar - unterwegs war ein
laufender Agent nicht zu stoppen. Dieser Befehl macht den bestehenden
Kill-Switch als Kommando verfuegbar ('stopp den Agenten', 'brich den Bau ab')
- damit hat auch das Handy die harte Kontrolle, Voraussetzung dafuer, den
Bau-Arm spaeter mobil zu oeffnen (Scheibe c2, PO-Entscheidung).

Entkoppelt wie shutdown.py: die Fachlogik kennt die Runtime nicht, nur einen
injizierten Hook. Sicherheitsstufe 0 (reine Kontrollaktion - sie STOPPT etwas,
startet nie etwas); requires_confirmation=False ist zwingend, damit der Befehl
auch ueber fail-closed Kanaele wirkt.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.agent_control")

# cancel_hook() -> bool: True, wenn es etwas zu stoppen gab (runtime.cancel_delegation).
_cancel_hook: Optional[Callable[[], bool]] = None


def configure(cancel_hook: Optional[Callable[[], bool]]) -> None:
    """Von jarvis_runtime.py beim Start aufgerufen: injiziert den Kill-Switch-
    Hook. main.py (Konsole ohne Delegations-Slot-Zugriff) laesst ihn weg ->
    der Befehl meldet dann ehrlich, dass hier nichts verdrahtet ist."""
    global _cancel_hook
    _cancel_hook = cancel_hook


class StopAgentCommand:
    name = "stop_agent"
    description = (
        "Bricht den gerade LAUFENDEN Bau-/Analyse-Agenten ab (z. B. 'stopp den "
        "Agenten', 'brich den Bau ab', 'halt den Lauf an') - der Kill-Switch "
        "beendet den Agenten-Subprozess. Klar abzugrenzen von stop_runtime "
        "(Jarvis selbst beenden) und shutdown_pc (Rechner aus). Wirkt nur, wenn "
        "gerade eine Delegation laeuft; startet nie etwas. Sicherheitsstufe 0."
    )
    # Zwingend False: eine Stopp-Aktion muss auch ueber fail-closed Kanaele
    # (ohne Bestaetigungsdialog) sofort greifen.
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if _cancel_hook is None:
            return Result(
                status=Status.SUCCESS,
                message=(
                    "Von hier komme ich nicht an den Agenten-Stopp - dieser Kanal "
                    "hat keinen Kill-Switch-Hook."
                ),
            )
        if _cancel_hook():
            logger.info("stop_agent: laufende Delegation abgebrochen.")
            return Result(
                status=Status.SUCCESS,
                message="Abgebrochen, Sir — der Agent wird gestoppt.",
            )
        return Result(
            status=Status.SUCCESS,
            message="Es läuft gerade kein Agent, Sir — nichts zu stoppen.",
        )


COMMANDS = [StopAgentCommand()]
