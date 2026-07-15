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
from typing import Callable, Optional

from core.models import Plan, Result, Status
from memory.long_term import LongTermMemory

_long_term: Optional[LongTermMemory] = None
# Sinn-Nachbar-Suche (Kundenreview 13.07., Duplikate): liefert zu einem neuen
# Fakt den sinngleichen BESTEHENDEN (oder None). Von der Runtime injiziert
# (Semantik-Index); ohne Injektion greift nur die exakte Dedupe wie bisher.
_similar_fact_fn: Optional[Callable[[str], Optional[str]]] = None


def configure(memory_dir: Path,
              similar_fact_fn: Optional[Callable[[str], Optional[str]]] = None) -> None:
    """Von main.py/jarvis_runtime.py einmal beim Start aufgerufen. Tests rufen
    dies mit tmp_path auf, bevor sie remember_fact/forget_fact ausfuehren."""
    global _long_term, _similar_fact_fn
    _long_term = LongTermMemory(memory_dir)
    _similar_fact_fn = similar_fact_fn


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
        "(nur auf ausdruecklichen Zuruf, z. B. 'Merk dir, dass ...'). target = "
        "der GANZE zu merkende Fakt im Wortlaut OHNE Trigger-Worte, NICHT in "
        "Einzelteile zerlegen (z. B. 'merk dir, dass ich meinen Kaffee schwarz "
        "trinke' -> target='trinkt seinen Kaffee schwarz'; 'ich wohne in "
        "Musterstadt' -> target='wohnt in Musterstadt'). Keine parameters."
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

        # Sinngleiches nicht doppelt anlegen (Kundenreview 13.07.: dieselbe
        # Praeferenz stand dreimal im Profil). Ehrlich sagen, was schon da
        # ist - und die Tuer nennen, falls es doch etwas Neues ist.
        if _similar_fact_fn is not None:
            try:
                twin = _similar_fact_fn(text)
            except Exception:  # noqa: BLE001 - Dedupe stoert das Merken nie
                twin = None
            if twin and " ".join(twin.lower().split()) != " ".join(text.lower().split()):
                return Result(
                    status=Status.SUCCESS,
                    message=(
                        f"Das habe ich sinngemäß schon notiert, Sir: «{twin}». "
                        f"Ich lege nichts doppelt an — wenn es wirklich etwas "
                        f"anderes ist, formulier es kurz um."
                    ),
                )

        category = plan.parameters.get("category", "allgemein")
        fact = _require_long_term().remember(text, category=category)
        # Persona-Pass (2026-07-09); fact.text statt text, damit das Echo eine
        # etwaige Redaction (ADR-040) sichtbar macht. data.text = der
        # GESPEICHERTE Wortlaut - das nackte «nein» danach (Undo, 15.07.)
        # loescht damit exakt, nie einen aehnlichen Nachbarn.
        return Result(
            status=Status.SUCCESS,
            message=f"Gemerkt, Sir — dauerhaft: {fact.text}",
            data={"text": fact.text},
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

        # exact (Nacht-Audit-Fix B): stille UI-Endpunkte verlangen den
        # exakten Treffer; Sprach-/Chat-Weg bleibt beim Teilstring.
        if _require_long_term().forget(text, exact=bool(plan.parameters.get("exact"))):
            # Formulierung entwertet den Fakt ausdruecklich (Welle 1.2,
            # "Meister"-Fix): die Bestaetigung landet im Gespraechsverlauf -
            # "gilt ab sofort nicht mehr" verstaerkt das Loeschen, statt den
            # alten Wortlaut nur zu wiederholen. Undo-Hinweis (Kundenreview
            # 13.07.): nichts verschwindet mehr hart, der Papierkorb faengt es.
            return Result(
                status=Status.SUCCESS,
                message=(
                    f"Erledigt - das habe ich aus meinem Langzeitgedächtnis entfernt "
                    f"und es gilt ab sofort nicht mehr: {text}. "
                    f"(Falls das ein Versehen war: «stell den Fakt wieder her».)"
                ),
            )
        return Result(
            status=Status.FAILED,
            message=f"Dazu habe ich in meinem Langzeitgedächtnis nichts gefunden: {text}",
        )


class RestoreFactCommand:
    name = "restore_fact"
    description = (
        "Holt einen geloeschten Fakt aus dem Papierkorb zurueck (z. B. 'stell "
        "den Fakt wieder her', 'das Loeschen war ein Versehen'). target = "
        "Suchtext; ohne target kommt der ZULETZT geloeschte Fakt zurueck."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        text = (plan.target or plan.parameters.get("text") or "").strip()
        fact = _require_long_term().restore(text)
        if fact is None:
            return Result(
                status=Status.FAILED,
                message=(
                    "Im Papierkorb liegt dazu nichts, Sir"
                    + (f" (gesucht: {text})" if text else "")
                    + " — dann gibt es auch nichts wiederherzustellen."
                ),
            )
        return Result(
            status=Status.SUCCESS,
            message=f"Wiederhergestellt, Sir — gilt wieder: {fact.text}",
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
COMMANDS = [RememberFactCommand(), ForgetFactCommand(), RestoreFactCommand(), ListFactsCommand()]
