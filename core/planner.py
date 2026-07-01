"""
Planner: zerlegt eine Nutzereingabe in eine geordnete Liste von Plänen
(Schritten). v0.3-Ansatz bewusst einfach (siehe ADR-004): keine eigene
Multi-Step-JSON-Struktur in der KI-Antwort, stattdessen wird die
Eingabe an einfachen Konnektoren ("und", "und dann", "danach", ";")
in Teilsätze gesplittet und jeder Teilsatz einzeln an die KI
geschickt (get_plan bleibt unverändert - kein Bruch an core/ai.py).

Warum so einfach? Regel 6 (Keine Architecture Astronautics) und
Regel 4 (90/10-Prinzip): eine naive Trennung deckt den heutigen
Bedarf (2-3 Aktionen pro Satz) ab. Eine "echte" Multi-Step-Planung
mit Rückfrage-Loops ist ein Later-Feature (siehe Handbook Kap. 27).

Falsifizierbarkeit: gilt als unzureichend, wenn Nutzer regelmäßig
zusammengesetzte Sätze verwenden, die die Splitter-Heuristik nicht
sauber trennt (z. B. verschachtelte "und" in einem Objektnamen).
Dann Review in v0.4.
"""
from __future__ import annotations

import logging
import re

from core.ai import AIEngine
from core.models import Message, Plan

logger = logging.getLogger("jarvis.planner")

# Reihenfolge wichtig: längere Konnektoren zuerst prüfen, damit
# "und dann" nicht schon beim kürzeren "und" auseinandergerissen wird.
_SPLIT_PATTERN = re.compile(r"\s+(?:und dann|danach|und)\s+|;\s*", flags=re.IGNORECASE)


class Planner:
    def __init__(self, ai: AIEngine):
        self.ai = ai

    def plan(self, user_input: str, history: list[Message]) -> list[Plan]:
        """Zerlegt user_input in 1..n Teilsätze und holt für jeden
        Teilsatz einen eigenen Plan von der KI. Reihenfolge bleibt
        erhalten - Schritt 1 wird vor Schritt 2 ausgeführt."""
        parts = [p.strip() for p in _SPLIT_PATTERN.split(user_input) if p.strip()]

        if not parts:
            parts = [user_input]

        if len(parts) > 1:
            logger.info("Eingabe in %d Schritte zerlegt: %s", len(parts), parts)

        return [self.ai.get_plan(part, history) for part in parts]
