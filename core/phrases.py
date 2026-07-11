"""
Persona-Variation (Nutzungslauf-Befund 2026-07-10: wiederkehrende Saetze
wie das immergleiche "Notiert, Sir" wirken mechanisch). pick() waehlt
zufaellig eine Variante - FAKTEN bleiben exakt, nur der Rahmen atmet.

Bewusst klein gehalten: kein Template-System, keine Zustaende - Commands
definieren ihre Varianten als Modul-Konstanten (Tests pruefen gegen die
Pools statt gegen einen festen Satz).
"""
from __future__ import annotations

import random


def pick(*variants: str) -> str:
    """Eine Variante, zufaellig - mindestens eine muss es geben."""
    return random.choice(variants)
