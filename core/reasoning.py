"""
Reasoning-Kern (ADR-060/064) - der denkende Kern, LIVE am Pfad: er FUEHRT die
per `reasoning_route_intents` freigegebenen Intents (Strangler-Migration,
aktuell ~41 von 66); der klassische Router laeuft parallel und traegt den Rest.
Verdrahtung: core/planner.py (_core_decision, Whitelist als Sicherheitsgrenze).

Er bekommt das Gespraech + die Werkzeug-Schemas (aus core/tool_schemas.py) und
ENTSCHEIDET: welches Werkzeug mit welchen Argumenten - ODER nichts davon, dann
ist es ein Gespraech (chat).

Bewusst REIN gehalten:
- Die eigentliche LLM-Werkzeug-Wahl ist als Callable INJIZIERT (`tool_caller`,
  live: AIEngine.choose_tool via Function-Calling) - die Logik bleibt ohne
  echten LLM/Netz testbar.
- Das Ergebnis ist ein `Plan` in DERSELBEN Form wie beim Router
  (intent=Werkzeugname, target, parameters) - alles laeuft ueber denselben
  `commands.dispatch` + dieselben Sicherheits-Gates.

Fail-safe: jede kaputte/unbekannte Wahl faellt auf `chat` zurueck - der Kern
loest NIE eigenmaechtig eine ungewollte Aktion aus (Handeln braucht ohnehin die
Gates; hier ist schon die WAHL vorsichtig)."""
from __future__ import annotations

import logging
from typing import Callable

from core.models import Plan
from core.tool_schemas import build_tool_schemas, tool_names

logger = logging.getLogger("jarvis.reasoning")

# Die Werkzeug-Wahl des LLM: Liste [(werkzeugname, argumente), ...] - 0 =
# Gespraech, 1..n = ein oder mehrere Schritte (Multi-Step).
# argumente ~ {"target": <str|None>, "parameters": {<...>}} (siehe tool_schemas).
ToolCaller = Callable[[str, list, list], "list[tuple[str, dict]]"]


def _chat_plan(user_input: str, confidence: float) -> Plan:
    return Plan(intent="chat", target=None, confidence=confidence, raw_input=user_input)


def _to_plan(user_input: str, name: str, args: dict) -> Plan:
    """Bildet die Werkzeug-Argumente auf einen Plan ab - fuer BEIDE Schema-Formen:
    generisch ({"target":..., "parameters":{...}}) und typisiert/flach (die
    echten Felder direkt, ADR-064). Diskriminator: ein `parameters`-Objekt heisst
    generisch; sonst sind die Felder flach ('target' bleibt das Ziel, der Rest
    wird zu Plan.parameters)."""
    args = dict(args or {})
    if isinstance(args.get("parameters"), dict):
        raw_target = args.get("target")
        parameters = dict(args["parameters"])
    else:
        raw_target = args.pop("target", None)
        parameters = args
    target = (str(raw_target).strip() or None) if raw_target else None
    return Plan(intent=name, target=target, parameters=parameters,
                confidence=1.0, raw_input=user_input)


def decide(user_input: str, history: list, tool_caller: ToolCaller,
           select_tools: "Callable[[str, list], list] | None" = None) -> "list[Plan]":
    """Der Kern entscheidet: keins, ein oder MEHRERE Werkzeuge (Multi-Step) -
    oder Gespraech. Die Modell-Sicht ist der FLACHE Werkzeugkatalog (ADR-073;
    die Fassaden-Wahl wurde empirisch verworfen und lebt nur als Mess-Werkzeug
    in scripts/facade_eval.py weiter).

    `tool_caller(user_input, history, tools)` liefert eine Liste [(name, args),
    ...] (leer = Gespraech). Rueckgabe ist IMMER eine nicht-leere Liste von
    Plaenen (bei Gespraech: [chat]). Fail-safe: Ausnahme -> [chat]; unbekannte
    Werkzeuge werden uebersprungen (nie eine geratene Aktion; sind ALLE
    unbekannt -> [chat]).

    `select_tools` (Plan B, optional): filtert die Tool-Schemas VOR der Wahl auf
    die zur Eingabe relevanten (Werkzeug-Vorfilter). FAIL-OPEN: wirft der Filter
    oder liefert er nichts, werden ALLE Werkzeuge genutzt (keine Regression)."""
    tools = build_tool_schemas()
    if select_tools is not None:
        try:
            tools = select_tools(user_input, tools) or tools
        except Exception:  # noqa: BLE001 - der Vorfilter darf den Kern nie brechen
            logger.warning("Tool-Vorfilter fehlgeschlagen (fail-open: alle Tools).", exc_info=True)
    try:
        choices = tool_caller(user_input, history or [], tools)
    except Exception:  # noqa: BLE001 - eine kaputte Wahl darf nie werfen
        logger.exception("Reasoning-Kern: Werkzeug-Wahl fehlgeschlagen -> chat.")
        return [_chat_plan(user_input, 0.0)]

    if not choices:
        # Der Kern hat bewusst KEIN Werkzeug gewaehlt -> Gespraech (klare Wahl).
        return [_chat_plan(user_input, 1.0)]

    known = tool_names()
    plans: list[Plan] = []
    for name, args in choices:
        if name not in known:
            logger.warning("Reasoning-Kern waehlte unbekanntes Werkzeug %r -> uebersprungen.", name)
            continue
        plans.append(_to_plan(user_input, name, args))
    if not plans:
        return [_chat_plan(user_input, 0.0)]
    logger.info("Reasoning-Kern waehlte %d Werkzeug(e): %s.",
                len(plans), "+".join(p.intent for p in plans))
    return plans
