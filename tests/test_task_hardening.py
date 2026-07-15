"""Hardening-Runde 15.07. (Sol-Analyse nach B8): Blocked-/VERIFYING-Recovery,
Cancel/Resume liegengebliebener Auftraege, letztes Ergebnis abfragbar,
Argument-Validierung, Store-Redaction, Transition-Enforcement im Store."""
from __future__ import annotations

import json
import threading

import pytest
from core.capability_registry import CapabilityRegistry, CapabilityResult, CapabilitySpec
from core.execution_lease import ExecutionLease
from core.task_models import (
    Action,
    CriterionState,
    DoDCriterion,
    IllegalTransition,
    PlannerDecision,
    PlannerDecisionKind,
    Task,
    TaskStatus,
    TrustClass,
)
from core.task_planner import build_planner_view
from core.task_policy import PolicyViolation, freeze_contract, validate_action
from core.task_runner import TaskRunner
from core.task_service import TaskService
from memory.task_store import TaskStore


def _spec(**kw):
    return CapabilitySpec(
        intent=kw.pop("intent", "sammeln"), domain=kw.pop("domain", "bauen"),
        description="Fake", executor=kw.pop(
            "executor", lambda a, c: CapabilityResult(status="ok", control_facts={"treffer": 1})),
        fact_schema={"treffer": int},
        argument_schema=kw.pop("argument_schema",
                               {"root": {"type": "string"}, "tiefe": {"type": "integer"}}),
        **kw)


def _task(**kw):
    return Task(title=kw.pop("title", "T"), goal="G",
                definition_of_done=kw.pop("dod", [DoDCriterion(description="d", verifier_kind="fake")]),
                allowed_actions=["sammeln"], **kw)


def _pass(criterion, task, observations, store):
    criterion.state = CriterionState.PASSED


RUN = PlannerDecision(kind=PlannerDecisionKind.RUN_ACTION, intent="sammeln")
VERIFY = PlannerDecision(kind=PlannerDecisionKind.BEGIN_VERIFICATION)


class Scripted:
    def __init__(self, decisions):
        self.d = list(decisions)
        self.views = []

    def decide(self, view):
        self.views.append(view)
        return self.d.pop(0) if self.d else None


def _stack(tmp_path, decisions, verifier=_pass):
    store = TaskStore(tmp_path)
    registry = CapabilityRegistry()
    registry.register(_spec())
    runner = TaskRunner(store, registry, Scripted(decisions), verifiers={"fake": verifier})
    return store, registry, runner


# --- Punkt 4: Enforcement ------------------------------------------------------

def test_store_enforces_state_machine_on_commit(tmp_path):
    """RUNNING -> COMPLETED wird vom STORE abgelehnt, nicht nur vom Test."""
    store = TaskStore(tmp_path)
    task = store.create(_task())
    task.status = TaskStatus.READY
    store.commit(task, "contract_frozen", task.revision)
    task.status = TaskStatus.RUNNING
    store.commit(task, "run_started", task.revision)

    task.status = TaskStatus.COMPLETED
    with pytest.raises(IllegalTransition):
        store.commit(task, "completed", task.revision)
    # Nichts journalisiert: die Spitze steht weiter auf RUNNING.
    task_fresh = TaskStore(tmp_path).load(task.task_id)
    assert task_fresh.status is TaskStatus.RUNNING


def test_store_redacts_every_persisted_field(tmp_path):
    """Der Store redigiert GRUNDSAETZLICH - auch Felder, die kein Zulieferer
    vorher redigiert hat (goal/Argumente/Fakten)."""
    secret = 'api_key = "sk-1234567890abcdef1234"'  # release-scan: ok (erfundenes Beispiel-Secret)
    store = TaskStore(tmp_path)
    task = store.create(_task(title=f"T {secret}"))
    store.record_action(Action(task_id=task.task_id, round_index=1, intent="sammeln",
                               arguments={"root": secret}))

    dumped = "".join(p.read_text(encoding="utf-8")
                     for p in (tmp_path / "tasks" / task.task_id).rglob("*.json"))
    assert "sk-1234567890abcdef1234" not in dumped  # release-scan: ok (erfundenes Beispiel-Secret)


