"""
Auftragsdatenmodell + Zustandsmaschine (Phase B.1, Bauschritt B1).

Verbindliche Quelle: ADR-074 + docs/proposals/phase-b-bauvertrag-2026-07-14.md
(v1.0), §4 Datenmodell und §5 Zustandsmaschine. Dieses Modul enthaelt
AUSSCHLIESSLICH pure Datentypen und die Transitionsregeln - keine
Persistenz (B2), keine Policy/Registry (B3), keinen Runner (B4).

Kernregeln, die hier strukturell erzwungen werden:
- RUNNING -> COMPLETED ist verboten; der Weg fuehrt IMMER ueber VERIFYING.
- Terminale Zustaende (COMPLETED/FAILED/CANCELLED) sind unveraenderlich.
- Ein Modell setzt nie selbst einen Zustand - es liefert nur eine typisierte
  PlannerDecision (RUN_ACTION | REQUEST_INPUT | BEGIN_VERIFICATION | BLOCK |
  FAIL), die der Runner validiert.
- Kein Auftrag gilt als erfuellt, solange ein erforderliches DoD-Kriterium
  nicht PASSED ist (dod_satisfied/unmet_required als pure Praedikate).

Serialisierung: to_dict/from_dict je Objekt (schema_version=1) - die
Grundlage fuer das Ereignisjournal in B2. Zeitstempel sind ISO-8601 in UTC.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    """UTC-Zeitstempel (Vertrag §4: alle Zeitfelder in UTC)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


# --- Zustaende ---------------------------------------------------------------

class TaskStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    BLOCKED = "BLOCKED"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
)

# Vertrag §5 - die EINZIGE Wahrheit ueber erlaubte Uebergaenge.
# RUNNING enthaelt bewusst KEIN COMPLETED (immer ueber VERIFYING).
ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.DRAFT: frozenset({TaskStatus.READY, TaskStatus.CANCELLED}),
    TaskStatus.READY: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED}),
    TaskStatus.RUNNING: frozenset({
        TaskStatus.WAITING_APPROVAL, TaskStatus.BLOCKED, TaskStatus.VERIFYING,
        TaskStatus.FAILED, TaskStatus.CANCELLED,
    }),
    TaskStatus.WAITING_APPROVAL: frozenset({
        TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.CANCELLED,
    }),
    TaskStatus.BLOCKED: frozenset({
        TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED,
    }),
    TaskStatus.VERIFYING: frozenset({
        TaskStatus.COMPLETED, TaskStatus.RUNNING, TaskStatus.BLOCKED,
        TaskStatus.FAILED, TaskStatus.CANCELLED,
    }),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


class IllegalTransition(ValueError):
    """Verbotener Zustandsuebergang - der Store journalisiert nur Gueltiges."""


