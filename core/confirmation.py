"""
ConfirmationGate (ADR-045) - der Antwortkanal fuer den bestehenden
Executor-Bestaetigungsdialog (Stufe 2/3, Handbook Kap. 10) ueber Remote-Kanaele.

Ein thread-sicherer Ein-Platz-Briefkasten:
- Executor-Seite (Runtime-Worker): `wait_answer(timeout)` blockiert, bis eine
  Antwort eintrifft oder das Zeitfenster ablaeuft. Timeout liefert "" und
  laeuft damit in den bestehenden Abbruchpfad des Executors ("Abgebrochen -
  keine Bestaetigung erhalten") - fail-closed bleibt der Kern.
- Kanal-Seite (z. B. Telegram-Handler): `offer_answer(text)` liefert True,
  wenn gerade eine Rueckfrage offen ist und der Text als Antwort konsumiert
  wurde - der Aufrufer reicht ihn dann NICHT an den Planner weiter. Sonst
  False (normale Verarbeitung).

Genau EINE offene Rueckfrage (Single-Slot): der Runtime-Worker ist seriell,
mehr kann es nie geben; ein zweiter wait_answer waehrend einer offenen
Rueckfrage gibt sofort "" zurueck (defensiv, sollte nie passieren).
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("jarvis.confirmation")


class ConfirmationGate:
    def __init__(self):
        self._cond = threading.Condition()
        self._waiting = False
        self._answer: str | None = None

    def wait_answer(self, timeout: float) -> str:
        """Blockiert bis zur Antwort oder bis zum Timeout ("")."""
        with self._cond:
            if self._waiting:
                logger.error("wait_answer waehrend offener Rueckfrage - fail closed.")
                return ""
            self._waiting = True
            self._answer = None
            deadline = time.monotonic() + timeout
            try:
                while self._answer is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._cond.wait(remaining)
                if self._answer is None:
                    logger.info("Bestaetigungs-Rueckfrage ohne Antwort (%.0fs) - fail closed.", timeout)
                return self._answer if self._answer is not None else ""
            finally:
                self._waiting = False
                self._answer = None

    def offer_answer(self, text: str) -> bool:
        """Bietet eine eingehende Nachricht als Antwort an. True = konsumiert
        (Aufrufer darf sie NICHT weiterverarbeiten), False = keine Rueckfrage
        offen (normale Verarbeitung)."""
        with self._cond:
            if not self._waiting or self._answer is not None:
                return False
            self._answer = text
            self._cond.notify_all()
            return True
