"""Tests fuer core/confirmation.py (ADR-045) - der Ein-Platz-Briefkasten
zwischen Executor-Rueckfrage (Runtime-Worker) und Kanal-Antwort (z. B.
Telegram-Handler-Thread). Fail-closed: Timeout/keine Antwort => ""."""
from __future__ import annotations

import threading
import time

from core.confirmation import ConfirmationGate


def _offer_until_accepted(gate: ConfirmationGate, text: str, attempts: int = 200) -> bool:
    """Bietet die Antwort an, bis der Warte-Thread bereit ist (max ~2 s)."""
    for _ in range(attempts):
        if gate.offer_answer(text):
            return True
        time.sleep(0.01)
    return False


def test_offer_without_pending_question_is_rejected():
    gate = ConfirmationGate()
    assert gate.offer_answer("ja") is False  # normale Nachricht, kein Konsum


def test_answer_reaches_waiting_worker():
    gate = ConfirmationGate()
    received = {}

    def worker():
        received["answer"] = gate.wait_answer(timeout=5.0)

    t = threading.Thread(target=worker)
    t.start()
    assert _offer_until_accepted(gate, "HERUNTERFAHREN")
    t.join(timeout=5.0)

    assert received["answer"] == "HERUNTERFAHREN"  # exakte Phrase unveraendert


def test_timeout_returns_empty_fail_closed():
    gate = ConfirmationGate()
    assert gate.wait_answer(timeout=0.05) == ""


def test_late_answer_after_timeout_is_rejected():
    gate = ConfirmationGate()
    assert gate.wait_answer(timeout=0.05) == ""
    # Die zu spaete Antwort wird NICHT konsumiert - sie ist wieder eine
    # normale Nachricht (kein stilles Verschlucken).
    assert gate.offer_answer("ja") is False


def test_exactly_one_answer_is_consumed():
    gate = ConfirmationGate()
    received = {}

    def worker():
        received["answer"] = gate.wait_answer(timeout=5.0)

    t = threading.Thread(target=worker)
    t.start()
    assert _offer_until_accepted(gate, "ja")
    t.join(timeout=5.0)

    assert received["answer"] == "ja"
    assert gate.offer_answer("nein") is False  # Slot ist wieder frei/leer


def test_gate_is_reusable_for_the_next_question():
    gate = ConfirmationGate()
    for expected in ("ja", "nein"):
        received = {}
        t = threading.Thread(target=lambda: received.setdefault("a", gate.wait_answer(timeout=5.0)))
        t.start()
        assert _offer_until_accepted(gate, expected)
        t.join(timeout=5.0)
        assert received["a"] == expected
