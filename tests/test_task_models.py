"""Tests fuer core/task_models.py (Phase B.1, Bauschritt B1) - Zustandsmaschine
und pure Datentypen nach dem Bauvertrag (ADR-074 /
docs/proposals/phase-b-bauvertrag-2026-07-14.md §4/§5, Testmatrix 'Zustaende')."""
from __future__ import annotations

import pytest
from core.task_models import (
    ALLOWED_TRANSITIONS,
    PLANNING_TRUSTED,
    TERMINAL_STATES,
    Action,
    Blocker,
    Budget,
    DoDCriterion,
    CriterionState,
    IllegalTransition,
    Observation,
    Outcome,
    SideEffect,
    Task,
    TaskStatus,
    TrustClass,
    Usage,
    budget_exceeded,
    can_transition,
    dod_satisfied,
    unmet_required,
    validate_transition,
)


# --- Zustandsmaschine (Vertrag §5) -------------------------------------------

def test_every_allowed_transition_validates():
    for source, targets in ALLOWED_TRANSITIONS.items():
        for target in targets:
            validate_transition(source, target)   # darf nicht werfen
            assert can_transition(source, target)


def test_running_to_completed_is_forbidden():
    """Harte Regel: der Weg zu COMPLETED fuehrt IMMER ueber VERIFYING."""
    with pytest.raises(IllegalTransition):
        validate_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED)
    assert TaskStatus.COMPLETED in ALLOWED_TRANSITIONS[TaskStatus.VERIFYING]


def test_terminal_states_reject_any_transition():
    for terminal in TERMINAL_STATES:
        assert ALLOWED_TRANSITIONS[terminal] == frozenset()
        for target in TaskStatus:
            with pytest.raises(IllegalTransition, match="terminal"):
                validate_transition(terminal, target)


def test_forbidden_transition_names_allowed_targets():
    """Die Fehlermeldung nennt die erlaubten Ziele - Diagnose statt Raetsel."""
    with pytest.raises(IllegalTransition, match="VERIFYING"):
        validate_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED)
    with pytest.raises(IllegalTransition):
        validate_transition(TaskStatus.DRAFT, TaskStatus.RUNNING)  # erst READY


def test_state_machine_matches_contract_table():
    """Die Tabelle aus Vertrag §5 - wortwoertlich, als Drift-Wächter."""
    expect = {
        TaskStatus.DRAFT: {TaskStatus.READY, TaskStatus.CANCELLED},
        TaskStatus.READY: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
        TaskStatus.RUNNING: {TaskStatus.WAITING_APPROVAL, TaskStatus.BLOCKED,
                             TaskStatus.VERIFYING, TaskStatus.FAILED,
                             TaskStatus.CANCELLED},
        TaskStatus.WAITING_APPROVAL: {TaskStatus.RUNNING, TaskStatus.BLOCKED,
                                      TaskStatus.CANCELLED},
        TaskStatus.BLOCKED: {TaskStatus.RUNNING, TaskStatus.FAILED,
                             TaskStatus.CANCELLED},
        TaskStatus.VERIFYING: {TaskStatus.COMPLETED, TaskStatus.RUNNING,
                               TaskStatus.BLOCKED, TaskStatus.FAILED,
                               TaskStatus.CANCELLED},
        TaskStatus.COMPLETED: set(),
        TaskStatus.FAILED: set(),
        TaskStatus.CANCELLED: set(),
    }
    assert {s: set(t) for s, t in ALLOWED_TRANSITIONS.items()} == expect


# --- Budget (Vertrag §4, Nachtrag 2) -----------------------------------------

def test_default_budget_matches_contract():
    b = Budget()
    assert (b.max_rounds, b.max_actions) == (3, 3)
    assert (b.max_control_llm_calls, b.max_data_llm_calls, b.max_total_llm_calls) == (6, 12, 18)
    assert b.max_elapsed_seconds == 600.0


def test_budget_exceeded_names_first_exhausted_cap():
    b = Budget()
    assert budget_exceeded(b, Usage()) is None
    assert budget_exceeded(b, Usage(rounds=3)) == "MAX_ROUNDS"
    assert budget_exceeded(b, Usage(actions=3)) == "MAX_ACTIONS"
    assert budget_exceeded(b, Usage(control_llm_calls=6)) == "MAX_CONTROL_LLM_CALLS"
    assert budget_exceeded(b, Usage(data_llm_calls=12)) == "MAX_DATA_LLM_CALLS"
    # Getrennte Konten: 5 control + 13 data reisst NICHT total (18), aber data (12).
    assert budget_exceeded(b, Usage(control_llm_calls=5, data_llm_calls=13)) == "MAX_DATA_LLM_CALLS"
    assert budget_exceeded(b, Usage(elapsed_seconds=600.0)) == "MAX_ELAPSED_SECONDS"
    assert Usage(control_llm_calls=2, data_llm_calls=3).total_llm_calls == 5


