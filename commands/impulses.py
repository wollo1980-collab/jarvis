"""
Impuls-Wegklick (Endsystem-Kampagne, ADR-054) - der stille Gegenpart zum
Impuls-Kreislauf: das ✕ auf einer Impuls-Karte klickt den Impuls weg (aus
`open` raus, key in die Nein-Liste). Kein Chat-Echo, keine Antwortzeile -
"verstanden" statt "nochmal fragen" (Muster wie /entry/delete, ADR-051).

BEWUSST KEIN Registry-Command / kein Planner-Intent: der Wegklick ist rein
UI-intern (nur der hart verdrahtete /impulse/dismiss-Endpunkt der Browser-
API ruft ihn). Waere er ein registrierter Command, taucht seine
Beschreibung im Planner-Prompt auf und die KI koennte ihn theoretisch aus
einer Sprach-/Telegram-Eingabe waehlen - genau das soll er nicht. Deshalb
eine schlichte Modul-Funktion statt einer Command-Klasse.

configure() bekommt DIE ImpulseStore-Instanz der Runtime (dieselbe, die die
Engine befuellt - sonst saehe der eine die Nein-Liste des anderen nicht).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("jarvis.commands.impulses")

_store = None


def configure(store) -> None:
    """Von jarvis_runtime.py/main.py mit der GETEILTEN ImpulseStore-Instanz
    verdrahtet."""
    global _store
    _store = store


def dismiss(key: str) -> bool:
    """Klickt den Impuls mit diesem key (oder id) weg. Liefert True, wenn
    etwas entfernt wurde. Fail-safe: ohne verdrahteten Store -> False."""
    if _store is None:
        logger.warning("Impuls-Wegklick ohne verdrahteten Store.")
        return False
    return _store.dismiss(key)


# Kein COMMANDS-Export: absichtlich nicht in der Registry (siehe Modul-Doc).
COMMANDS: list = []
