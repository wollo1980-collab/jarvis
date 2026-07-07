"""Tests fuer commands/plan.py - das Agenten-Backend ist injiziert, es wird
kein echter `claude` aufgerufen. Der Vorschlag wird von Jarvis selbst additiv
in memory_dir/proposals geschrieben (Agent bleibt read-only)."""
from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import commands.plan as plan
from core.agent_backend import AgentResult
from core.models import Plan, Status


class FakeBackend:
    """Ersetzt AgentBackend 1:1. Merkt sich Aufrufe (inkl. Prompt + cancel_event)
    und liefert ein voreingestelltes Ergebnis."""

    def __init__(self, result: AgentResult):
        self._result = result
        self.calls: list[tuple] = []

    def analyze(self, repo, question, limits, cancel_event=None):
        self.calls.append((repo, question, cancel_event))
        return self._result


def _config(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(memory_dir=tmp_path, agent_timeout=120.0)


def _configure(tmp_path: Path, backend) -> None:
    plan.configure(_config(tmp_path), backend=backend)


def test_command_is_long_running():
    assert plan.PlanNextStepCommand.long_running is True


def test_success_writes_isolated_proposal_and_summary(tmp_path: Path):
    backend = FakeBackend(
        AgentResult(text="# Titel\n## Empfehlung\nScheibe 7.", ok=True, duration_seconds=1.0, num_turns=3)
    )
    _configure(tmp_path, backend)

    result = plan.PlanNextStepCommand().execute(Plan(intent="plan_next_step"))

    assert result.status == Status.SUCCESS
    assert "Scheibe 7." in result.message
    # Jarvis schreibt den Entwurf - additiv, isoliert in proposals/.
    proposals = list((tmp_path / "proposals").glob("*-plan-next-step.md"))
    assert len(proposals) == 1
    body = proposals[0].read_text(encoding="utf-8")
    assert "## Empfehlung" in body
    assert result.data["artifact"] == str(proposals[0])


def test_write_isolation_touches_only_proposals_dir(tmp_path: Path):
    backend = FakeBackend(AgentResult(text="ok", ok=True, duration_seconds=0.1))
    _configure(tmp_path, backend)

    plan.PlanNextStepCommand().execute(Plan(intent="plan_next_step"))

    # Es entsteht ausschliesslich das proposals/-Verzeichnis, nichts anderes.
    entries = sorted(p.name for p in tmp_path.iterdir())
    assert entries == ["proposals"]


def test_run_async_matches_execute_and_forwards_cancel_event(tmp_path: Path):
    backend = FakeBackend(AgentResult(text="# T\n## Empfehlung\nX", ok=True, duration_seconds=0.1))
    _configure(tmp_path, backend)
    cancel = threading.Event()

    result = plan.PlanNextStepCommand().run_async(Plan(intent="plan_next_step"), cancel_event=cancel)

    assert result.status == Status.SUCCESS
    # Der Kill-Switch wird bis zum Backend durchgereicht.
    assert backend.calls[0][2] is cancel


def test_backend_failure_is_reported_not_silent(tmp_path: Path):
    backend = FakeBackend(
        AgentResult(text="", ok=False, duration_seconds=0.1, detail="Zeitlimit ueberschritten")
    )
    _configure(tmp_path, backend)

    result = plan.PlanNextStepCommand().execute(Plan(intent="plan_next_step"))

    assert result.status == Status.FAILED
    assert "Zeitlimit" in result.message
    # Bei Fehlschlag wird kein Entwurf geschrieben.
    assert not (tmp_path / "proposals").exists()


def test_not_configured_raises_clear_error(tmp_path: Path):
    # Zustand aus vorherigen Tests zuruecksetzen.
    plan._configured = False
    plan._backend = None
    try:
        plan.PlanNextStepCommand().execute(Plan(intent="plan_next_step"))
        assert False, "erwartete RuntimeError"
    except RuntimeError as e:
        assert "nicht konfiguriert" in str(e)


def test_prompt_enforces_reading_honesty_and_fixed_structure():
    prompt = plan._PLANNING_PROMPT
    # liest den echten Projektstand selbst
    assert "PROJECT_STATE.md" in prompt and "HANDBOOK.md" in prompt and "docs/adr/" in prompt
    # ehrlicher "kein Schritt"-Fall (kein erzwungener Vorschlag)
    assert "keinen klar begründbaren nächsten Schritt" in prompt
    assert "NIEMALS einen Vorschlag" in prompt
    # feste Artefakt-Struktur (alle Abschnitte)
    for section in (
        "## Kurzfassung",
        "## Warum jetzt?",
        "## Vorgeschlagener Umfang",
        "## Begründung",
        "## Risiken",
        "## Governance-/ADR-Prüfung",
        "## Offene Fragen",
        "## Empfehlung",
    ):
        assert section in prompt