# --- Definition of Done (Vertrag §4) -----------------------------------------

def test_dod_requires_all_required_passed():
    must = DoDCriterion(description="alles klassifiziert", verifier_kind="portfolio")
    nice = DoDCriterion(description="optional", verifier_kind="x", required=False)
    assert dod_satisfied([must, nice]) is False          # PENDING blockiert
    assert unmet_required([must, nice]) == [must]

    must.state = CriterionState.PASSED
    assert dod_satisfied([must, nice]) is True           # optional darf offen sein

    must.state = CriterionState.FAILED
    assert dod_satisfied([must, nice]) is False


def test_dod_empty_or_optional_only_is_never_satisfied():
    """Ehrlich statt formal gruen: ohne pruefbares Pflicht-Kriterium gibt es
    kein COMPLETED."""
    assert dod_satisfied([]) is False
    only_optional = [DoDCriterion(description="nett", verifier_kind="x", required=False)]
    assert dod_satisfied(only_optional) is False


# --- Vertrauensklassen (Vertrag §6.3) ----------------------------------------

def test_planning_allowed_derives_from_trust_only():
    base = dict(task_id="t", action_id="a", source="portfolio_reader")
    assert Observation(trust=TrustClass.SYSTEM, **base).planning_allowed
    assert Observation(trust=TrustClass.ADAPTER_VERIFIED, **base).planning_allowed
    for untrusted in (TrustClass.USER, TrustClass.EXTERNAL_UNTRUSTED, TrustClass.MODEL_DERIVED):
        obs = Observation(trust=untrusted, **base)
        assert not obs.planning_allowed
        assert not obs.verification_allowed
    assert PLANNING_TRUSTED == {TrustClass.SYSTEM, TrustClass.ADAPTER_VERIFIED}


def test_effective_risk_is_max_of_base_and_dynamic():
    a = Action(task_id="t", round_index=1, intent="collect_portfolio_evidence",
               base_risk=0, dynamic_risk=2)
    assert a.effective_risk == 2                          # dynamisch gewinnt
    a2 = Action(task_id="t", round_index=1, intent="x", base_risk=1, dynamic_risk=0)
    assert a2.effective_risk == 1                         # Basis gewinnt


# --- Serialisierung (Grundlage fuer B2) ---------------------------------------

def test_task_roundtrip_preserves_everything():
    task = Task(
        title="Portfolio-Review",
        goal="Alle aktiven Projekte unter C:\\KI analysieren",
        original_request="Analysiere alle aktiven Projekte …",
        definition_of_done=[DoDCriterion(description="klassifiziert", verifier_kind="portfolio")],
        allowed_actions=["collect_portfolio_evidence"],
        blocker=Blocker(code="BUDGET_EXHAUSTED", detail="MAX_ROUNDS"),
        outcome=Outcome(summary="…", evidence_ids=["e1"], limitations=["ohne jkc"]),
        source="telegram",
    )
    task.status = TaskStatus.BLOCKED
    task.revision = 7

    again = Task.from_dict(task.to_dict())

    assert again.to_dict() == task.to_dict()
    assert again.task_id == task.task_id
    assert again.parent_task_id is None
    assert again.status is TaskStatus.BLOCKED
    assert again.blocker.code == "BUDGET_EXHAUSTED"
    assert again.definition_of_done[0].state is CriterionState.PENDING
    assert again.budget.max_total_llm_calls == 18
    assert again.is_terminal is False


def test_task_to_dict_sorts_allowed_actions():
    """Vertrag §4: die Allowlist ist SORTIERT eingefroren (deterministisch)."""
    task = Task(title="t", goal="g", allowed_actions=["zebra", "alpha"])
    assert task.to_dict()["allowed_actions"] == ["alpha", "zebra"]


def test_action_and_observation_roundtrip():
    action = Action(task_id="t1", round_index=2, intent="collect_portfolio_evidence",
                    arguments={"root": "C:\\KI"}, domain="bauen",
                    side_effect=SideEffect.NONE, idempotency_key="k1")
    assert Action.from_dict(action.to_dict()).to_dict() == action.to_dict()

    obs = Observation(task_id="t1", action_id=action.action_id,
                      source="portfolio_reader", trust=TrustClass.ADAPTER_VERIFIED,
                      status="ok", control_facts={"projects_found": 9},
                      artifact_ref="art-1", artifact_hash="abc")
    data = obs.to_dict()
    assert data["planning_allowed"] is True               # abgeleitet, nicht gesetzt
    assert Observation.from_dict(data).to_dict() == data
