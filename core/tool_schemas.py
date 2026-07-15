"""
Werkzeug-Schemas aus der Befehls-Registry (ADR-060/064) - die LIVE-Modell-
Sicht des Reasoning-Kerns: die vorhandenen Befehle (`commands.REGISTRY`)
werden als FLACHER Katalog von Tool-Schemas im OpenAI-Function-Calling-Format
gerendert (ADR-073: flach ist gemessen besser als jede Fassaden-Sicht).

Bewusst schmal und rein (kein LLM-Aufruf, keine Verdrahtung, kein Verhalten):
- EINE Quelle - dieselbe Registry + `description`, aus der auch der Planner-
  Prompt gebaut wird (kein zweiter Katalog, der driften kann).
- Arg-nehmende Werkzeuge tragen TYPISIERTE Schemas (core/tool_params,
  ADR-064 - der Multi-Step-Enabler); der Rest die generische
  {target, parameters}-Form. Beide bilden 1:1 auf die bestehende
  `Plan`-Struktur ab (`commands.dispatch(Plan(...))`).

Die Ausfuehrung (und damit ALLE Sicherheits-Gates: requires_confirmation etc.)
laeuft unveraendert ueber den bestehenden Executor - dieses Modul beschreibt
nur, WAS es an Werkzeugen gibt, nie wie sie ausgefuehrt werden.
"""
from __future__ import annotations

# Der Sonderfall "kein Werkzeug noetig": ruft der Kern KEIN Werkzeug, ist es ein
# Gespraech (chat). chat ist deshalb kein Werkzeug in der Liste.
_TARGET_DESC = (
    "Das Ziel/Objekt der Aktion, falls noetig (z. B. Ort beim Wetter, Repo-Alias "
    "bei einer Delegation, Suchbegriff). Weglassen, wenn der Befehl kein Ziel braucht."
)
_PARAMS_DESC = (
    "Weitere Felder je nach Befehl, wie in der Beschreibung genannt "
    '(z. B. {"day": "morgen"} beim Wetter, {"task": "..."} bei einer Delegation, '
    '{"level": 50} bei der Lautstaerke). Leeres Objekt, wenn nichts noetig ist.'
)


def _generic_params() -> dict:
    """Rueckfall-Schema fuer Werkzeuge ohne typisierte Spec: die uniforme
    {target, parameters}-Form (reine Lese-/Nullargument-Befehle)."""
    return {
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": _TARGET_DESC},
            "parameters": {
                "type": "object",
                "description": _PARAMS_DESC,
                "additionalProperties": True,
            },
        },
        "required": [],
    }


def _typed_params(spec: dict) -> dict:
    """Typisiertes Schema aus core/tool_params: echte Felder als Properties,
    additionalProperties=False - so fuellt der Kern die Argumente auch bei
    parallelen Aufrufen zuverlaessig (ADR-064)."""
    return {
        "type": "object",
        "properties": dict(spec["properties"]),
        "required": list(spec.get("required", [])),
        "additionalProperties": False,
    }


def build_tool_schemas() -> list[dict]:
    """Rendert die Registry als Liste von Function-Tool-Schemas (OpenAI-Format).
    Arg-nehmende Werkzeuge bekommen ein TYPISIERTES Schema (core/tool_params,
    ADR-064 - Multi-Step-Enabler); der Rest behaelt das generische {target,
    parameters}. Reihenfolge stabil (sortiert), damit Prompts cachebar bleiben."""
    from commands import REGISTRY
    from core.tool_params import PARAM_SCHEMAS

    schemas: list[dict] = []
    for name in sorted(REGISTRY):
        command = REGISTRY[name]
        description = (getattr(command, "description", "") or name).strip()
        spec = PARAM_SCHEMAS.get(name)
        parameters = _typed_params(spec) if spec else _generic_params()
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            }
        )
    return schemas


def tool_names() -> list[str]:
    """Die Namen aller Werkzeuge (= registrierte Befehls-Intents), sortiert."""
    from commands import REGISTRY

    return sorted(REGISTRY)
