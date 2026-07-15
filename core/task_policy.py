"""
Task-Policy - die Sicherheitsgrenze des Auftrags-Loops (Phase B.1, B3).

Verbindliche Quelle: Bauvertrag v1.0 §6 (ADR-074). B.1 kennt genau EINE
Policy: `read_only_v1` - read_only == true, side_effect == NONE,
effective_risk == 0 (= max(base_risk, dynamic_risk), Nachtrag/§6.2).
Alles andere fuehrt VOR dem Dispatch zu einem PolicyViolation-Blocker
(BLOCKED/POLICY_VIOLATION), nie zu einer Ausfuehrung.

Die bestehende confirmation_required-Logik des Executors wird hier bewusst
NICHT wiederverwendet (sie kann statisch Bestaetigungsfreies nicht dynamisch
hochstufen - Vertrag §6.2); Approvals kommen erst mit S5.
"""
from __future__ import annotations

from core.capability_registry import CapabilityRegistry, CapabilitySpec
from core.task_models import Action, SideEffect, Task, dod_satisfied, unmet_required  # noqa: F401 (dod-Re-Export fuer Runner)

READ_ONLY_V1 = "read_only_v1"


class PolicyViolation(Exception):
    """Verstoss gegen den Sicherheitsvertrag - maschinenlesbarer Code fuer
    den strukturierten Blocker."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def freeze_contract(task: Task, registry: CapabilityRegistry) -> Task:
    """Prueft den Auftrags-Vertrag VOR dem Einfrieren (DRAFT -> READY):
    Policy bekannt, parent null (B.1), Allowlist nicht leer + vollstaendig
    registriert + read-only/risikofrei, DoD mit Pflicht-Kriterien. Die
    Allowlist wird SORTIERT eingefroren (deterministisch)."""
    if task.policy_id != READ_ONLY_V1:
        raise PolicyViolation("POLICY_VIOLATION", f"Unbekannte Policy {task.policy_id!r} (B.1: nur {READ_ONLY_V1}).")
    if task.parent_task_id is not None:
        raise PolicyViolation("POLICY_VIOLATION", "parent_task_id muss in B.1 null sein (keine Kindauftraege).")
    if not task.allowed_actions:
        raise PolicyViolation("POLICY_VIOLATION", "Leere Allowlist - ein Auftrag ohne erlaubte Aktionen ist nicht startbar.")
    if not any(c.required for c in task.definition_of_done):
        raise PolicyViolation("POLICY_VIOLATION", "Definition of Done ohne Pflicht-Kriterium - nichts waere pruefbar.")
    for intent in task.allowed_actions:
        spec = registry.get(intent)
        if spec is None:
            raise PolicyViolation("POLICY_VIOLATION", f"Aktion {intent!r} ist keine registrierte Capability.")
        _require_read_only(spec)
    task.allowed_actions = sorted(task.allowed_actions)
    return task


def validate_action(task: Task, action: Action, registry: CapabilityRegistry) -> CapabilitySpec:
    """Prueft eine vorgeschlagene Aktion VOR dem Dispatch gegen die
    EINGEFRORENE Allowlist und die read_only_v1-Regeln. Das Modell kann die
    Liste weder erweitern noch einen unbekannten Intent ausfuehren."""
    if action.intent not in task.allowed_actions:
        raise PolicyViolation(
            "POLICY_VIOLATION",
            f"Aktion {action.intent!r} steht nicht in der eingefrorenen Allowlist {task.allowed_actions}.")
    spec = registry.get(action.intent)
    if spec is None:
        raise PolicyViolation("POLICY_VIOLATION", f"Capability {action.intent!r} ist nicht registriert.")
    _require_read_only(spec)
    if action.side_effect is not SideEffect.NONE:
        raise PolicyViolation("POLICY_VIOLATION", f"Seiteneffekt {action.side_effect.value} ist in {READ_ONLY_V1} verboten.")
    # §6.2: das HOEHERE Risiko gewinnt - auch ein dynamisch hochgestuftes.
    action.base_risk = spec.base_risk
    if action.effective_risk != 0:
        raise PolicyViolation(
            "POLICY_VIOLATION",
            f"effective_risk={action.effective_risk} (base={action.base_risk}, "
            f"dynamic={action.dynamic_risk}) - {READ_ONLY_V1} erlaubt nur 0.")
    action.arguments = _validate_arguments(spec, action.arguments)
    return spec


# Grosszuegiger Deckel je Argument-String - Argumente sind Steuerwerte
# (Pfad, Suchbegriff), nie Dokumente.
_MAX_ARG_CHARS = 500

_ARG_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool}


def _validate_arguments(spec: CapabilitySpec, arguments: dict) -> dict:
    """Argument-Validierung VOR dem Dispatch (Hardening 15.07., Sol-Analyse
    Punkt 3): nur im argument_schema deklarierte Schluessel, nur Skalare,
    Typen geprueft, Strings gedeckelt und redigiert. Das Modell kann einer
    Capability keine unangekuendigten Parameter unterschieben."""
    from core.redaction import redact

    schema_props = (spec.argument_schema or {})
    clean: dict = {}
    for key, value in (arguments or {}).items():
        prop = schema_props.get(key)
        if prop is None:
            raise PolicyViolation(
                "POLICY_VIOLATION",
                f"{spec.intent}: unbekanntes Argument {key!r} (erlaubt: {sorted(schema_props)}).")
        expected = _ARG_TYPES.get(str(prop.get("type", "string")), str)
        if isinstance(value, bool) and expected is not bool:
            raise PolicyViolation("POLICY_VIOLATION", f"{spec.intent}: {key!r} hat Typ bool, erwartet {prop.get('type')}.")
        if not isinstance(value, expected):
            raise PolicyViolation(
                "POLICY_VIOLATION",
                f"{spec.intent}: {key!r} hat Typ {type(value).__name__}, erwartet {prop.get('type', 'string')}.")
        if isinstance(value, str):
            if len(value) > _MAX_ARG_CHARS:
                raise PolicyViolation(
                    "POLICY_VIOLATION",
                    f"{spec.intent}: {key!r} ist {len(value)} Zeichen lang (> {_MAX_ARG_CHARS}).")
            value = redact(value)
        clean[key] = value
    return clean


def _require_read_only(spec: CapabilitySpec) -> None:
    if not spec.read_only or spec.side_effect is not SideEffect.NONE or spec.base_risk != 0:
        raise PolicyViolation(
            "POLICY_VIOLATION",
            f"Capability {spec.intent!r} ist nicht read-only/risikofrei "
            f"(read_only={spec.read_only}, side_effect={spec.side_effect.value}, "
            f"base_risk={spec.base_risk}) - in {READ_ONLY_V1} nicht zulaessig.")
