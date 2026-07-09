"""
Commands fuer das Langzeitgedaechtnis (v0.4, ADR-009) - explizite
Merk-/Vergiss-Befehle ueber memory/long_term.py::LongTermMemory.

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
    tmp_path auf, bevor sie remember_fact/forget_fact ausfuehren."""
    global _long_term
    _long_term = LongTermMemory(memory_dir)


def _require_long_term() -> LongTermMemory:
    if _long_term is None:
        raise RuntimeError(
            "Langzeitgedaechtnis nicht konfiguriert - commands.memory.configure() "
            "muss beim Start aufgerufen werden (siehe main.py)."
        )
    return _long_term


class RememberFactCommand:
    name = "remember_fact"
    description = (
        "Merkt sich dauerhaft einen Fakt - Projekt, Gewohnheit oder Praeferenz "
        "(nur auf ausdruecklichen Zuruf, z. B. 'Merk dir, dass ...')."
    )
    # Unkritische Aktion (Sicherheitsstufe 1) - reiner Datenlayer, keine
    # Systemaktion, deshalb keine Bestaetigung noetig.
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        text = (plan.target or "").strip()
        if not text:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Was genau darf ich mir merken, Sir?",
            )

        category = plan.parameters.get("category", "allgemein")
        fact = _require_long_term().remember(text, category=category)
        # Persona-Pass (2026-07-09); fact.text statt text, damit das Echo eine
        # etwaige Redaction (ADR-040) sichtbar macht.
        return Result(
            status=Status.SUCCESS,
            message=f"Gemerkt, Sir — dauerhaft: {fact.text}",
        )


class ForgetFactCommand:
    name = "forget_fact"
    description = "Loescht einen zuvor gemerkten Fakt wieder (z. B. 'Vergiss, dass ...')."
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        text = (plan.target or "").strip()
        if not text:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Was soll ich genau vergessen?",
            )

        if _require_long_term().forget(text):
            # Formulierung entwertet den Fakt ausdruecklich (Welle 1.2,
            # "Meister"-Fix): die Bestaetigung landet im Gespraechsverlauf -
            # "gilt ab sofort nicht mehr" verstaerkt das Loeschen, statt den
            # alten Wortlaut nur zu wiederholen.
            return Result(
                status=Status.SUCCESS,
                message=(
                    f"Erledigt - das habe ich aus meinem Langzeitgedächtnis entfernt "
                    f"und es gilt ab sofort nicht mehr: {text}"
                ),
            )
        return Result(
            status=Status.FAILED,
            message=f"Dazu habe ich in meinem Langzeitgedächtnis nichts gefunden: {text}",
        )


class ListFactsCommand:
    name = "list_facts"
    description = (
        "Zeigt alle dauerhaft gemerkten Fakten des Langzeitgedaechtnisses mit "
        "Kategorie (z. B. 'was hast du dir gemerkt?', 'zeig dein Gedaechtnis', "
        "'welche Fakten kennst du ueber mich?'). Nur lesend."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        facts = _require_long_term().all_facts()
        if not facts:
            return Result(
                status=Status.SUCCESS,
                message="Mein Langzeitgedächtnis ist leer, Sir — ein unbeschriebenes Blatt.",
            )
        lines = "\n".join(f"- ({f.category}) {f.text}" for f in facts)
        return Result(
            status=Status.SUCCESS,
            message=f"Mein Langzeitgedächtnis, Sir — {len(facts)} Einträge:\n{lines}",
            data={"count": len(facts)},
        )


# Registrierungspunkt fuer dieses Modul - commands/__init__.py liest
# diese Liste beim Start ein.
COMMANDS = [RememberFactCommand(), ForgetFactCommand(), ListFactsCommand()]
