"""
TaskRunner - die Zustandsmaschine in Aktion (Phase B.1, Bauschritt B4).

Verbindliche Quelle: Bauvertrag v1.0 §8. Je Runde exakt: Task laden ->
Abbruch/Deadline/Budget pruefen -> PlannerView (nur Kontrollfakten) ->
typisierte Entscheidung -> deterministisch validieren -> ACTION_PROPOSED +
ACTION_STARTED persistieren -> genau EINE Capability -> Ergebnis trennen
(ObservationReducer) -> Observation/ActionRecord persistieren -> DoD ->
weiter, blockieren oder VERIFYING.

Harte Regeln aus §5, hier durchgesetzt: COMPLETED nur ueber VERIFYING;
Budget-Erschoepfung ist BLOCKED/BUDGET_EXHAUSTED, kein Fehlschlag; ohne
strukturierten Entscheider BLOCKED/PLANNER_UNAVAILABLE; das Modell setzt
nie Zustaende. REQUEST_INPUT blockiert in B.1 mit INPUT_REQUIRED (der
Approval-Fluss kommt erst mit S5).

Capability-Timeouts liegen bewusst IN den Capabilities (z. B. subprocess-
Timeout je git-Aufruf); der Runner deckelt zusaetzlich die Gesamtzeit
(budget.max_elapsed_seconds) und prueft das Cancel-Event vor jeder Runde
und nach jeder Aktion.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from core.capability_registry import (
    CapabilityRegistry,
    CapabilityResult,
    FactSchemaViolation,
    reduce_observation,
)
from core.task_models import (
    Action,
    ActionRecord,
    ActionState,
    Blocker,
    Observation,
    Outcome,
    PlannerDecision,
    PlannerDecisionKind,
    Task,
    TaskStatus,
    budget_exceeded,
    dod_satisfied,
    new_id,
    unmet_required,
    utc_now_iso,
)
from core.task_planner import (
    PlannerUnavailable,
    TaskDecisionProvider,
    build_planner_view,
)
from core.task_policy import PolicyViolation, validate_action
from memory.task_store import TaskStore

logger = logging.getLogger("jarvis.task_runner")

# Verifier: (criterion, task, observations, store) -> None (setzt state/
# evidence_ids/failure_reason am Kriterium). Registriert je verifier_kind.
Verifier = Callable[..., None]
# Berichtsgenerierung (Data Plane, handlungsunfaehig):
# (task, observations, store) -> (Outcome, anzahl_data_llm_calls)
ReportFn = Callable[[Task, list[Observation], TaskStore], tuple[Outcome, int]]

EventListener = Callable[[str, Task], None]


class TaskRunner:
    def __init__(self, store: TaskStore, registry: CapabilityRegistry,
                 decision_provider: Optional[TaskDecisionProvider],
                 report_fn: Optional[ReportFn] = None,
                 verifiers: Optional[dict[str, Verifier]] = None,
                 emit: Optional[EventListener] = None):
        self.store = store
        self.registry = registry
        self.decision_provider = decision_provider
        self.report_fn = report_fn
        self.verifiers = dict(verifiers or {})
        self._emit = emit or (lambda kind, task: None)

    # --- Hauptschleife ---------------------------------------------------------

    def run(self, task_id: str, cancel_event: threading.Event) -> Task:
        task = self.store.load(task_id)
        if task.status is TaskStatus.READY:
            task.status = TaskStatus.RUNNING
            task.started_at = task.started_at or utc_now_iso()
            task = self.store.commit(task, "run_started", task.revision, actor="runner")
        # Crash WAEHREND der Pruefung (Hardening 15.07., Sol-Analyse Punkt 1):
        # ein in VERIFYING liegengebliebener Auftrag wird erneut geprueft -
        # die Verifier sind deterministisch, doppelt pruefen ist gefahrlos.
        if task.status is TaskStatus.VERIFYING:
            task = self._verify(task)
        started = time.monotonic()

        while task.status is TaskStatus.RUNNING:
            task.usage.elapsed_seconds += max(0.0, time.monotonic() - started)
            started = time.monotonic()
            if cancel_event.is_set():
                return self._cancel(task)
            if self._deadline_passed(task):
                return self._block(task, "DEADLINE_EXCEEDED", task.deadline_at or "")
            cap = budget_exceeded(task.budget, task.usage)
            if cap:
                return self._block(task, "BUDGET_EXHAUSTED", cap)

            decision = self._decide(task)
            if isinstance(decision, Task):          # bereits blockiert
                return decision
            task = self._apply_decision(task, decision, cancel_event)
        return task

    # --- Entscheidung ------------------------------------------------------------

    def _decide(self, task: Task):
        if self.decision_provider is None:
            return self._block(task, "PLANNER_UNAVAILABLE", "Kein Entscheidungs-Provider verdrahtet.")
        observations = self.store.load_observations(task.task_id)
        view = build_planner_view(task, observations, self.registry)
        try:
            decision = self.decision_provider.decide(view)
        except PlannerUnavailable as err:
            return self._block(task, "PLANNER_UNAVAILABLE", str(err))
        except Exception:  # noqa: BLE001 - Provider-Fehler blockiert, nie Absturz
            logger.exception("TaskRunner: Entscheidungs-Provider warf.")
            return self._block(task, "PLANNER_UNAVAILABLE", "Provider-Fehler (siehe Log).")
        task.usage.control_llm_calls += 1
        if decision is None:
            return self._block(task, "PLANNER_INVALID", "Keine typisierte Entscheidung geliefert.")
        return decision

    def _apply_decision(self, task: Task, decision: PlannerDecision,
                        cancel_event: threading.Event) -> Task:
        kind = decision.kind
        if kind is PlannerDecisionKind.RUN_ACTION:
            return self._run_action(task, decision, cancel_event)
        if kind is PlannerDecisionKind.REQUEST_INPUT:
            task.status = TaskStatus.BLOCKED
            task.blocker = Blocker(code="INPUT_REQUIRED", detail=decision.question)
            task = self.store.commit(task, "waiting_for_input", task.revision, actor="runner")
            self._emit("waiting_for_input", task)
            return task
        if kind is PlannerDecisionKind.BEGIN_VERIFICATION:
            return self._verify(task)
        if kind is PlannerDecisionKind.BLOCK:
            return self._block(task, "PLANNER_BLOCKED", decision.reason)
        if kind is PlannerDecisionKind.FAIL:
            task.status = TaskStatus.FAILED
            task.blocker = Blocker(code="PLANNER_FAILED", detail=decision.reason)
            task = self.store.commit(task, "failed", task.revision, actor="runner")
            self._emit("failed", task)
            return task
        return self._block(task, "PLANNER_INVALID", f"Unbekannte Entscheidung {kind!r}.")

    # --- Aktion -------------------------------------------------------------------

    def _run_action(self, task: Task, decision: PlannerDecision,
                    cancel_event: threading.Event) -> Task:
        round_index = task.usage.rounds + 1
        action = Action(
            task_id=task.task_id, round_index=round_index,
            intent=decision.intent, arguments=dict(decision.arguments),
            idempotency_key=f"{task.task_id}:{round_index}:{decision.intent}",
        )
        try:
            spec = validate_action(task, action, self.registry)
        except PolicyViolation as err:
            return self._block(task, err.code, err.detail)
        action.domain = spec.domain

        # ACTION_PROPOSED + ACTION_STARTED sind persistiert, BEVOR etwas laeuft.
        self.store.record_action(action)
        task.usage.rounds = round_index
        task.usage.actions += 1
        task.active_action_id = action.action_id
        task = self.store.commit(task, "action_started", task.revision, actor="runner")
        self._emit("round_started", task)
        record = ActionRecord(action_id=action.action_id, task_id=task.task_id,
                              state=ActionState.STARTED, started_at=utc_now_iso())
        self.store.record_action_record(record)
        self._emit("action_started", task)

        result = self._execute(spec, action, cancel_event)
        try:
            observation = reduce_observation(spec, action, result, self.store, task.task_id)
        except FactSchemaViolation as err:
            record.state = ActionState.FAILED
            record.ended_at = utc_now_iso()
            record.error_code = "FACT_SCHEMA_VIOLATION"
            self.store.record_action_record(record)
            return self._block(task, "FACT_SCHEMA_VIOLATION", str(err))
        self.store.record_observation(observation)

        record.state = (ActionState.SUCCEEDED if result.status == "ok" else ActionState.FAILED)
        record.ended_at = utc_now_iso()
        record.observation_ids = [observation.observation_id]
        record.error_code = result.error_code
        record.retryable = result.retryable
        self.store.record_action_record(record)

        task.active_action_id = None
        task = self.store.commit(task, "action_completed", task.revision, actor="runner")
        self._emit("action_completed", task)
        if cancel_event.is_set():
            return self._cancel(task)
        return task

    def _execute(self, spec, action: Action, cancel_event: threading.Event) -> CapabilityResult:
        try:
            return spec.executor(action, {"cancel_event": cancel_event})
        except Exception as err:  # noqa: BLE001 - Adapterfehler = Fehl-Observation
            logger.exception("Capability %s warf.", spec.intent)
            return CapabilityResult(status="error", error_code=type(err).__name__,
                                    raw_text=str(err))

    # --- Verifikation ----------------------------------------------------------------

    def _verify(self, task: Task) -> Task:
        task.status = TaskStatus.VERIFYING
        task = self.store.commit(task, "verification_started", task.revision, actor="runner")
        self._emit("verifying", task)

        observations = self.store.load_observations(task.task_id)
        if self.report_fn is not None and task.outcome is None:
            try:
                outcome, data_calls = self.report_fn(task, observations, self.store)
                task.outcome = outcome
                task.usage.data_llm_calls += int(data_calls)
            except Exception:  # noqa: BLE001 - Bericht scheitert -> blockieren, nie raten
                logger.exception("Berichtsgenerierung fehlgeschlagen.")
                return self._block(task, "REPORT_FAILED", "Berichtsgenerierung fehlgeschlagen (siehe Log).")

        for criterion in task.definition_of_done:
            verifier = self.verifiers.get(criterion.verifier_kind)
            if verifier is None:
                criterion.state = criterion.state  # bleibt PENDING/UNKNOWN
                continue
            try:
                verifier(criterion, task, observations, self.store)
            except Exception:  # noqa: BLE001 - Verifier-Fehler = Kriterium UNKNOWN
                logger.exception("Verifier %s warf.", criterion.verifier_kind)
                criterion.failure_reason = "VERIFIER_ERROR"

        if dod_satisfied(task.definition_of_done):
            task.status = TaskStatus.COMPLETED
            task.completed_at = utc_now_iso()
            task.blocker = None
            task = self.store.commit(task, "completed", task.revision, actor="runner")
            self._emit("completed", task)
            return task

        unmet = [c.description[:80] for c in unmet_required(task.definition_of_done)]
        if budget_exceeded(task.budget, task.usage):
            return self._block(task, "DOD_UNMET", f"Offen: {unmet}")
        # Budget uebrig: zurueck in die Arbeit (VERIFYING -> RUNNING erlaubt).
        task.status = TaskStatus.RUNNING
        task = self.store.commit(task, "verification_incomplete", task.revision, actor="runner")
        return task

    # --- Zustands-Helfer -----------------------------------------------------------

    def _block(self, task: Task, code: str, detail: str) -> Task:
        task.status = TaskStatus.BLOCKED
        task.blocker = Blocker(code=code, detail=str(detail)[:500])
        task = self.store.commit(task, "blocked", task.revision, actor="runner")
        self._emit("blocked", task)
        return task

    def _cancel(self, task: Task) -> Task:
        task.status = TaskStatus.CANCELLED
        task = self.store.commit(task, "cancelled", task.revision, actor="runner")
        self._emit("cancelled", task)
        return task

    def _deadline_passed(self, task: Task) -> bool:
        if not task.deadline_at:
            return False
        try:
            deadline = datetime.fromisoformat(task.deadline_at)
        except ValueError:
            return False
        now = datetime.now(deadline.tzinfo or timezone.utc)
        return now > deadline

    # --- Wiederanlauf (Vertrag §7) ---------------------------------------------------

    def resume(self, task_id: str) -> Optional[Task]:
        """Wendet die Wiederanlauf-Regeln an und liefert den Task, wenn er
        wieder LAUFFAEHIG ist (der Service reiht ihn dann ein) - sonst None."""
        task = self.store.load(task_id)
        if task.is_terminal:
            return None
        if task.status is TaskStatus.WAITING_APPROVAL:
            # B.1 erzeugt nie Approvals; abgelaufene blockieren ehrlich.
            task.status = TaskStatus.BLOCKED
            task.blocker = Blocker(code="APPROVAL_EXPIRED", detail="Neustart waehrend offener Freigabe.")
            self.store.commit(task, "blocked", task.revision, actor="resume")
            return None
        if task.status is TaskStatus.RUNNING and task.active_action_id:
            # Read-only-Aktion in STARTED ohne Abschluss: PROCESS_INTERRUPTED
            # protokollieren; ein neuer Versuch ist eine NEUE Aktion im Budget.
            record = ActionRecord(action_id=task.active_action_id, task_id=task.task_id,
                                  state=ActionState.OUTCOME_UNKNOWN, attempt=1,
                                  ended_at=utc_now_iso(), error_code="PROCESS_INTERRUPTED",
                                  retryable=True, record_id=new_id())
            self.store.record_action_record(record)
            task.active_action_id = None
            task = self.store.commit(task, "process_interrupted", task.revision, actor="resume")
        if task.status in (TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.VERIFYING):
            # VERIFYING (Hardening 15.07.): run() prueft erneut - deterministisch.
            return task
        return None
