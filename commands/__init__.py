"""
Command Registry + minimaler Dispatch.

Kein voller Executor mit State-Machine/Async (folgt in v0.3) - aber
neue Commands brauchen nur eine Registrierung in ihrem Modul, keine
Änderung an bestehendem Code. Der Dispatch selbst führt niemals
eigene Business-Logik aus, er koordiniert nur.
"""
from __future__ import annotations

import logging
from typing import Protocol

from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands")


class Command(Protocol):
    name: str

    def execute(self, plan: Plan) -> Result: ...


REGISTRY: dict[str, Command] = {}


def register(command: Command) -> None:
    if command.name in REGISTRY:
        raise ValueError(f"Command '{command.name}' ist bereits registriert.")
    REGISTRY[command.name] = command


def dispatch(plan: Plan) -> Result:
    """Sucht den passenden Command über den Intent und führt ihn aus."""
    command = REGISTRY.get(plan.intent)

    if command is None:
        if plan.intent == "chat":
            # Kein Systembefehl, sondern normale Konversation.
            return Result(status=Status.SUCCESS, message="", data={"chat": True})
        logger.info("Unbekannter Intent: %s", plan.intent)
        return Result(
            status=Status.NEEDS_CLARIFICATION,
            message=f"Ich kenne keinen Befehl für '{plan.intent}'.",
        )

    try:
        return command.execute(plan)
    except Exception as e:
        logger.exception("Command '%s' fehlgeschlagen", plan.intent)
        return Result(status=Status.FAILED, message=f"Fehler bei '{plan.intent}': {e}")


def _register_all() -> None:
    from commands import installer, memory, monitor, system

    for module in (system, memory, monitor, installer):
        for command in getattr(module, "COMMANDS", []):
            register(command)


_register_all()
