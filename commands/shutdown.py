"""
Runtime-Beenden (stop_runtime) - Reibungsfix: Jarvis ueber Telegram sauber
herunterfahren, statt PIDs zu jagen.

Der Befehl faehrt NICHT selbst herunter - das wuerde den eigenen Worker-Thread
per join() blockieren (Selbst-Deadlock). Er ruft nur einen aus der
Verdrahtungsschicht injizierten Hook, der das Stop-Sentinel in die
Runtime-Queue legt; der Worker bricht in der naechsten Runde ab, main() faehrt
im finally sauber herunter (Telegram-Stop + runtime.stop()). Entkoppelt wie
plan.py/delegate.py: die Fachlogik kennt die Runtime nicht, nur den Hook.

Sicherheitsstufe 0 (Kontrollaktion, kein Datenverlust, reversibel per Neustart).
requires_confirmation=False ist zwingend: die Runtime-Speech ist fail-closed
(_RuntimeSpeech, ADR-018) - ein bestaetigungspflichtiger Befehl waere ueber
Telegram gesperrt.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.shutdown")

_shutdown_hook: Optional[Callable[[], None]] = None


def configure(shutdown_hook: Optional[Callable[[], None]]) -> None:
    """Von jarvis_runtime.py beim Start aufgerufen: injiziert den Hook, der das
    Herunterfahren der Runtime anstoesst (Stop-Sentinel in die Queue). main.py
    (Konsole) ruft dies NICHT auf -> dort meldet der Befehl freundlich, dass
    Beenden hier nicht verdrahtet ist (die Konsole hat ihr eigenes Exit-Wort)."""
    global _shutdown_hook
    _shutdown_hook = shutdown_hook


class StopRuntimeCommand:
    name = "stop_runtime"
    description = (
        "Faehrt Jarvis selbst (die laufende Runtime) sauber herunter - NICHT den "
        "Computer. Trigger z. B. 'beende dich', 'fahr dich runter', 'stell dich ab', "
        "'beende Jarvis', 'Jarvis herunterfahren'. Klar abzugrenzen von shutdown_pc "
        "(Rechner ausschalten) und von Abschiedsworten wie 'Tschuess'/'Ende' (= chat). "
        "Sicherheitsstufe 0, reversibel per Neustart. Setzt sonst nichts um."
    )
    # Zwingend: die Runtime-Speech ist fail-closed - ein bestaetigungspflichtiger
    # Befehl waere ueber Telegram gesperrt und nie ausfuehrbar.
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if _shutdown_hook is None:
            return Result(
                status=Status.SUCCESS,
                message=(
                    "Von hier kann ich mich nicht selbst beenden - dieser Kanal hat "
                    "keinen Herunterfahr-Hook. (In der Konsole das Exit-Wort nutzen.)"
                ),
            )
        logger.info("stop_runtime: Herunterfahren angefordert.")
        _shutdown_hook()
        return Result(
            status=Status.SUCCESS,
            message="Verstanden - ich fahre herunter. Bis bald!",
        )


COMMANDS = [StopRuntimeCommand()]
