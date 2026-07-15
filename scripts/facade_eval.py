"""
Fassaden-Wahl als MESS-Werkzeug (ADR-073 Punkt 4) - kein Produktionspfad.

Die Acht-Werkzeuge-TOOLAUSWAHL (ADR-072 Phase A) wurde empirisch verworfen
(verschachtelt 64-66/73, zweistufig 58/73, Basislinie 66-67/73; Messprotokoll
docs/proposals/acht-werkzeuge-und-auftrags-loop-design-2026-07-14.md §3b).
Dieser Code lebt hier weiter, damit ein kuenftiger staerkerer API-Waehler
DIESELBE Messlatte durchlaufen kann: `reasoning_eval --facade [--model X]`.
Wiedervorlage-Kriterium: ADR-073 'Falsifizierbarkeit'.

Die Bereichs-Struktur selbst (TOOL_DOMAINS, intent_to_tool) bleibt in
core/capability_tools.py - sie ist Organisations-/Sicherheitsebene und
waechter-gesichert; hier wird sie nur importiert (keine zweite Wahrheit).
"""
from __future__ import annotations

import logging
import re

from core.capability_tools import TOOL_DOMAINS, intent_to_tool

logger = logging.getLogger("jarvis.facade_eval")

_EXAMPLE_RE = re.compile(r"'([^']{3,70})'")


def _action_lines(intents: "list[str]") -> str:
    """Eine knappe Zeile je Aktion: deutscher Name + BEISPIEL-Saetze aus der
    Registry-Beschreibung (Nachschaerf-Runde 1 der Messlatte: die Beispiele
    sind das staerkste Wahl-Signal - Prosa-Anrisse liessen seltene Aktionen
    auf chat fallen). Quelle bleibt die Registry (keine zweite Wahrheit)."""
    from commands import REGISTRY
    from core.intent_labels import label_for

    lines = []
    for intent in intents:
        desc = str(getattr(REGISTRY.get(intent), "description", "") or "")
        examples = _EXAMPLE_RE.findall(desc)[:2]
        if examples:
            hint = "z. B. " + " / ".join(f"«{e}»" for e in examples)
        else:
            hint = desc.split(" - ")[0].split(". ")[0].strip()[:110]
        lines.append(f"- {intent} ({label_for(intent)}): {hint}")
    return "\n".join(lines)


def _union_properties(intents: "list[str]") -> dict:
    """Union der typisierten Felder aller Aktionen des Werkzeugs (ADR-064:
    typisierte Argumente sind der Multi-Step-Enabler; gleichnamige Felder
    teilen die Semantik). Plus generisches `target`."""
    from core.tool_params import PARAM_SCHEMAS

    properties: dict = {
        "target": {"type": "string",
                   "description": "Ziel/Objekt der Aktion (z. B. Ort, Suchbegriff, Repo-Alias, Fakt)."},
    }
    for intent in intents:
        spec = PARAM_SCHEMAS.get(intent)
        for key, value in (spec or {}).get("properties", {}).items():
            properties.setdefault(key, value)
    return properties


def build_capability_schemas() -> "list[dict]":
    """Die acht Werkzeug-Schemas im Function-Calling-Format (Messrunden 1/2:
    verschachtelte Wahl). `aktion` ist Pflicht und traegt die bestehenden
    Intent-Namen als Enum."""
    schemas = []
    for tool, (desc, intents) in TOOL_DOMAINS.items():
        properties = {
            "aktion": {
                "type": "string",
                "enum": list(intents),
                "description": "Die gewuenschte Aktion dieses Bereichs (Pflicht).",
            },
            **_union_properties(intents),
        }
        schemas.append({
            "type": "function",
            "function": {
                "name": tool,
                "description": f"{desc}\nAktionen:\n{_action_lines(intents)}",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": ["aktion"],
                    "additionalProperties": False,
                },
            },
        })
    return schemas


