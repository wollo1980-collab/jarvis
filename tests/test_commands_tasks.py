"""Tests fuer commands/tasks.py (B7) + Runtime-Verdrahtung des TaskService
(B6): Kanal-Tuer, ehrliche Nicht-Konfiguration, geteilte ExecutionLease
(Regressionstest Nachtrag 4: nie zwei Ausfuehrungspfade)."""
from __future__ import annotations

import time
from pathlib import Path

import commands.tasks as tasks
from core.config import Config
from core.models import Plan, Status
from core.task_models import TaskStatus
from core.task_service import TaskSubmitError


class FakeService:
    def __init__(self, fail_code: str = ""):
        self.submitted = []
        self.cancelled = 0
        self.fail_code = fail_code

    def submit(self, task):
        if self.fail_code:
            raise TaskSubmitError(self.fail_code, "läuft bereits: Auftrag abc12345")
        self.submitted.append(task)
        return task

    def status_line(self):
        return "Auftrag abc12345 «Portfolio-Review»: RUNNING, Runde 1/3"

    def cancel(self):
        self.cancelled += 1
        return "abc12345deadbeef"


def test_configure_puts_real_root_path_into_description():
    """Live-Reibung 15.07.: «Analysiere C:KI» landete im Ereignisprotokoll -
    der konfigurierte Pfad steht jetzt WOERTLICH in der Beschreibung (Router
    und Kern waehlen nach genau diesen Beispielen)."""
    tasks.configure(lambda: None, "C:\\KI")
    desc = tasks.PortfolioReviewCommand.description
    assert "analysiere C:\\KI" in desc
    assert "analysiere C:KI" in desc                  # auch ohne Backslash getippt
    assert "analyze_event_log" in desc                # Abgrenzung ausdruecklich
    assert desc.startswith(tasks.PortfolioReviewCommand.BASE_DESCRIPTION[:40])


def test_commands_answer_honestly_without_service():
    tasks.configure(lambda: None, "")
    for cmd in tasks.COMMANDS:
        result = cmd.execute(Plan(intent=cmd.name))
        assert result.status == Status.FAILED
        assert "task_portfolio_root" in result.message


def test_portfolio_review_submits_frozen_readonly_task():
    service = FakeService()
    tasks.configure(lambda: service, "C:\\KI")

    result = tasks.PortfolioReviewCommand().execute(
        Plan(intent="portfolio_review", raw_input="analysiere mein portfolio",
             parameters={"source": "telegram"}))

    assert result.status == Status.SUCCESS
    task = service.submitted[0]
    assert task.allowed_actions == ["collect_portfolio_evidence"]
    assert task.policy_id == "read_only_v1"
    assert any(c.required for c in task.definition_of_done)
    assert "C:\\KI" in task.goal and task.source == "telegram"
    assert task.task_id[:8] in result.message          # Kurz-ID in der Quittung


def test_second_submit_reports_conflict_honestly():
    service = FakeService(fail_code="ACTIVE_TASK_CONFLICT")
    tasks.configure(lambda: service, "C:\\KI")
    result = tasks.PortfolioReviewCommand().execute(Plan(intent="portfolio_review"))
    assert result.status == Status.FAILED
    assert "läuft bereits" in result.message


def test_status_and_cancel_pass_through():
    service = FakeService()
    tasks.configure(lambda: service, "C:\\KI")
    status = tasks.TaskStatusCommand().execute(Plan(intent="task_status"))
    assert "Runde 1/3" in status.message
    cancelled = tasks.TaskCancelCommand().execute(Plan(intent="task_cancel"))
    assert cancelled.status == Status.SUCCESS and "abc12345" in cancelled.message
    assert service.cancelled == 1


# --- Runtime-Verdrahtung (B6) ---------------------------------------------------

class _NoPlanAI:
    """FakeAI ohne Provider: der TaskService entsteht, aber der Entscheider
    fehlt -> ein Lauf endet ehrlich mit BLOCKED/PLANNER_UNAVAILABLE."""

    def get_plan(self, user_input, history):
        return Plan(intent="chat", raw_input=user_input)

    def answer(self, user_input, history, long_term_summary=""):
        return "ok"

    def generate(self, system, user_text, **kw):
        return "{}"


def _runtime(tmp_path: Path, root: str):
    from jarvis_runtime import JarvisRuntime

    memory_dir = tmp_path / "memory_data"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)
    config = Config(memory_dir=memory_dir, log_dir=tmp_path / "logs",
                    max_history_entries=20)
    config.task_portfolio_root = root
    return JarvisRuntime(config, ai=_NoPlanAI())


def test_runtime_without_root_builds_service_but_gates_portfolio(tmp_path):
    """H3: der TaskService existiert IMMER (Legacy-Adapter §9); der
    Portfolio-AUFTRAG bleibt ohne Root ehrlich abgeschaltet."""
    runtime = _runtime(tmp_path, "")
    assert runtime.task_service is not None
    review = tasks.PortfolioReviewCommand().execute(Plan(intent="portfolio_review"))
    assert review.status == Status.FAILED and "task_portfolio_root" in review.message
    status = tasks.TaskStatusCommand().execute(Plan(intent="task_status"))
    assert status.status == Status.SUCCESS and "Kein aktiver Auftrag" in status.message


def test_runtime_lease_is_shared_between_delegation_and_tasks(tmp_path):
    """Regressionstest (Nachtrag 4): haelt die Legacy-Delegation die Lease,
    startet der TaskService-Auftrag NICHT - erst nach der Freigabe (und
    endet dann ehrlich BLOCKED/PLANNER_UNAVAILABLE, weil kein Provider)."""
    portfolio_root = tmp_path / "ki"
    (portfolio_root / "alpha").mkdir(parents=True)
    runtime = _runtime(tmp_path, str(portfolio_root))
    assert runtime.task_service is not None
    service = runtime.task_service

    assert runtime.execution_lease.acquire("delegation") is True
    service.start()
    try:
        result = tasks.PortfolioReviewCommand().execute(Plan(intent="portfolio_review"))
        assert result.status == Status.SUCCESS
        task_id = result.data["task_id"]
        time.sleep(0.3)
        assert service.store.load(task_id).status is TaskStatus.READY   # wartet auf Lease

        runtime.execution_lease.release("delegation")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            task = service.store.load(task_id)
            if task.status is TaskStatus.BLOCKED:
                break
            time.sleep(0.05)
        assert task.status is TaskStatus.BLOCKED
        assert task.blocker.code == "PLANNER_UNAVAILABLE"
    finally:
        service.stop()


def test_dispatch_delegation_respects_task_lease(tmp_path):
    """Umgekehrte Richtung: haelt der TaskService die Lease, lehnt die
    Legacy-Delegation hoeflich ab (busy) statt parallel zu laufen."""
    runtime = _runtime(tmp_path, "")
    assert runtime.execution_lease.acquire("task_service") is True
    replies: list[str] = []

    runtime._dispatch_delegation("analysiere x", Plan(intent="delegate_analysis"),
                                 command=None, reply_callback=replies.append)

    assert replies and "läuft bereits" in replies[0].lower()
    assert runtime._delegation_active is False       # nichts gestartet
