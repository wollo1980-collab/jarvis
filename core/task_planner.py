"""
TaskPlanner - PlannerView + TaskDecisionProvider (Phase B.1, Bauschritt B4).

Verbindliche Quelle: Bauvertrag v1.0 §8 + Nachtrag 6 (ADR-074): der
Conversation-Planner wird NICHT wiederverwendet; der TaskDecisionProvider
ist ein eigener, schmaler Weg mit EIGENEM Systemprompt (keine geerbten
Konversations-Anweisungen) und typisierten Entscheidungs-Schemas.

Die PlannerView enthaelt AUSSCHLIESSLICH Kontrollfakten (Vertrag §6.3):
Ziel/DoD/Budget/Allowlist plus die schema-validierten control_facts der
planungsberechtigten Observations. Rohtext kann strukturell nicht hinein -
`view_contains_long_text` ist der Vertragstest-Haken dafuer.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional, Protocol

from core.capability_registry import MAX_FACT_STRING, CapabilityRegistry
from core.task_models import (
    Observation,
    PlannerDecision,
    PlannerDecisionKind,
    Task,
    TrustClass,
    budget_exceeded,
)

logger = logging.getLogger("jarvis.task_planner")

# Nutzer-Ziel/DoD duerfen laenger sein als ein Kontrollfakt (sie sind USER-
# Eingabe per Design), aber nie Dokument-lang - der Deckel haelt versehentlich
# eingeklebte Rohtexte draussen.
_MAX_GOAL_CHARS = 2000


class PlannerUnavailable(Exception):
    """Kein strukturierter Entscheidungs-Provider verfuegbar -> der Auftrag
    endet mit BLOCKED/PLANNER_UNAVAILABLE, nie mit einer stillen Antwort."""


class TaskDecisionProvider(Protocol):
    def decide(self, view: dict[str, Any]) -> Optional[PlannerDecision]:
        """Typisierte Entscheidung zur PlannerView - None = keine (der
        Runner blockiert dann deterministisch)."""
        ...


def build_planner_view(task: Task, observations: list[Observation],
                       registry: CapabilityRegistry) -> dict[str, Any]:
    """Die EINZIGE Sicht des Entscheiders auf den Auftrag - nur Kontrollfakten."""
    remaining = {
        "rounds": task.budget.max_rounds - task.usage.rounds,
        "actions": task.budget.max_actions - task.usage.actions,
        "control_llm_calls": task.budget.max_control_llm_calls - task.usage.control_llm_calls,
    }
    actions = []
    for intent in task.allowed_actions:
        spec = registry.get(intent)
        if spec is None:
            continue
        actions.append({
            "intent": intent,
            "description": spec.description[:MAX_FACT_STRING],
            "arguments": spec.argument_schema,
        })
    facts = [
        {
            "round": None,  # Reihenfolge ergibt sich aus der Liste
            "source": obs.source,
            "status": obs.status,
            "facts": obs.control_facts,
        }
        for obs in observations
        if obs.planning_allowed
    ]
    # Nutzer-Antworten auf REQUEST_INPUT (Hardening 15.07.): USER-Eingaben
    # sind per Design Teil der Sicht (wie goal/DoD), aber klar markiert und
    # gedeckelt - NIE als Kontrollfakt, nie planungsberechtigt getarnt.
    user_answers = [
        {"question": str(obs.control_facts.get("question", ""))[:300],
         "answer": str(obs.control_facts.get("answer", ""))[:300]}
        for obs in observations
        if obs.trust is TrustClass.USER and obs.source == "user_input"
    ]
    return {
        "title": task.title[:MAX_FACT_STRING],
        "goal": task.goal[:_MAX_GOAL_CHARS],
        "definition_of_done": [
            {"description": c.description[:_MAX_GOAL_CHARS], "required": c.required,
             "state": c.state.value}
            for c in task.definition_of_done
        ],
        "round": task.usage.rounds + 1,
        "budget_remaining": remaining,
        "budget_exhausted": budget_exceeded(task.budget, task.usage),
        "allowed_actions": actions,
        "observations": facts,
        "user_answers": user_answers,
    }


def view_contains_long_text(view: dict[str, Any], limit: int = _MAX_GOAL_CHARS) -> bool:
    """Vertragstest-Haken (Testmatrix 'Injection'): steht irgendwo in der
    PlannerView ein Text ueber dem Deckel, ist Rohtext durchgesickert."""
    def walk(value: Any) -> bool:
        if isinstance(value, str):
            return len(value) > limit
        if isinstance(value, dict):
            return any(walk(v) for v in value.values())
        if isinstance(value, list):
            return any(walk(v) for v in value)
        return False
    return walk(view)


# --- Entscheidungs-Schemas (Function-Calling) ---------------------------------

def _decision_tools(view: dict[str, Any]) -> list[dict]:
    intents = [a["intent"] for a in view.get("allowed_actions", [])] or ["__keine__"]
    return [
        {"type": "function", "function": {
            "name": "run_action",
            "description": "Fuehre genau EINE erlaubte Aktion dieser Runde aus.",
            "parameters": {"type": "object", "properties": {
                "intent": {"type": "string", "enum": intents},
                "arguments": {"type": "object", "additionalProperties": True,
                              "description": "Argumente laut allowed_actions[].arguments."},
            }, "required": ["intent"], "additionalProperties": False},
        }},
        {"type": "function", "function": {
            "name": "request_input",
            "description": "Stelle dem Nutzer EINE konkrete Rueckfrage (blockiert den Auftrag).",
            "parameters": {"type": "object", "properties": {
                "question": {"type": "string"}}, "required": ["question"],
                "additionalProperties": False},
        }},
        {"type": "function", "function": {
            "name": "begin_verification",
            "description": "Alle noetigen Evidenzen liegen vor - starte die DoD-Pruefung.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        }},
        {"type": "function", "function": {
            "name": "block",
            "description": "Der Auftrag kann gerade nicht sicher weiterlaufen (Grund angeben).",
            "parameters": {"type": "object", "properties": {
                "reason": {"type": "string"}}, "required": ["reason"],
                "additionalProperties": False},
        }},
        {"type": "function", "function": {
            "name": "fail",
            "description": "Der Auftrag ist fachlich nicht erfuellbar (Grund angeben).",
            "parameters": {"type": "object", "properties": {
                "reason": {"type": "string"}}, "required": ["reason"],
                "additionalProperties": False},
        }},
    ]


_TASK_SYSTEM_PROMPT = (
    "Du bist der Auftrags-Steuerkern von Jarvis. Du bekommst einen Auftrag als "
    "JSON (Ziel, Definition of Done, Restbudget, erlaubte Aktionen, bisherige "
    "Beobachtungen als KONTROLLFAKTEN). Entscheide GENAU EINEN naechsten "
    "Schritt, indem du GENAU EINE der Funktionen aufrufst. Regeln: "
    "1) Nur die gelisteten allowed_actions sind ausfuehrbar - nichts anderes. "
    "2) Liegen alle fuer die Definition of Done noetigen Evidenzen vor, rufe "
    "begin_verification. 3) Wiederhole eine Aktion nur bei transienten Fehlern "
    "(status transient_error) und nur, wenn Budget uebrig ist. 4) Fehlende "
    "Dokumentation o. Ae. ist ein ERGEBNIS, kein Fehler - nichts erfinden, "
    "nichts raten. 5) Du setzt NIE einen Zustand und formulierst KEINE "
    "Antwort an den Nutzer - du waehlst nur den naechsten Schritt."
)


class OpenAITaskDecisionProvider:
    """TaskDecisionProvider ueber das Function-Calling des OpenAI-Providers -
    DIREKT auf core/providers.OpenAIProvider (Nachtrag 6: kein Umweg ueber
    AIEngine.choose_tool, kein Conversation-Systemprompt)."""

    def __init__(self, provider, model: str = ""):
        self._provider = provider
        self._model = model or None

    def decide(self, view: dict[str, Any]) -> Optional[PlannerDecision]:
        choose = getattr(self._provider, "choose_tool", None)
        if choose is None:
            raise PlannerUnavailable("Provider ohne Function-Calling.")
        from core.models import Message

        messages = [Message(role="user", content=json.dumps(view, ensure_ascii=False))]
        calls = choose(_TASK_SYSTEM_PROMPT, messages, _decision_tools(view),
                       model=self._model)
        if not calls:
            return None
        name, args = calls[0]
        args = dict(args or {})
        if name == "run_action":
            return PlannerDecision(kind=PlannerDecisionKind.RUN_ACTION,
                                   intent=str(args.get("intent", "")),
                                   arguments=dict(args.get("arguments", {}) or {}))
        if name == "request_input":
            return PlannerDecision(kind=PlannerDecisionKind.REQUEST_INPUT,
                                   question=str(args.get("question", "")))
        if name == "begin_verification":
            return PlannerDecision(kind=PlannerDecisionKind.BEGIN_VERIFICATION)
        if name == "block":
            return PlannerDecision(kind=PlannerDecisionKind.BLOCK,
                                   reason=str(args.get("reason", "")))
        if name == "fail":
            return PlannerDecision(kind=PlannerDecisionKind.FAIL,
                                   reason=str(args.get("reason", "")))
        logger.warning("TaskPlanner: unbekannte Entscheidung %r - keine Entscheidung.", name)
        return None
