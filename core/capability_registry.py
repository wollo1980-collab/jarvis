"""
Capability-Registry + ObservationReducer (Phase B.1, Bauschritt B3).

Verbindliche Quelle: Bauvertrag v1.0 §6.1/§6.3 (ADR-074, Kernentscheidung 3).
NUR ausdruecklich registrierte Capabilities sind fuer Auftraege sichtbar -
die Chat-Kommandos werden nicht pauschal freigeschaltet.

Nachtrag 1: `CapabilitySpec.domain` ist ein EIGENES Feld und wird gegen die
acht TOOL_DOMAINS-Schluesselnamen validiert - Capabilities kommen NICHT in
TOOL_DOMAINS (der Vollstaendigkeits-Waechter dort lehnt Geister ab).

Der ObservationReducer ist die Naht zwischen Data- und Control-Plane:
er trennt jedes Capability-Ergebnis in schema-validierte KONTROLLFAKTEN
(kurze Skalare, laengengedeckelt - Rohtext kann hier strukturell nicht
durchsickern) und ein REDIGIERTES Rohdaten-Artefakt (nur fuer die
handlungsunfaehige Berichtsgenerierung; Vertrag §6.3, ADR-061).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from core.capability_tools import TOOL_DOMAINS
from core.redaction import redact
from core.task_models import Action, Observation, SideEffect, TrustClass

logger = logging.getLogger("jarvis.capability_registry")

# Kontrollfakten sind KURZE Skalare - alles Laengere ist Rohtext und gehoert
# ins Artefakt. Der Deckel ist die strukturelle Injection-Grenze (§6.3).
MAX_FACT_STRING = 300
MAX_FACT_LIST = 100


@dataclass
class CapabilityResult:
    """Rohergebnis einer Capability-Ausfuehrung - der Reducer trennt es."""
    status: str                      # "ok" | "transient_error" | "error"
    control_facts: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""               # -> Artefakt (redigiert), NIE Planung
    error_code: str = ""
    retryable: bool = False


# executor(action, context) -> CapabilityResult; context ist ein kleines
# dict (z. B. {"cancel_event": Event}) - keine Runtime-Objekte.
CapabilityExecutor = Callable[[Action, dict], CapabilityResult]


class FactSchemaViolation(ValueError):
    """Ein Adapter hat den Kontrollfakten-Vertrag verletzt (Programmfehler -
    laut scheitern, nie still durchreichen)."""


@dataclass(frozen=True)
class CapabilitySpec:
    intent: str
    domain: str                      # TOOL_DOMAINS-Schluesselname (Nachtrag 1)
    description: str
    executor: CapabilityExecutor
    fact_schema: dict[str, type]     # erlaubte control_facts: Name -> Typ
    argument_schema: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    base_risk: int = 0
    side_effect: SideEffect = SideEffect.NONE
    repeatable: bool = True
    timeout_seconds: float = 120.0
    supports_cancel: bool = False
    verifier_kind: str = ""


class CapabilityRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, CapabilitySpec] = {}

    def register(self, spec: CapabilitySpec) -> None:
        if spec.domain not in TOOL_DOMAINS:
            raise ValueError(
                f"CapabilitySpec.domain {spec.domain!r} ist kein TOOL_DOMAINS-"
                f"Bereich (erlaubt: {sorted(TOOL_DOMAINS)})."
            )
        if spec.intent in self._specs:
            raise ValueError(f"Capability {spec.intent!r} ist bereits registriert.")
        self._specs[spec.intent] = spec

    def get(self, intent: str) -> Optional[CapabilitySpec]:
        return self._specs.get(intent)

    def names(self) -> list[str]:
        return sorted(self._specs)


def validate_control_facts(spec: CapabilitySpec, facts: dict[str, Any]) -> dict[str, Any]:
    """Schema-Validierung der Kontrollfakten (Vertrag §6.3): nur bekannte
    Schluessel, nur Skalare bzw. Listen kurzer Skalare, Strings laengen-
    gedeckelt UND redigiert. Verstoss -> FactSchemaViolation (laut)."""
    clean: dict[str, Any] = {}
    for key, value in (facts or {}).items():
        expected = spec.fact_schema.get(key)
        if expected is None:
            raise FactSchemaViolation(
                f"{spec.intent}: unbekannter Kontrollfakt {key!r} "
                f"(erlaubt: {sorted(spec.fact_schema)}).")
        clean[key] = _validate_value(spec.intent, key, value, expected)
    return clean


def _validate_value(intent: str, key: str, value: Any, expected: type) -> Any:
    if expected is list:
        if not isinstance(value, list) or len(value) > MAX_FACT_LIST:
            raise FactSchemaViolation(f"{intent}: {key!r} muss eine Liste (<= {MAX_FACT_LIST}) sein.")
        return [_validate_scalar(intent, key, item) for item in value]
    if not isinstance(value, expected) or isinstance(value, bool) and expected is not bool:
        raise FactSchemaViolation(
            f"{intent}: {key!r} hat Typ {type(value).__name__}, erwartet {expected.__name__}.")
    return _validate_scalar(intent, key, value)


def _validate_scalar(intent: str, key: str, value: Any) -> Any:
    if isinstance(value, str):
        if len(value) > MAX_FACT_STRING:
            raise FactSchemaViolation(
                f"{intent}: {key!r} ist {len(value)} Zeichen lang (> {MAX_FACT_STRING}) - "
                f"Rohtext gehoert ins Artefakt, nie in die Kontrollfakten.")
        return redact(value)
    if isinstance(value, dict):
        # Ein Fakt-Eintrag darf ein FLACHES Objekt kurzer Skalare sein
        # (z. B. je Projekt {name, has_state, ...}) - nie tiefer.
        return {k: _validate_scalar(intent, f"{key}.{k}", v) for k, v in value.items()
                if not isinstance(v, (dict, list))}
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    raise FactSchemaViolation(f"{intent}: {key!r} traegt nicht-skalaren Typ {type(value).__name__}.")


def reduce_observation(spec: CapabilitySpec, action: Action, result: CapabilityResult,
                       store, task_id: str) -> Observation:
    """Data-/Control-Plane-Naht: schreibt das REDIGIERTE Rohdaten-Artefakt
    ZUERST (Vertrag §7), validiert die Kontrollfakten gegen das Schema und
    liefert die Observation (Vertrauensklasse ADAPTER_VERIFIED - unsere
    Adapter, unser Schema; Rohtexte bleiben EXTERNAL_UNTRUSTED im Artefakt)."""
    artifact_ref, artifact_hash = "", ""
    if result.raw_text:
        artifact_ref, artifact_hash = store.write_artifact(
            task_id, result.raw_text, kind=spec.intent)
    facts = validate_control_facts(spec, result.control_facts)
    if result.error_code:
        facts = {**facts, "error_code": redact(str(result.error_code))[:MAX_FACT_STRING]}
    return Observation(
        task_id=task_id,
        action_id=action.action_id,
        source=spec.intent,
        trust=TrustClass.ADAPTER_VERIFIED,
        status=result.status,
        control_facts=facts,
        artifact_ref=artifact_ref,
        artifact_hash=artifact_hash,
    )