def build_domain_schemas() -> "list[dict]":
    """Stufe 1 der Zwei-Stufen-Wahl (Messprotokoll 3b, Runde 3): NUR die acht
    Bereiche, ohne Argumente - eine leichte 8er-Wahl statt der schweren
    Verschachtelung. Die Aktions-Zeilen bleiben als Wahl-Signal enthalten."""
    schemas = []
    for tool, (desc, intents) in TOOL_DOMAINS.items():
        schemas.append({
            "type": "function",
            "function": {
                "name": tool,
                "description": f"{desc}\nAktionen:\n{_action_lines(intents)}",
                "parameters": {"type": "object", "properties": {},
                               "additionalProperties": False},
            },
        })
    return schemas


def build_action_schemas(tool: str) -> "list[dict]":
    """Stufe 2: die Aktionen EINES Bereichs im bewaehrten FLACHEN Format
    (exakt build_tool_schemas, gefiltert) - kleines Menue, volle typisierte
    Argumente, keine Verschachtelung."""
    from core.tool_schemas import build_tool_schemas

    wanted = set(TOOL_DOMAINS.get(tool, ("", []))[1])
    return [s for s in build_tool_schemas() if s["function"]["name"] in wanted]


# Deckel fuer Stufe 2: mehr als 3 Bereiche je Eingabe waere kein Auftrag mehr,
# sondern Rauschen - und jeder Bereich kostet einen (kleinen) LLM-Call.
_MAX_DOMAINS_PER_TURN = 3


def two_stage_choose(user_input: str, history: list, tool_caller) -> "list[tuple[str, dict]]":
    """Zwei-Stufen-Wahl: erst Bereich(e), dann Aktion(en) im Bereich - liefert
    direkt Legacy-Wahlen [(intent, args)]. Leer = Gespraech. Fehler der
    Stufe 2 eines Bereichs ueberspringen nur DIESEN Bereich (fail-safe);
    Fehler der Stufe 1 propagieren (der Aufrufer faengt sie wie bisher)."""
    stage1 = tool_caller(user_input, history or [], build_domain_schemas())
    domains: list[str] = []
    for name, _args in stage1 or []:
        if name in TOOL_DOMAINS and name not in domains:
            domains.append(name)
    if not domains:
        return []
    choices: list[tuple[str, dict]] = []
    valid = intent_to_tool()
    for domain in domains[:_MAX_DOMAINS_PER_TURN]:
        try:
            stage2 = tool_caller(user_input, history or [], build_action_schemas(domain))
        except Exception:  # noqa: BLE001 - ein Bereich darf die anderen nie kippen
            logger.warning("Zwei-Stufen-Wahl: Stufe 2 fuer %r fehlgeschlagen.", domain, exc_info=True)
            continue
        for name, args in stage2 or []:
            if valid.get(name) == domain:
                choices.append((name, dict(args or {})))
            else:
                logger.warning("Zwei-Stufen-Wahl: %r gehoert nicht zu %r - uebersprungen.", name, domain)
    return choices


def to_legacy_choices(choices: "list[tuple[str, dict]]") -> "list[tuple[str, dict]]":
    """Uebersetzt Fassaden-Wahlen [(tool, {aktion, ...args})] auf die
    bestehende Form [(intent, args)] - unbekanntes Tool/fehlende oder
    fremde aktion wird uebersprungen (fail-safe: der Auswerter macht
    daraus chat, nie eine geratene Aktion). Messrunden 1/2."""
    valid = intent_to_tool()
    out: list[tuple[str, dict]] = []
    for tool, args in choices:
        if tool not in TOOL_DOMAINS:
            # Legacy-Durchreiche: falls der Waehler (Test/Mix) einen alten
            # Intent-Namen liefert, bleibt er gueltig.
            if tool in valid:
                out.append((tool, args))
            else:
                logger.warning("Fassade: unbekanntes Werkzeug %r uebersprungen.", tool)
            continue
        args = dict(args or {})
        aktion = str(args.pop("aktion", "") or "").strip()
        if valid.get(aktion) != tool:
            logger.warning("Fassade: Aktion %r gehoert nicht zu %r - uebersprungen.", aktion, tool)
            continue
        out.append((aktion, args))
    return out