def test_unknown_or_wrong_typed_arguments_are_rejected_before_dispatch(tmp_path):
    registry = CapabilityRegistry()
    registry.register(_spec())
    task = freeze_contract(_task(), registry)

    with pytest.raises(PolicyViolation, match="unbekanntes Argument"):
        validate_action(task, Action(task_id=task.task_id, round_index=1, intent="sammeln",
                                     arguments={"shell": "rm -rf"}), registry)
    with pytest.raises(PolicyViolation, match="erwartet integer"):
        validate_action(task, Action(task_id=task.task_id, round_index=1, intent="sammeln",
                                     arguments={"tiefe": "drei"}), registry)
    ok = Action(task_id=task.task_id, round_index=1, intent="sammeln",
                arguments={"root": "C:\\KI", "tiefe": 1})
    validate_action(task, ok, registry)
    assert ok.arguments == {"root": "C:\\KI", "tiefe": 1}


# --- Punkt 1: Recovery/Cancel/Resume --------------------------------------------

def test_verifying_crash_is_resumed_and_completes(tmp_path):
    """Crash in VERIFYING: resume() reiht wieder ein, run() prueft erneut."""
    store, registry, runner = _stack(tmp_path, [])
    task = freeze_contract(_task(), registry)
    store.create(task)
    task.status = TaskStatus.READY
    store.commit(task, "contract_frozen", task.revision)
    task.status = TaskStatus.RUNNING
    store.commit(task, "run_started", task.revision)
    task.status = TaskStatus.VERIFYING
    store.commit(task, "verification_started", task.revision)   # 'Crash' hier

    resumed = runner.resume(task.task_id)
    assert resumed is not None
    done = runner.run(task.task_id, threading.Event())
    assert done.status is TaskStatus.COMPLETED


def test_stranded_blocked_task_can_be_cancelled_and_unblocks_new_submits(tmp_path):
    """Sol-Analyse Punkt 1: ein BLOCKED-Auftrag ohne Worker war unabbrechbar
    und blockierte jeden neuen Auftrag."""
    store, registry, runner = _stack(tmp_path, [])
    service = TaskService(store, runner, ExecutionLease())
    task = freeze_contract(_task(), registry)
    store.create(task)
    task.status = TaskStatus.READY
    store.commit(task, "contract_frozen", task.revision)
    task.status = TaskStatus.RUNNING
    store.commit(task, "run_started", task.revision)
    task.status = TaskStatus.BLOCKED
    store.commit(task, "blocked", task.revision)                # liegengeblieben

    cancelled = service.cancel()

    assert cancelled == task.task_id
    assert store.load(task.task_id).status is TaskStatus.CANCELLED
    second = service.submit(_task(title="Zweiter"))             # nicht mehr blockiert
    assert second.status is TaskStatus.READY


def test_blocked_task_resumes_with_user_answer_in_planner_view(tmp_path):
    """Fortsetzung + Rueckfrage (§9-Kanalparitaet): die Antwort erreicht den
    Entscheider als markierte, gedeckelte USER-Antwort - nie als Kontrollfakt."""
    ask = PlannerDecision(kind=PlannerDecisionKind.REQUEST_INPUT, question="Welcher Root?")
    store, registry, runner = _stack(tmp_path, [ask, RUN, VERIFY])
    service = TaskService(store, runner, ExecutionLease())
    task = freeze_contract(_task(), registry)
    store.create(task)
    task.status = TaskStatus.READY
    store.commit(task, "contract_frozen", task.revision)
    blocked = runner.run(task.task_id, threading.Event())
    assert blocked.status is TaskStatus.BLOCKED
    assert blocked.blocker.code == "INPUT_REQUIRED"

    resumed_id = service.resume_task("nimm C:\\KI")
    assert resumed_id == task.task_id
    done = runner.run(task.task_id, threading.Event())

    assert done.status is TaskStatus.COMPLETED
    planner = runner.decision_provider
    answered_views = [v for v in planner.views if v.get("user_answers")]
    assert answered_views
    assert answered_views[0]["user_answers"][0]["answer"] == "nimm C:\\KI"
    view_obs = json.dumps([v.get("observations") for v in planner.views])
    assert "nimm C:" not in view_obs        # nie als planungsberechtigter Fakt getarnt


