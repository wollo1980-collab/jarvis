"""Tests fuer commands/delegate.py - das Agenten-Backend ist injiziert,
es wird kein echter `claude` aufgerufen. Allowlist/Artefakt laufen gegen
tmp_path."""
from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import commands.delegate as delegate
from core.agent_backend import AgentResult
from core.models import Plan, Status


class FakeBackend:
    """Ersetzt AgentBackend 1:1. Merkt sich den letzten Aufruf und liefert
    ein voreingestelltes Ergebnis."""

    def __init__(self, result: AgentResult):
        self._result = result
        self.calls: list[tuple[Path, str]] = []
        self.cancel_events: list = []

    def analyze(self, repo, question, limits, cancel_event=None):
        self.calls.append((repo, question))
        self.cancel_events.append(cancel_event)
        return self._result


def _config(tmp_path: Path, repos: list) -> SimpleNamespace:
    return SimpleNamespace(agent_repos=repos, memory_dir=tmp_path, agent_timeout=120.0)


def _configure_with_repo(tmp_path: Path, backend) -> Path:
    """Legt ein echtes Repo-Verzeichnis an (die Allowlist verlangt is_dir())
    und verdrahtet den Command darauf."""
    repo = tmp_path / "jarvis"
    repo.mkdir()
    delegate.configure(
        _config(tmp_path, [{"alias": "jarvis", "path": str(repo)}]),
        backend=backend,
    )
    return repo


def test_success_writes_artifact_and_short_summary(tmp_path: Path):
    backend = FakeBackend(
        AgentResult(text="Analyse-Text.", ok=True, duration_seconds=1.2, num_turns=3, cost_usd=0.01)
    )
    repo = _configure_with_repo(tmp_path, backend)

    result = delegate.DelegateAnalysisCommand().execute(
        Plan(intent="delegate_analysis", target="jarvis", parameters={"question": "wie laeuft X?"})
    )

    assert result.status == Status.SUCCESS
    assert "Analyse-Text." in result.message
    assert backend.calls == [(repo, "wie laeuft X?")]

    artifacts = list((tmp_path / "delegations").glob("*.md"))
    assert len(artifacts) == 1
    body = artifacts[0].read_text(encoding="utf-8")
    assert "Analyse-Text." in body
    assert "jarvis" in body
    assert result.data["artifact"] == str(artifacts[0])


def test_alias_case_insensitive(tmp_path: Path):
    backend = FakeBackend(AgentResult(text="ok", ok=True, duration_seconds=0.1))
    _configure_with_repo(tmp_path, backend)

    result = delegate.DelegateAnalysisCommand().execute(
        Plan(intent="delegate_analysis", target="JARVIS", parameters={"question": "frage"})
    )
    assert result.status == Status.SUCCESS


def test_question_fallback_from_raw_input(tmp_path: Path):
    backend = FakeBackend(AgentResult(text="ok", ok=True, duration_seconds=0.1))
    repo = _configure_with_repo(tmp_path, backend)

    result = delegate.DelegateAnalysisCommand().execute(
        Plan(
            intent="delegate_analysis",
            target="jarvis",
            parameters={},
            raw_input="analysiere jarvis: wie funktioniert der Executor?",
        )
    )
    assert result.status == Status.SUCCESS
    assert backend.calls[0][1] == "wie funktioniert der Executor?"


def test_unknown_repo_is_rejected_fail_closed(tmp_path: Path):
    backend = FakeBackend(AgentResult(text="darf nie laufen", ok=True, duration_seconds=0.1))
    _configure_with_repo(tmp_path, backend)

    result = delegate.DelegateAnalysisCommand().execute(
        Plan(intent="delegate_analysis", target="geheim", parameters={"question": "frage"})
    )
    assert result.status == Status.FAILED
    assert "nicht fuer die Analyse freigegeben" in result.message
    assert backend.calls == []  # Backend NIE aufgerufen


def test_empty_allowlist_needs_configuration(tmp_path: Path):
    backend = FakeBackend(AgentResult(text="x", ok=True, duration_seconds=0.1))
    delegate.configure(_config(tmp_path, []), backend=backend)

    result = delegate.DelegateAnalysisCommand().execute(
        Plan(intent="delegate_analysis", target="jarvis", parameters={"question": "frage"})
    )
    assert result.status == Status.NEEDS_CLARIFICATION
    assert "agent_repos" in result.message


def test_missing_question_needs_clarification(tmp_path: Path):
    backend = FakeBackend(AgentResult(text="x", ok=True, duration_seconds=0.1))
    _configure_with_repo(tmp_path, backend)

    result = delegate.DelegateAnalysisCommand().execute(
        Plan(intent="delegate_analysis", target="jarvis", parameters={})
    )
    assert result.status == Status.NEEDS_CLARIFICATION


def test_backend_failure_is_reported_not_silent(tmp_path: Path):
    backend = FakeBackend(
        AgentResult(text="", ok=False, duration_seconds=0.1, detail="Zeitlimit ueberschritten")
    )
    _configure_with_repo(tmp_path, backend)

    result = delegate.DelegateAnalysisCommand().execute(
        Plan(intent="delegate_analysis", target="jarvis", parameters={"question": "frage"})
    )
    assert result.status == Status.FAILED
    assert "Zeitlimit" in result.message


def test_command_is_marked_long_running():
    # Die Runtime entscheidet allein am Attribut, ob asynchron ausgefuehrt wird.
    assert delegate.DelegateAnalysisCommand.long_running is True


def test_run_async_matches_execute_and_forwards_cancel_event(tmp_path: Path):
    backend = FakeBackend(AgentResult(text="Analyse-Text.", ok=True, duration_seconds=0.1))
    _configure_with_repo(tmp_path, backend)
    cancel = threading.Event()

    result = delegate.DelegateAnalysisCommand().run_async(
        Plan(intent="delegate_analysis", target="jarvis", parameters={"question": "frage"}),
        cancel_event=cancel,
    )

    assert result.status == Status.SUCCESS
    assert "Analyse-Text." in result.message
    # Der Kill-Switch wird bis zum Backend durchgereicht.
    assert backend.cancel_events == [cancel]


def test_execute_passes_no_cancel_event(tmp_path: Path):
    backend = FakeBackend(AgentResult(text="ok", ok=True, duration_seconds=0.1))
    _configure_with_repo(tmp_path, backend)

    delegate.DelegateAnalysisCommand().execute(
        Plan(intent="delegate_analysis", target="jarvis", parameters={"question": "frage"})
    )
    assert backend.cancel_events == [None]


def test_non_existing_path_is_skipped_from_allowlist(tmp_path: Path):
    backend = FakeBackend(AgentResult(text="x", ok=True, duration_seconds=0.1))
    delegate.configure(
        _config(tmp_path, [{"alias": "ghost", "path": str(tmp_path / "does-not-exist")}]),
        backend=backend,
    )
    result = delegate.DelegateAnalysisCommand().execute(
        Plan(intent="delegate_analysis", target="ghost", parameters={"question": "frage"})
    )
    # Pfad existiert nicht -> nicht in der Allowlist -> wie leere Allowlist.
    assert result.status == Status.NEEDS_CLARIFICATION
