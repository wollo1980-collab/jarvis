"""
Zentrale Datenmodelle: Plan, Result, Status, Message.

Noch kein voller Planner – aber saubere, typisierte Strukturen,
die später ohne Bruch an bestehenden Aufrufern erweitert werden können.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class Status(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    NEEDS_CLARIFICATION = "needs_clarification"

    @property
    def symbol(self) -> str:
        """Executor-Regeln (Handbook Kap. 5): ✓ Erfolg, ✗ Fehler, ? Unsicher."""
        return {
            Status.SUCCESS: "✓",
            Status.FAILED: "✗",
            Status.NEEDS_CLARIFICATION: "?",
        }[self]


@dataclass
class Result:
    """Rückgabewert jeder externen Aktion. Jede Aktion liefert einen
    nachvollziehbaren Status zurück – keine stillen Fehler."""
    status: Status
    message: str
    data: Optional[dict[str, Any]] = None

    @property
    def ok(self) -> bool:
        return self.status == Status.SUCCESS


@dataclass
class Plan:
    """Von der KI erzeugter Plan. Die KI kennt keine Systembefehle,
    sie erzeugt ausschließlich Intent + Target + Parameter."""
    intent: str
    target: Optional[str] = None
    parameters: dict[str, Any] = field(default_factory=dict)
    raw_input: str = ""
    confidence: float = 1.0


@dataclass
class Message:
    """Ein Eintrag im Gesprächsgedächtnis."""
    role: str  # "user" | "assistant"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_openai_format(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}