def test_resume_without_blocked_task_is_honest(tmp_path):
    store, registry, runner = _stack(tmp_path, [])
    service = TaskService(store, runner, ExecutionLease())
    assert service.resume_task("egal") is None


# --- Punkt 2: letztes Ergebnis abfragbar -------------------------------------------

def test_status_line_shows_last_finished_task_with_outcome(tmp_path):
    from core.task_models import Outcome

    store, registry, runner = _stack(tmp_path, [])
    service = TaskService(store, runner, ExecutionLease())
    task = freeze_contract(_task(title="Portfolio-Review"), registry)
    store.create(task)
    task.status = TaskStatus.READY
    store.commit(task, "contract_frozen", task.revision)
    task.status = TaskStatus.RUNNING
    store.commit(task, "run_started", task.revision)
    task.status = TaskStatus.VERIFYING
    store.commit(task, "verification_started", task.revision)
    task.status = TaskStatus.COMPLETED
    task.outcome = Outcome(summary="Priorität: jarvis — weiterbauen.")
    store.commit(task, "completed", task.revision)

    line = service.status_line()

    assert "Zuletzt:" in line and "Portfolio-Review" in line and "COMPLETED" in line
    assert "Priorität: jarvis" in line


def test_outbox_keeps_long_summaries_and_cuts_only_at_line_breaks(tmp_path):
    """Live-Reibung 15.07.: der 600-Zeichen-Deckel riss den 9-Projekte-
    Bericht mitten im Wort ab. Jetzt: grosszuegiger Deckel, Kuerzung nur an
    Zeilengrenze, mit ehrlichem Kuerzungs-Hinweis."""
    from core.fileio import read_json
    from core.task_models import Outcome

    store, registry, runner = _stack(tmp_path, [])
    service = TaskService(store, runner, ExecutionLease())
    task = freeze_contract(_task(title="Portfolio-Review"), registry)
    store.create(task)
    task.status = TaskStatus.READY
    store.commit(task, "contract_frozen", task.revision)
    task.status = TaskStatus.RUNNING
    store.commit(task, "run_started", task.revision)
    task.status = TaskStatus.VERIFYING
    store.commit(task, "verification_started", task.revision)
    lines = [f"• projekt-{i}: Ein vollstaendiger Satz zum Stand des Projekts Nummer {i}."
             for i in range(30)]
    task.outcome = Outcome(summary="\n".join(lines))
    task.status = TaskStatus.COMPLETED
    store.commit(task, "completed", task.revision)
    service._outbox_add("completed", task)

    entry = read_json(tmp_path / "tasks" / "outbox.json", [])[-1]
    message = entry["message"]
    assert "projekt-8" in message                      # weit ueber den alten 600
    for line in message.splitlines():
        assert not line.endswith(("Der A", "Numm", "Proj"))
    if "gekürzt" in message:
        assert message.rstrip().endswith("zeigt den Stand)")


def test_planner_view_budget_shows_remaining(tmp_path):
    """Sichtprobe: die PlannerView traegt user_answers-Feld immer (leer ok)."""
    store, registry, runner = _stack(tmp_path, [])
    task = freeze_contract(_task(), registry)
    view = build_planner_view(task, [], registry)
    assert view["user_answers"] == []
    assert view["budget_remaining"]["rounds"] == 3
    # und USER-Trust bleibt von den planungsberechtigten Fakten getrennt:
    from core.task_models import Observation
    obs = Observation(task_id="t", action_id="", source="user_input",
                      trust=TrustClass.USER, control_facts={"answer": "x", "question": "q"})
    view2 = build_planner_view(task, [obs], registry)
    assert view2["observations"] == [] and view2["user_answers"] == [{"question": "q", "answer": "x"}]
