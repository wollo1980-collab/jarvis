"""
Commands für das Langzeitgedächtnis (v0.4, ADR-009) - explizite
Merk-/Vergiss-Befehle über memory/long_term.py::LongTermMemory.

Die Command-Registry (commands/__init__.py) instanziiert alle
Commands beim Modul-Import, VOR Config.load()/main() - deshalb kann
LongTermMemory nicht wie sonst per Konstruktor injiziert werden (der
Pfad steht erst zur Laufzeit fest). Stattdessen: configure() wird
einmal von main.py beim Start aufgerufen (genau wie Config.load()
selbst), Tests rufen configure() mit tmp_path auf, um den echten
memory_data-Ordner nicht anzufassen.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.models import Plan, Result, Status
from memory.long_term import LongTermMemory

_long_term: Optional[LongTermMemory] = None


def configure(memory_dir: Path) -> None:
    """Von main.py einmal beim Start aufgerufen. Tests rufen dies mit
    tmp_path auf, bevor sie remember_fact/forget_fact ausführen."""
    global _long_term
    _long_term = LongTermMemory(memory_dir)


def _require_long_term() -> LongTermMemory:
    if _long_term is None:
        raise RuntimeError(
            "Langzeitgedächtnis nicht konfiguriert - commands.memory.configure() "
            "muss beim Start aufgerufen werden (siehe main.py)."
        )
    return _long_term


class RememberFactCommand:
    name = "remember_fact"
    description = (
        "Merkt sich dauerhaft einen Fakt - Projekt, Gewohnheit oder Präferenz "
        "(nur auf ausdrücklichen Zuruf, z. B. 'Merk dir, dass ...')."
    )
    # Unkritische Aktion (Sicherheitsstufe 1) - reiner Datenlayer, keine
    # Systemaktion, deshalb keine Bestätigung nötig.
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        text = (plan.target or "").strip()
        if not text:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Was genau soll ich mir merken?",
            )

        category = plan.parameters.get("category", "allgemein")
        _require_long_term().remember(text, category=category)
        return Result(status=Status.SUCCESS, message=f"Gemerkt: {text}")


class ForgetFactCommand:
    name = "forget_fact"
    description = "Löscht einen zuvor gemerkten Fakt wieder (z. B. 'Vergiss, dass ...')."
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        text = (plan.target or "").strip()
        if not text:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Was genau soll ich vergessen?",
            )

        if _require_long_term().forget(text):
            return Result(status=Status.SUCCESS, message=f"Vergessen: {text}")
        return Result(
            status=Status.FAILED,
            message=f"Dazu habe ich nichts in meinem Langzeitgedächtnis gefunden: {text}",
        )


# Registrierungspunkt für dieses Modul - commands/__init__.py liest
# diese Liste beim Start ein.
COMMANDS = [RememberFactCommand(), ForgetFactCommand()]