def can_transition(source: TaskStatus, target: TaskStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(source, frozenset())


def validate_transition(source: TaskStatus, target: TaskStatus) -> None:
    """Wirft IllegalTransition mit klarem Grund; terminale Zustaende nennen
    ihre Unveraenderlichkeit ausdruecklich (Testmatrix 'Zustaende')."""
    if source in TERMINAL_STATES:
        raise IllegalTransition(
            f"{source.value} ist terminal - keine weiteren Uebergaenge erlaubt."
        )
    if not can_transition(source, target):
        raise IllegalTransition(
            f"Uebergang {source.value} -> {target.value} ist nicht erlaubt "
            f"(erlaubt: {sorted(s.value for s in ALLOWED_TRANSITIONS[source])})."
        )


# --- Typisierte Planner-Entscheidung (Vertrag §5/§8) -------------------------

class PlannerDecisionKind(str, Enum):
    RUN_ACTION = "RUN_ACTION"
    REQUEST_INPUT = "REQUEST_INPUT"
    BEGIN_VERIFICATION = "BEGIN_VERIFICATION"
    BLOCK = "BLOCK"
    FAIL = "FAIL"


@dataclass
class PlannerDecision:
    """Das EINZIGE, was ein Modell liefern darf - nie einen Zustand. Der
    Runner (B4) validiert Kind + Argumente deterministisch."""
    kind: PlannerDecisionKind
    intent: str = ""                 # nur RUN_ACTION
    arguments: dict[str, Any] = field(default_factory=dict)  # nur RUN_ACTION
    question: str = ""               # nur REQUEST_INPUT
    reason: str = ""                 # BLOCK/FAIL: maschinenlesbarer Grund


# --- Weitere Enums (Vertrag §4/§6) -------------------------------------------

class CriterionState(str, Enum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class ActionState(str, Enum):
    PROPOSED = "PROPOSED"
    AUTHORIZED = "AUTHORIZED"
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


class EffectState(str, Enum):
    NONE = "NONE"
    NOT_STARTED = "NOT_STARTED"
    APPLIED = "APPLIED"
    VERIFIED = "VERIFIED"
    UNKNOWN = "UNKNOWN"
    COMPENSATED = "COMPENSATED"


class SideEffect(str, Enum):
    NONE = "NONE"
    LOCAL_WRITE = "LOCAL_WRITE"      # ab S5 - in B.1 nie zugelassen
    EXTERNAL = "EXTERNAL"            # ab S5 - in B.1 nie zugelassen


class TrustClass(str, Enum):
    SYSTEM = "SYSTEM"
    ADAPTER_VERIFIED = "ADAPTER_VERIFIED"
    USER = "USER"
    EXTERNAL_UNTRUSTED = "EXTERNAL_UNTRUSTED"
    MODEL_DERIVED = "MODEL_DERIVED"


# Nur diese Klassen duerfen den naechsten Aktionsschritt beeinflussen
# (Vertrag §6.3); alles andere erreicht nur die Berichtsgenerierung.
PLANNING_TRUSTED: frozenset[TrustClass] = frozenset(
    {TrustClass.SYSTEM, TrustClass.ADAPTER_VERIFIED}
)


class ApprovalState(str, Enum):
    OPEN = "OPEN"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"


# --- Budget & Verbrauch (Vertrag §4, Nachtrag 2: getrennte LLM-Budgets) ------

@dataclass
class Budget:
    """Harte Grenzen; Standardwerte = B.1-Vertrag. Kosten werden erfasst,
    aber (noch) nicht als harte Grenze ausgegeben."""
    max_rounds: int = 3
    max_actions: int = 3
    max_control_llm_calls: int = 6
    max_data_llm_calls: int = 12
    max_total_llm_calls: int = 18
    max_elapsed_seconds: float = 600.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_rounds": self.max_rounds,
            "max_actions": self.max_actions,
            "max_control_llm_calls": self.max_control_llm_calls,
            "max_data_llm_calls": self.max_data_llm_calls,
            "max_total_llm_calls": self.max_total_llm_calls,
            "max_elapsed_seconds": self.max_elapsed_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Budget":
        default = cls()
        return cls(
            max_rounds=int(data.get("max_rounds", default.max_rounds)),
            max_actions=int(data.get("max_actions", default.max_actions)),
            max_control_llm_calls=int(
                data.get("max_control_llm_calls", default.max_control_llm_calls)),
            max_data_llm_calls=int(
                data.get("max_data_llm_calls", default.max_data_llm_calls)),
            max_total_llm_calls=int(
                data.get("max_total_llm_calls", default.max_total_llm_calls)),
            max_elapsed_seconds=float(
                data.get("max_elapsed_seconds", default.max_elapsed_seconds)),
        )


@dataclass
class Usage:
    """Verbrauch - Control- und Data-Plane-Calls GETRENNT (Nachtrag 2:
    die Berichtsgenerierung darf das Planungs-Budget nicht fressen)."""
    rounds: int = 0
    actions: int = 0
    control_llm_calls: int = 0
    data_llm_calls: int = 0
    elapsed_seconds: float = 0.0
    cost_usd: Optional[float] = None   # erfasst, keine harte Grenze (B.1)

    @property
    def total_llm_calls(self) -> int:
        return self.control_llm_calls + self.data_llm_calls

    def to_dict(self) -> dict[str, Any]:
        return {
            "rounds": self.rounds,
            "actions": self.actions,
            "control_llm_calls": self.control_llm_calls,
            "data_llm_calls": self.data_llm_calls,
            "elapsed_seconds": self.elapsed_seconds,
            "cost_usd": self.cost_usd,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Usage":
        return cls(
            rounds=int(data.get("rounds", 0)),
            actions=int(data.get("actions", 0)),
            control_llm_calls=int(data.get("control_llm_calls", 0)),
            data_llm_calls=int(data.get("data_llm_calls", 0)),
            elapsed_seconds=float(data.get("elapsed_seconds", 0.0)),
            cost_usd=data.get("cost_usd"),
        )


def budget_exceeded(budget: Budget, usage: Usage) -> Optional[str]:
    """Erster ueberschrittener Deckel als maschinenlesbarer Grund (fuer
    BLOCKED/BUDGET_EXHAUSTED) - oder None. Reine Funktion, kein Zustand."""
    if usage.rounds >= budget.max_rounds:
        return "MAX_ROUNDS"
    if usage.actions >= budget.max_actions:
        return "MAX_ACTIONS"
    if usage.control_llm_calls >= budget.max_control_llm_calls:
        return "MAX_CONTROL_LLM_CALLS"
    if usage.data_llm_calls >= budget.max_data_llm_calls:
        return "MAX_DATA_LLM_CALLS"
    if usage.total_llm_calls >= budget.max_total_llm_calls:
        return "MAX_TOTAL_LLM_CALLS"
    if usage.elapsed_seconds >= budget.max_elapsed_seconds:
        return "MAX_ELAPSED_SECONDS"
    return None


# --- Definition of Done (Vertrag §4) -----------------------------------------

@dataclass
class DoDCriterion:
    description: str
    verifier_kind: str
    required: bool = True
    state: CriterionState = CriterionState.PENDING
    evidence_ids: list[str] = field(default_factory=list)
    failure_reason: str = ""
    criterion_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "description": self.description,
            "verifier_kind": self.verifier_kind,
            "required": self.required,
            "state": self.state.value,
            "evidence_ids": list(self.evidence_ids),
            "failure_reason": self.failure_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DoDCriterion":
        return cls(
            criterion_id=str(data.get("criterion_id") or new_id()),
            description=str(data.get("description", "")),
            verifier_kind=str(data.get("verifier_kind", "")),
            required=bool(data.get("required", True)),
            state=CriterionState(data.get("state", CriterionState.PENDING.value)),
            evidence_ids=list(data.get("evidence_ids", []) or []),
            failure_reason=str(data.get("failure_reason", "")),
        )


def unmet_required(criteria: "list[DoDCriterion]") -> "list[DoDCriterion]":
    """Alle erforderlichen Kriterien, die (noch) nicht PASSED sind."""
    return [c for c in criteria if c.required and c.state is not CriterionState.PASSED]


def dod_satisfied(criteria: "list[DoDCriterion]") -> bool:
    """Vertrag §4: kein Abschluss, solange ein erforderliches Kriterium nicht
    PASSED ist. Leere DoD gilt als NICHT erfuellt (ein Auftrag ohne pruefbare
    Kriterien darf nie COMPLETED werden - ehrlich statt formal gruen)."""
    if not any(c.required for c in criteria):
        return False
    return not unmet_required(criteria)


# --- Blocker & Ergebnis ------------------------------------------------------

@dataclass
class Blocker:
    """Strukturierter Blockiergrund (Vertrag §5: Budget/Policy/Store etc.
    blockieren mit Code, nie mit behauptetem Fehlschlag)."""
    code: str                        # z. B. BUDGET_EXHAUSTED, POLICY_VIOLATION
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Blocker":
        return cls(code=str(data.get("code", "")), detail=str(data.get("detail", "")))


@dataclass
class Outcome:
    summary: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "evidence_ids": list(self.evidence_ids),
            "limitations": list(self.limitations),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Outcome":
        return cls(
            summary=str(data.get("summary", "")),
            evidence_ids=list(data.get("evidence_ids", []) or []),
            limitations=list(data.get("limitations", []) or []),
        )


# --- Task (Vertrag §4) --------------------------------------------------------

@dataclass
class Task:
    title: str
    goal: str
    original_request: str = ""       # REDIGIERT (Secrets nie im Journal)
    definition_of_done: list[DoDCriterion] = field(default_factory=list)
    status: TaskStatus = TaskStatus.DRAFT
    policy_id: str = "read_only_v1"
    allowed_actions: list[str] = field(default_factory=list)  # vor READY eingefroren, sortiert
    budget: Budget = field(default_factory=Budget)
    usage: Usage = field(default_factory=Usage)
    blocker: Optional[Blocker] = None
    active_action_id: Optional[str] = None
    outcome: Optional[Outcome] = None
    source: str = ""                 # Ursprungskanal - KEINE Callbacks
    schema_version: int = SCHEMA_VERSION
    task_id: str = field(default_factory=new_id)
    parent_task_id: Optional[str] = None    # B.1: zwingend None (Policy prueft)
    revision: int = 0                # +1 je persistiertem Ereignis (B2)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    started_at: Optional[str] = None
    deadline_at: Optional[str] = None
    completed_at: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATES

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "revision": self.revision,
            "title": self.title,
            "goal": self.goal,
            "original_request": self.original_request,
            "definition_of_done": [c.to_dict() for c in self.definition_of_done],
            "status": self.status.value,
            "policy_id": self.policy_id,
            "allowed_actions": sorted(self.allowed_actions),
            "budget": self.budget.to_dict(),
            "usage": self.usage.to_dict(),
            "blocker": self.blocker.to_dict() if self.blocker else None,
            "active_action_id": self.active_action_id,
            "outcome": self.outcome.to_dict() if self.outcome else None,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "deadline_at": self.deadline_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        return cls(
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            task_id=str(data.get("task_id") or new_id()),
            parent_task_id=data.get("parent_task_id"),
            revision=int(data.get("revision", 0)),
            title=str(data.get("title", "")),
            goal=str(data.get("goal", "")),
            original_request=str(data.get("original_request", "")),
            definition_of_done=[
                DoDCriterion.from_dict(c) for c in data.get("definition_of_done", []) or []
            ],
            status=TaskStatus(data.get("status", TaskStatus.DRAFT.value)),
            policy_id=str(data.get("policy_id", "read_only_v1")),
            allowed_actions=sorted(data.get("allowed_actions", []) or []),
            budget=Budget.from_dict(data.get("budget", {}) or {}),
            usage=Usage.from_dict(data.get("usage", {}) or {}),
            blocker=Blocker.from_dict(data["blocker"]) if data.get("blocker") else None,
            active_action_id=data.get("active_action_id"),
            outcome=Outcome.from_dict(data["outcome"]) if data.get("outcome") else None,
            source=str(data.get("source", "")),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
            started_at=data.get("started_at"),
            deadline_at=data.get("deadline_at"),
            completed_at=data.get("completed_at"),
        )


# --- Action / Observation / Approval / ActionRecord (Vertrag §4) --------------

@dataclass
class Action:
    task_id: str
    round_index: int
    intent: str
    target: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)  # REDIGIERT
    domain: str = ""                 # CapabilitySpec.domain (Nachtrag 1)
    base_risk: int = 0
    dynamic_risk: int = 0
    side_effect: SideEffect = SideEffect.NONE
    idempotency_key: str = ""
    action_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def effective_risk(self) -> int:
        """Vertrag §6.2: max(Basisrisiko, dynamisches Risiko)."""
        return max(self.base_risk, self.dynamic_risk)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "task_id": self.task_id,
            "round_index": self.round_index,
            "intent": self.intent,
            "target": self.target,
            "arguments": dict(self.arguments),
            "domain": self.domain,
            "base_risk": self.base_risk,
            "dynamic_risk": self.dynamic_risk,
            "side_effect": self.side_effect.value,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        return cls(
            action_id=str(data.get("action_id") or new_id()),
            task_id=str(data.get("task_id", "")),
            round_index=int(data.get("round_index", 0)),
            intent=str(data.get("intent", "")),
            target=str(data.get("target", "")),
            arguments=dict(data.get("arguments", {}) or {}),
            domain=str(data.get("domain", "")),
            base_risk=int(data.get("base_risk", 0)),
            dynamic_risk=int(data.get("dynamic_risk", 0)),
            side_effect=SideEffect(data.get("side_effect", SideEffect.NONE.value)),
            idempotency_key=str(data.get("idempotency_key", "")),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


@dataclass
class Observation:
    task_id: str
    action_id: str
    source: str
    trust: TrustClass
    status: str = ""                 # z. B. ok / transient_error
    control_facts: dict[str, Any] = field(default_factory=dict)  # schema-validiert (B3)
    artifact_ref: str = ""
    artifact_hash: str = ""
    sensitivity: str = "normal"
    observation_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def planning_allowed(self) -> bool:
        """Vertrag §6.3: NUR SYSTEM/ADAPTER_VERIFIED beeinflussen Planung -
        abgeleitet aus der Vertrauensklasse, nie frei setzbar."""
        return self.trust in PLANNING_TRUSTED

    @property
    def verification_allowed(self) -> bool:
        return self.trust in PLANNING_TRUSTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "task_id": self.task_id,
            "action_id": self.action_id,
            "source": self.source,
            "trust": self.trust.value,
            "status": self.status,
            "control_facts": dict(self.control_facts),
            "artifact_ref": self.artifact_ref,
            "artifact_hash": self.artifact_hash,
            "planning_allowed": self.planning_allowed,
            "verification_allowed": self.verification_allowed,
            "sensitivity": self.sensitivity,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Observation":
        return cls(
            observation_id=str(data.get("observation_id") or new_id()),
            task_id=str(data.get("task_id", "")),
            action_id=str(data.get("action_id", "")),
            source=str(data.get("source", "")),
            trust=TrustClass(data.get("trust", TrustClass.EXTERNAL_UNTRUSTED.value)),
            status=str(data.get("status", "")),
            control_facts=dict(data.get("control_facts", {}) or {}),
            artifact_ref=str(data.get("artifact_ref", "")),
            artifact_hash=str(data.get("artifact_hash", "")),
            sensitivity=str(data.get("sensitivity", "normal")),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


@dataclass
class Approval:
    """In B.1 modelliert, aber nie erzeugt (nur Risiko 0 zugelassen).
    Ab S5: Bindung an task_id + action_id + approval_id (Vertrag §6.4)."""
    task_id: str
    action_id: str
    state: ApprovalState = ApprovalState.OPEN
    channel: str = ""
    expires_at: Optional[str] = None
    decision: str = ""
    approval_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "task_id": self.task_id,
            "action_id": self.action_id,
            "state": self.state.value,
            "channel": self.channel,
            "expires_at": self.expires_at,
            "decision": self.decision,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Approval":
        return cls(
            approval_id=str(data.get("approval_id") or new_id()),
            task_id=str(data.get("task_id", "")),
            action_id=str(data.get("action_id", "")),
            state=ApprovalState(data.get("state", ApprovalState.OPEN.value)),
            channel=str(data.get("channel", "")),
            expires_at=data.get("expires_at"),
            decision=str(data.get("decision", "")),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


@dataclass
class ActionRecord:
    """Unveraenderlicher Ausfuehrungs-Nachweis eines Aktionsversuchs."""
    action_id: str
    task_id: str
    state: ActionState = ActionState.PROPOSED
    attempt: int = 1
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    observation_ids: list[str] = field(default_factory=list)
    error_code: str = ""
    retryable: bool = False
    effect: EffectState = EffectState.NONE
    record_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "action_id": self.action_id,
            "task_id": self.task_id,
            "state": self.state.value,
            "attempt": self.attempt,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "observation_ids": list(self.observation_ids),
            "error_code": self.error_code,
            "retryable": self.retryable,
            "effect": self.effect.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionRecord":
        return cls(
            record_id=str(data.get("record_id") or new_id()),
            action_id=str(data.get("action_id", "")),
            task_id=str(data.get("task_id", "")),
            state=ActionState(data.get("state", ActionState.PROPOSED.value)),
            attempt=int(data.get("attempt", 1)),
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
            observation_ids=list(data.get("observation_ids", []) or []),
            error_code=str(data.get("error_code", "")),
            retryable=bool(data.get("retryable", False)),
            effect=EffectState(data.get("effect", EffectState.NONE.value)),
        )
