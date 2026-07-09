"""
Runtime-Neustart (restart_runtime, Welle 3.4) - Nutzungslauf-Befund
2026-07-09: Beenden per Zuruf war komfortabel, das Neustarten (Doppelklick
auf die Verknuepfung) umstaendlich. "Starte dich neu" schliesst die Luecke.

Gleiches Entkopplungs-Muster wie shutdown.py: der Befehl kennt die Runtime
nicht, er ruft nur einen aus der Verdrahtungsschicht injizierten Hook. Der
Hook (jarvis_runtime._request_restart) startet den abgekoppelten
Nachfolger-Prozess und legt DANACH das Stop-Sentinel in die Queue - schlaegt
schon der Prozess-Start fehl, faehrt nichts herunter (lieber im Dienst
bleiben als tot). Der Hook meldet per Rueckgabewert, ob der Neustart
eingeleitet wurde - die Antwort an den Nutzer bleibt ehrlich.

Sicherheitsstufe 0 (Kontrollaktion wie stop_runtime, kein Datenverlust).
requires_confirmation=False ist zwingend: die Runtime-Speech ist fail-closed
(_RuntimeSpeech, ADR-018) - ein bestaetigungspflichtiger Befehl waere ueber
Telegram gesperrt.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.restart")

_restart_hook: Optional[Callable[[], bool]] = None


def configure(restart_hook: Optional[Callable[[], bool]]) -> None:
    """Von jarvis_runtime.py beim Start aufgerufen: injiziert den Hook, der
    den Neustart einleitet (Nachfolger starten + Stop-Sentinel). main.py
    (Konsole) ruft dies NICHT auf -> dort meldet der Befehl freundlich, dass
    ein Neustart hier nicht verdrahtet ist."""
    global _restart_hook
    _restart_hook = restart_hook


class RestartRuntimeCommand:
    name = "restart_runtime"
    description = (
        "Startet Jarvis selbst (die laufende Runtime) neu: sauber herunterfahren "
        "und frisch wieder starten - NICHT den Computer. Trigger z. B. 'starte "
        "dich neu', 'Neustart', 'restarte dich', 'starte Jarvis neu'. Klar "
        "abzugrenzen von stop_runtime (nur beenden) und restart_pc/shutdown_pc "
        "(den Rechner). Sicherheitsstufe 0. Setzt sonst nichts um."
    )
    # Zwingend: die Runtime-Speech ist fail-closed - ein bestaetigungspflichtiger
    # Befehl waere ueber Telegram gesperrt und nie ausfuehrbar.
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if _restart_hook is None:
            return Result(
                status=Status.SUCCESS,
                message=(
                    "Von hier kann ich mich nicht selbst neu starten - dieser "
                    "Kanal hat keinen Neustart-Hook. (In der Konsole beenden "
                    "und neu starten.)"
                ),
            )
        logger.info("restart_runtime: Neustart angefordert.")
        if not _restart_hook():
            return Result(
                status=Status.FAILED,
                message=(
                    "Der Neustart ließ sich nicht einleiten, Sir — ich bleibe "
                    "im Dienst. Details stehen im Log."
                ),
            )
        return Result(
            status=Status.SUCCESS,
            message="Wie du wünschst, Sir — ich starte mich neu. Gleich wieder da.",
        )


COMMANDS = [RestartRuntimeCommand()]
