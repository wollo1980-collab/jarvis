"""
ExecutionLease - der gemeinsame Single-Flight-Koordinator (ADR-074 Nachtrag 4).

Genau EIN externer Ausfuehrungspfad zur Zeit: der TaskService (Phase B) und
die Legacy-Delegation (ADR-035) teilen sich DIESE eine Sperre, statt dass
der TaskService direkt `_delegation_active` aus der Runtime abfragt. Ein
Regressionstest haelt fest, dass nie zwei Pfade gleichzeitig laufen.

Bewusst klein: nicht-blockierendes acquire mit Besitzer-Namen, release nur
durch den Besitzer (fail-loud bei Fremd-Release - das waere ein Programm-
fehler, kein Betriebszustand).
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger("jarvis.execution_lease")


class ExecutionLease:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owner: Optional[str] = None

    @property
    def owner(self) -> Optional[str]:
        return self._owner

    @property
    def busy(self) -> bool:
        return self._owner is not None

    def acquire(self, owner: str) -> bool:
        """True = Lease gehoert jetzt `owner`; False = ein anderer Pfad
        laeuft bereits (Aufrufer lehnt hoeflich ab oder wartet selbst)."""
        with self._lock:
            if self._owner is not None:
                return False
            self._owner = owner
            logger.info("ExecutionLease vergeben an %r.", owner)
            return True

    def release(self, owner: str) -> None:
        with self._lock:
            if self._owner != owner:
                raise RuntimeError(
                    f"ExecutionLease: {owner!r} will freigeben, Besitzer ist {self._owner!r}.")
            self._owner = None
            logger.info("ExecutionLease freigegeben von %r.", owner)
