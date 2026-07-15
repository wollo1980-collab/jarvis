"""Tests fuer commands/delegate.py - das Agenten-Backend ist injiziert,
es wird kein echter `claude` aufgerufen. Allowlist/Artefakt laufen gegen
tmp_path."""
from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import commands.delegate as delegate
from core.agent_backend import AgentResult
from core.models import Plan, Status


@pytest.fixture(autouse=True)
def _stub_self_check(monkeypatch):
    """Die Selbstpruefung (ADR-055) nach delegate_work laesst echtes Gate +
    pytest laufen - fuer die Delegations-Tests wird sie auf ein schnelles,
    gruenes Stub gesetzt. Der Hook selbst wird gezielt getestet
    (test_work_success_runs_self_check_*), dort ueberschrieben."""
    import core.verify

    monkeypatch.setattr(
        core.verify, "run_verification",
        lambda repo, **kw: {"repo": Path(repo).name, "ok": True,
                            "checks": [{"name": "Testsuite (pytest)", "ok": True}]},
    )


class FakeBackend:
    """Ersetzt AgentBackend 1:1. Merkt sich den letzten Aufruf und liefert
    ein voreingestelltes Ergebnis."""

    name = "TestBackend"

    def __init__(self, result: AgentResult):
        self._result = result
        self.calls: list[tuple[Path, str]] = []
        self.cancel_events: list = []
        self.redirects: list = []

    def analyze(self, repo, question, limits, cancel_event=None, on_event=None, redirect=None):
        self.calls.append((repo, question))
        self.cancel_events.append(cancel_event)
        self.redirects.append(redirect)
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


def test_two_analyses_same_timestamp_do_not_overwrite(tmp_path: Path, monkeypatch):
    """Audit-Fix P2a: zwei Analysen in derselben Sekunde erzeugen zwei
    Artefakte (create-only), kein Überschreiben."""
    import datetime as _dt

    class _FixedDT:
        @staticmethod
        def now():
            return _dt.datetime(2026, 7, 7, 18, 58, 24)

    monkeypatch.setattr(delegate, "datetime", _FixedDT)
    backend = FakeBackend(AgentResult(text="Analyse", ok=True, duration_seconds=0.1))
    _configure_with_repo(tmp_path, backend)
    cmd = delegate.DelegateAnalysisCommand()
    plan_obj = Plan(intent="delegate_analysis", target="jarvis", parameters={"question": "q"})

    cmd.execute(plan_obj)
    cmd.execute(plan_obj)

    files = list((tmp_path / "delegations").glob("*.md"))
    assert len(files) == 2


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
    assert "keinen Lese-Zugriff" in result.message
    assert "Was hast du gebaut?" in result.message   # die naechste Tuer
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


def test_delegate_requires_injected_backend(tmp_path: Path):
    # ADR-036: die Fachlogik nennt/instanziiert kein Backend - es MUSS injiziert
    # werden. Ohne Backend gibt es keinen eingebauten Default, und die Analyse
    # scheitert klar statt still mit einem festen Werkzeug zu laufen.
    delegate.configure(_config(tmp_path, [{"alias": "jarvis", "path": str(tmp_path)}]), backend=None)
    assert delegate._backend is None
    with pytest.raises(RuntimeError, match="Backend"):
        delegate.DelegateAnalysisCommand().execute(
            Plan(intent="delegate_analysis", target="jarvis", parameters={"question": "frage"})
        )


def test_artifact_header_shows_injected_backend_name(tmp_path: Path):
    backend = FakeBackend(AgentResult(text="Analyse.", ok=True, duration_seconds=0.1))
    _configure_with_repo(tmp_path, backend)

    delegate.DelegateAnalysisCommand().execute(
        Plan(intent="delegate_analysis", target="jarvis", parameters={"question": "q"})
    )

    artifact = next((tmp_path / "delegations").glob("*.md"))
    body = artifact.read_text(encoding="utf-8")
    assert "TestBackend" in body            # generischer Name aus dem Backend
    assert "Claude Code" not in body         # kein hartkodierter Werkzeugname


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


# --- Schreibende Delegation im Kaefig (ADR-050, Stufe 0) --------------------

import subprocess


class FakeWorkBackend(FakeBackend):
    """FakeBackend + work(): optionaler on_work-Hook simuliert die
    Dateiaenderungen des Agenten im Ziel-Repo."""

    def __init__(self, result: AgentResult, on_work=None):
        super().__init__(result)
        self._on_work = on_work
        self.wide_tools_calls: list = []

    def work(self, repo, task, limits, cancel_event=None, on_event=None,
             redirect=None, wide_tools=False):
        self.calls.append((repo, task))
        self.cancel_events.append(cancel_event)
        self.redirects.append(redirect)
        self.wide_tools_calls.append(wide_tools)
        if self._on_work is not None:
            self._on_work(repo)
        return self._result


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )


def _write_repo(tmp_path: Path) -> Path:
    """Echtes, sauberes Git-Repo als Schreib-Ziel (die Sichtung braucht git)."""
    repo = tmp_path / "jkc"
    repo.mkdir()
    (repo / "README.md").write_text("# jkc\n", encoding="utf-8")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "-A")
    _run_git(repo, "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-m", "init")
    return repo


def _configure_write(tmp_path: Path, backend, repo: Path, warn_usd: float = 2.0) -> None:
    delegate.configure(
        SimpleNamespace(
            agent_repos=[],
            agent_write_repos=[{"alias": "jkc", "path": str(repo)}],
            memory_dir=tmp_path,
            agent_timeout=120.0,
            agent_cost_warn_usd=warn_usd,
        ),
        backend=backend,
    )


def test_work_is_stufe_2_and_needs_separate_write_allowlist(tmp_path: Path):
    """Lesen heisst nicht schreiben: agent_repos allein schaltet
    delegate_work NICHT frei."""
    cmd = delegate.DelegateWorkCommand()
    assert cmd.requires_confirmation is True
    assert cmd.long_running is True

    backend = FakeWorkBackend(AgentResult(text="", ok=True, duration_seconds=0.1))
    repo = tmp_path / "nur-lesen"
    repo.mkdir()
    delegate.configure(
        SimpleNamespace(agent_repos=[{"alias": "jarvis", "path": str(repo)}],
                        memory_dir=tmp_path, agent_timeout=120.0),
        backend=backend,
    )

    result = cmd.execute(Plan(intent="delegate_work", target="jarvis",
                              parameters={"task": "mach was"}))
    assert result.status == Status.NEEDS_CLARIFICATION
    assert "agent_write_repos" in result.message
    assert backend.calls == []  # kein Lauf ohne Schreib-Allowlist


def test_misheard_alias_suggests_closest_but_never_auto_resolves(tmp_path: Path):
    """Live-Reibung 15.07.: die Sprach-Transkription machte aus «jkc» erst
    «Jack», dann «Jck» - beide fielen aus der exakten Schreib-Allowlist und
    der Agent startete nie (also feuerte auch der 🔐-Hook nie). Die Ablehnung
    NENNT jetzt den naechsten Nachbarn, loest aber NIE automatisch auf (eine
    Schreib-Freigabe bleibt exakt und ausdruecklich)."""
    backend = FakeWorkBackend(AgentResult(text="", ok=True, duration_seconds=0.1))
    repo = _write_repo(tmp_path)
    _configure_write(tmp_path, backend, repo)

    for misheard in ("jck", "Jack", "jc"):
        result = delegate.DelegateWorkCommand().execute(
            Plan(intent="delegate_work", target=misheard, parameters={"task": "pip list"}))
        assert result.status == Status.FAILED
        assert "«jkc»" in result.message           # Nachbar wird genannt
        assert backend.calls == []                 # aber NIE automatisch gestartet

    # Ein voellig anderer Name bekommt KEINEN irrefuehrenden Vorschlag:
    far = delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="videoschnitt", parameters={"task": "x"}))
    assert "«jkc»" not in far.message
    assert backend.calls == []


def test_closest_alias_helper_is_conservative():
    from commands.delegate import _closest_alias

    assert _closest_alias("Jck", ["jkc"]) == "jkc"       # Transposition
    assert _closest_alias("Jack", ["jkc"]) == "jkc"      # +1 Buchstabe, dist<=2
    assert _closest_alias("videoschnitt", ["jkc"]) == ""  # weit weg -> kein Vorschlag
    assert _closest_alias("", ["jkc"]) == ""


def test_work_success_writes_diff_artifact_and_commits_nothing(tmp_path: Path):
    def agent_changes(repo: Path) -> None:
        (repo / "README.md").write_text("# jkc\n\nNeu vom Agenten.\n", encoding="utf-8")
        (repo / "docs").mkdir()
        (repo / "docs" / "NEU.md").write_text("Inhalt vom Agenten\n", encoding="utf-8")

    backend = FakeWorkBackend(
        AgentResult(text="Zwei Dateien angepasst.", ok=True, duration_seconds=3.0,
                    num_turns=5, cost_usd=0.42),
        on_work=agent_changes,
    )
    repo = _write_repo(tmp_path)
    _configure_write(tmp_path, backend, repo)

    result = delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc",
             parameters={"task": "README ergaenzen und NEU.md anlegen"})
    )

    assert result.status == Status.SUCCESS
    assert "nichts committet" in result.message
    assert result.data["changed_files"] == 2
    # Kein Commit durch den Lauf: die Aenderungen liegen im Arbeitsbaum.
    porcelain = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert porcelain.strip() != ""
    # Diff-Artefakt zur Sichtung enthaelt Aenderung + neue Datei:
    artifact = Path(result.data["artifact"])
    content = artifact.read_text(encoding="utf-8")
    assert "Neu vom Agenten" in content
    assert "NEUE DATEI: docs/NEU.md" in content
    assert "Zwei Dateien angepasst." in content


def test_work_success_runs_self_check_and_reports_green(tmp_path: Path, monkeypatch):
    """Stufe 3 (ADR-055): nach erfolgreichem Bau prueft Jarvis selbst - ein
    gruenes Ergebnis wird an die Antwort angehaengt (Bauen->Pruefen->Vorlegen)."""
    import core.verify
    seen = {}

    def fake_verify(repo, **kw):
        seen["repo"] = Path(repo).name
        return {"repo": Path(repo).name, "ok": True,
                "checks": [{"name": "Konsistenz-Gate", "ok": True},
                           {"name": "Testsuite (pytest)", "ok": True}]}

    monkeypatch.setattr(core.verify, "run_verification", fake_verify)
    backend = FakeWorkBackend(AgentResult(text="fertig", ok=True, duration_seconds=1.0))
    repo = _write_repo(tmp_path)
    _configure_write(tmp_path, backend, repo)

    result = delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "x"}))

    assert result.status == Status.SUCCESS
    assert "Selbstpruefung bestanden" in result.message
    assert result.data["self_check"]["ok"] is True
    assert seen["repo"] == "jkc"          # genau das Ziel-Repo wurde geprueft


def test_work_success_self_check_red_warns_but_stays_success(tmp_path: Path, monkeypatch):
    """Eine ROTE Selbstpruefung warnt deutlich ('nicht committen'), aendert aber
    den Delegations-Status nicht - der Bau lief, der Diff liegt zur Sichtung."""
    import core.verify
    monkeypatch.setattr(core.verify, "run_verification",
                        lambda repo, **kw: {"repo": Path(repo).name, "ok": False,
                                            "checks": [{"name": "Testsuite (pytest)", "ok": False,
                                                        "tail": "1 failed"}]})
    backend = FakeWorkBackend(AgentResult(text="fertig", ok=True, duration_seconds=1.0))
    repo = _write_repo(tmp_path)
    _configure_write(tmp_path, backend, repo)

    result = delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "x"}))

    assert result.status == Status.SUCCESS          # Bau lief - Sichtung beim PO
    assert "Selbstpruefung ROT" in result.message
    assert "nicht committen" in result.message
    assert result.data["self_check"]["ok"] is False


def test_red_self_check_records_reflection_and_feeds_next_task(tmp_path: Path, monkeypatch):
    """Plan G: eine ROTE Selbstpruefung haelt eine Reflexion fest; der NAECHSTE
    Auftrag in demselben Projekt bekommt sie mit ('nicht wiederholen')."""
    import core.verify
    monkeypatch.setattr(core.verify, "run_verification",
                        lambda repo, **kw: {"repo": Path(repo).name, "ok": False,
                                            "checks": [{"name": "Testsuite (pytest)", "ok": False}]})
    backend = FakeWorkBackend(AgentResult(text="fertig", ok=True, duration_seconds=1.0))
    repo = _write_repo(tmp_path)
    _configure_write(tmp_path, backend, repo)

    # 1. Lauf: rot -> Reflexion festgehalten
    delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "feature X bauen"}))
    notes = delegate._reflections.recent("jkc")
    assert notes and "ROT" in notes[0]

    # 2. Lauf: der an den Agenten gereichte Auftrag traegt die Reflexion
    delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "feature Y bauen"}))
    last_task = backend.calls[-1][1]
    assert "NICHT wiederholen" in last_task
    assert "ROT" in last_task


def test_work_self_check_failure_is_failsafe(tmp_path: Path, monkeypatch):
    """Scheitert die Pruefung SELBST (nicht der Code), bleibt die Delegation
    erfolgreich - nur ein Vermerk, kein Absturz."""
    import core.verify

    def boom(repo, **kw):
        raise RuntimeError("verify kaputt")

    monkeypatch.setattr(core.verify, "run_verification", boom)
    backend = FakeWorkBackend(AgentResult(text="fertig", ok=True, duration_seconds=1.0))
    repo = _write_repo(tmp_path)
    _configure_write(tmp_path, backend, repo)

    result = delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "x"}))

    assert result.status == Status.SUCCESS
    assert "nicht durchfuehrbar" in result.message
    assert result.data["self_check"] is None


def test_work_forwards_agent_events_to_sink(tmp_path: Path):
    """Durchsicht (ADR-056 Scheibe 1): der event_sink der Runtime wird bis
    zum Backend durchgereicht - die Schritt-Ereignisse landen beim Publisher
    (der sie ins UI leitet)."""
    seen = []

    class StreamBackend(FakeBackend):
        def work(self, repo, task, limits, cancel_event=None, on_event=None,
                 redirect=None, wide_tools=False):
            self.calls.append((repo, task))
            if on_event is not None:
                on_event({"kind": "start", "label": "Agent gestartet", "detail": ""})
                on_event({"kind": "tool", "label": "Read", "detail": "x.py"})
            return self._result

    backend = StreamBackend(AgentResult(text="ok", ok=True, duration_seconds=0.1))
    repo = _write_repo(tmp_path)
    delegate.configure(
        SimpleNamespace(agent_repos=[], agent_write_repos=[{"alias": "jkc", "path": str(repo)}],
                        memory_dir=tmp_path, agent_timeout=120.0, agent_cost_warn_usd=2.0),
        backend=backend, event_sink=seen.append,
    )

    delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "x"}))

    kinds = [e["kind"] for e in seen]
    assert "start" in kinds and "tool" in kinds


def test_work_forwards_redirect_channel_to_backend(tmp_path: Path):
    """Umlenken (ADR-056 Scheibe 3): der Redirect-Draht der Runtime wird bis
    zum Backend durchgereicht (zusammen mit event_sink laeuft der Bau
    interaktiv). Analyse bleibt davon unberuehrt (redirect nur bei work)."""
    from core.agent_backend import RedirectChannel

    channel = RedirectChannel()
    backend = FakeWorkBackend(AgentResult(text="ok", ok=True, duration_seconds=0.1))
    repo = _write_repo(tmp_path)
    delegate.configure(
        SimpleNamespace(agent_repos=[], agent_write_repos=[{"alias": "jkc", "path": str(repo)}],
                        memory_dir=tmp_path, agent_timeout=120.0, agent_cost_warn_usd=2.0),
        backend=backend, event_sink=lambda e: None, redirect=channel,
    )

    delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "x"}))

    assert backend.redirects[-1] is channel   # exakt der Runtime-Draht


def test_work_refuses_dirty_tree(tmp_path: Path):
    """Sauberer Baum als Vorbedingung - sonst ist die Sichtung nicht
    eindeutig. Der Agent wird gar nicht erst gestartet."""
    backend = FakeWorkBackend(AgentResult(text="", ok=True, duration_seconds=0.1))
    repo = _write_repo(tmp_path)
    (repo / "README.md").write_text("lokal veraendert\n", encoding="utf-8")
    _configure_write(tmp_path, backend, repo)

    result = delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "egal"})
    )
    assert result.status == Status.FAILED
    assert "unbestaetigte Aenderungen" in result.message
    assert backend.calls == []


def test_work_refuses_directory_without_git(tmp_path: Path):
    backend = FakeWorkBackend(AgentResult(text="", ok=True, duration_seconds=0.1))
    repo = tmp_path / "jkc"
    repo.mkdir()
    _configure_write(tmp_path, backend, repo)

    result = delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "egal"})
    )
    assert result.status == Status.FAILED
    assert "kein Git-Repo" in result.message
    assert backend.calls == []


def test_work_warns_above_cost_threshold(tmp_path: Path):
    backend = FakeWorkBackend(
        AgentResult(text="teuer.", ok=True, duration_seconds=1.0, cost_usd=5.0)
    )
    repo = _write_repo(tmp_path)
    _configure_write(tmp_path, backend, repo, warn_usd=2.0)

    result = delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "grosse Arbeit"})
    )
    assert result.status == Status.SUCCESS
    assert "Warnschwelle" in result.message
    # Ehrliche Einordnung (PO-Hinweis 2026-07-10): Gegenwert, nicht Rechnung -
    # der Agent laeuft ueber das MAX-Abo, die knappe Ressource ist Kontingent.
    assert "Gegenwert" in result.message
    assert "Abo" in result.message


def test_work_prefers_verbatim_raw_over_planner_paraphrase(tmp_path: Path):
    """Live-Befund 2026-07-10 (AP1-Start): der Planner KUERZTE einen langen
    Auftrag beim Umschreiben in parameters.task - dem Agenten fehlte die
    halbe Spezifikation. Der Wortlaut nach dem ':' der Roheingabe gewinnt,
    wenn er laenger ist."""
    backend = FakeWorkBackend(
        AgentResult(text="ok", ok=True, duration_seconds=0.1)
    )
    repo = _write_repo(tmp_path)
    _configure_write(tmp_path, backend, repo)
    long_task = "Erstens A. Zweitens B mit vielen Details. Drittens C. Viertens D."

    result = delegate.DelegateWorkCommand().execute(
        Plan(
            intent="delegate_work", target="jkc",
            parameters={"task": "A und B."},  # Paraphrase des Planners
            raw_input=f"Erledige in jkc: {long_task}",
        )
    )

    assert result.status == Status.SUCCESS
    assert backend.calls[0][1] == long_task  # Wortlaut, nicht Paraphrase


# --- project_continue ("mach weiter an <projekt>", Kampagnen-Stufe 2) --------

import json as _json


class FakeAI:
    """Ersetzt AIEngine.generate() 1:1: liefert vorbereitetes JSON oder wirft."""

    def __init__(self, payload=None, error: Exception = None):
        self._payload = payload
        self._error = error
        self.calls: list[tuple[str, str, bool]] = []

    def generate(self, system, user_text, *, json_mode=False, max_tokens=None):
        self.calls.append((system, user_text, json_mode))
        if self._error is not None:
            raise self._error
        return _json.dumps(self._payload)


_AP2 = {
    "kurzfassung": "AP2 CLI Erfassen/Lesen: Notizen anlegen und suchen.",
    "auftrag": "Setze AP2 um: CLI-Befehle add/list/search laut PROJECT_STATE, inkl. Tests.",
}


def _continue_repo(tmp_path: Path) -> Path:
    """Sauberes Ziel-Repo MIT Projektstand (PROJECT_STATE + logbook committet -
    der Sauberer-Baum-Waechter des delegate_work-Pfads gilt auch hier)."""
    repo = tmp_path / "jkc"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    (docs / "PROJECT_STATE.md").write_text(
        "# JKC\n\nNaechstes Arbeitspaket: AP2 CLI Erfassen/Lesen.\n", encoding="utf-8"
    )
    (docs / "logbook.md").write_text("2026-07-10: AP1 abgeschlossen.\n", encoding="utf-8")
    (repo / "README.md").write_text("# jkc\n", encoding="utf-8")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "-A")
    _run_git(repo, "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-m", "init")
    return repo


def _configure_continue(tmp_path: Path, backend, repo: Path, ai) -> None:
    delegate.configure(
        SimpleNamespace(
            agent_repos=[],
            agent_write_repos=[{"alias": "jkc", "path": str(repo)}],
            memory_dir=tmp_path,
            agent_timeout=120.0,
            agent_cost_warn_usd=2.0,
        ),
        backend=backend,
        ai=ai,
    )


def test_project_continue_is_stufe_2_long_running_and_registered():
    from commands import REGISTRY

    cmd = delegate.ProjectContinueCommand
    assert cmd.requires_confirmation is True
    assert cmd.long_running is True
    assert REGISTRY["project_continue"].name == "project_continue"


def test_continue_preview_builds_task_stores_it_and_shows_kurzfassung(tmp_path: Path):
    backend = FakeWorkBackend(AgentResult(text="", ok=True, duration_seconds=0.1))
    repo = _continue_repo(tmp_path)
    ai = FakeAI(payload=_AP2)
    _configure_continue(tmp_path, backend, repo, ai)
    plan_obj = Plan(intent="project_continue", target="jkc")

    text = delegate.ProjectContinueCommand().preview(plan_obj)

    assert "AP2 CLI Erfassen/Lesen" in text
    # Der gebaute Auftrag liegt im Plan - die Ausfuehrung nach dem Ja nutzt
    # exakt ihn (kein zweiter, abweichender LLM-Lauf).
    assert plan_obj.parameters["task"] == _AP2["auftrag"]
    # Der Bau-Aufruf bekommt den kuratierten Projektstand im JSON-Modus:
    assert "Naechstes Arbeitspaket" in ai.calls[0][1]
    assert ai.calls[0][2] is True
    assert backend.calls == []  # die Vorschau delegiert NIE


def test_continue_preview_unknown_repo_recommends_no(tmp_path: Path):
    backend = FakeWorkBackend(AgentResult(text="", ok=True, duration_seconds=0.1))
    repo = _continue_repo(tmp_path)
    ai = FakeAI(payload=_AP2)
    _configure_continue(tmp_path, backend, repo, ai)
    plan_obj = Plan(intent="project_continue", target="geheim")

    text = delegate.ProjectContinueCommand().preview(plan_obj)

    assert "darf ich gerade nicht weiterbauen" in text
    assert "Bau mir" in text                        # die naechste Tuer
    assert "task" not in plan_obj.parameters
    assert ai.calls == []  # ohne Freigabe wird gar nicht erst gebaut


def test_continue_preview_no_next_step_recommends_no(tmp_path: Path):
    backend = FakeWorkBackend(AgentResult(text="", ok=True, duration_seconds=0.1))
    repo = _continue_repo(tmp_path)
    ai = FakeAI(payload={"kurzfassung": "Alle Arbeitspakete sind abgeschlossen.", "auftrag": None})
    _configure_continue(tmp_path, backend, repo, ai)
    plan_obj = Plan(intent="project_continue", target="jkc")

    text = delegate.ProjectContinueCommand().preview(plan_obj)

    assert "KEINEN delegierbaren naechsten Schritt" in text
    assert "task" not in plan_obj.parameters


def test_continue_preview_llm_error_recommends_no(tmp_path: Path):
    backend = FakeWorkBackend(AgentResult(text="", ok=True, duration_seconds=0.1))
    repo = _continue_repo(tmp_path)
    ai = FakeAI(error=RuntimeError("api down"))
    _configure_continue(tmp_path, backend, repo, ai)
    plan_obj = Plan(intent="project_continue", target="jkc")

    text = delegate.ProjectContinueCommand().preview(plan_obj)

    assert "Nein" in text  # ehrliche Empfehlung statt Crash
    assert "task" not in plan_obj.parameters


def test_continue_execute_uses_prebuilt_task_through_work_path(tmp_path: Path):
    """Nach dem Ja laeuft exakt der delegate_work-Pfad: Kaefig-Backend
    bekommt den in der Vorschau gebauten Auftrag, Diff-Artefakt entsteht,
    nichts wird committet."""

    def agent_changes(repo: Path) -> None:
        (repo / "notes.py").write_text("# AP2\n", encoding="utf-8")

    backend = FakeWorkBackend(
        AgentResult(text="AP2 umgesetzt.", ok=True, duration_seconds=2.0, cost_usd=0.5),
        on_work=agent_changes,
    )
    repo = _continue_repo(tmp_path)
    ai = FakeAI(payload=_AP2)
    _configure_continue(tmp_path, backend, repo, ai)
    plan_obj = Plan(intent="project_continue", target="jkc")
    cmd = delegate.ProjectContinueCommand()
    cmd.preview(plan_obj)  # baut den Auftrag (wie vor der echten Rueckfrage)

    result = cmd.execute(plan_obj)

    assert result.status == Status.SUCCESS
    assert backend.calls == [(repo, _AP2["auftrag"])]
    assert len(ai.calls) == 1  # kein zweiter Bau-Lauf in der Ausfuehrung
    assert result.message.startswith("Weiterarbeit an 'jkc'")
    assert "AP2 CLI Erfassen/Lesen" in result.message
    assert "nichts committet" in result.message
    assert Path(result.data["artifact"]).is_file()
    assert result.data["kurzfassung"] == _AP2["kurzfassung"]


def test_continue_execute_builds_task_itself_when_preview_did_not_run(tmp_path: Path):
    backend = FakeWorkBackend(AgentResult(text="ok", ok=True, duration_seconds=0.1))
    repo = _continue_repo(tmp_path)
    ai = FakeAI(payload=_AP2)
    _configure_continue(tmp_path, backend, repo, ai)

    result = delegate.ProjectContinueCommand().execute(
        Plan(intent="project_continue", target="jkc")
    )

    assert result.status == Status.SUCCESS
    assert backend.calls == [(repo, _AP2["auftrag"])]


def test_continue_execute_fail_closed_without_ai(tmp_path: Path):
    backend = FakeWorkBackend(AgentResult(text="darf nie laufen", ok=True, duration_seconds=0.1))
    repo = _continue_repo(tmp_path)
    _configure_continue(tmp_path, backend, repo, ai=None)

    result = delegate.ProjectContinueCommand().execute(
        Plan(intent="project_continue", target="jkc")
    )

    assert result.status == Status.FAILED
    assert "nichts delegiert" in result.message
    assert backend.calls == []


def test_continue_execute_fail_closed_without_project_state(tmp_path: Path):
    """Ohne PROJECT_STATE gibt es nichts Ehrliches fortzusetzen - kein
    geratener Auftrag aus dem logbook allein."""
    backend = FakeWorkBackend(AgentResult(text="", ok=True, duration_seconds=0.1))
    repo = _write_repo(tmp_path)  # Repo OHNE docs/PROJECT_STATE.md
    ai = FakeAI(payload=_AP2)
    _configure_continue(tmp_path, backend, repo, ai)

    result = delegate.ProjectContinueCommand().execute(
        Plan(intent="project_continue", target="jkc")
    )

    assert result.status == Status.FAILED
    assert ai.calls == []  # ohne Stand kein LLM-Aufruf
    assert backend.calls == []


def test_continue_execute_rejects_unallowed_repo_fail_closed(tmp_path: Path):
    backend = FakeWorkBackend(AgentResult(text="", ok=True, duration_seconds=0.1))
    repo = _continue_repo(tmp_path)
    ai = FakeAI(payload=_AP2)
    _configure_continue(tmp_path, backend, repo, ai)

    result = delegate.ProjectContinueCommand().execute(
        Plan(intent="project_continue", target="geheim")
    )

    assert result.status == Status.FAILED
    assert "darf ich nicht weiterarbeiten" in result.message
    assert backend.calls == []


def test_continue_execute_without_alias_asks_back(tmp_path: Path):
    backend = FakeWorkBackend(AgentResult(text="", ok=True, duration_seconds=0.1))
    repo = _continue_repo(tmp_path)
    _configure_continue(tmp_path, backend, repo, FakeAI(payload=_AP2))

    result = delegate.ProjectContinueCommand().execute(Plan(intent="project_continue"))

    assert result.status == Status.NEEDS_CLARIFICATION
    assert "jkc" in result.message  # nennt die freigegebenen Projekte


def test_continue_execute_honest_when_no_next_step(tmp_path: Path):
    backend = FakeWorkBackend(AgentResult(text="", ok=True, duration_seconds=0.1))
    repo = _continue_repo(tmp_path)
    ai = FakeAI(payload={"kurzfassung": "Alles abgeschlossen.", "auftrag": None})
    _configure_continue(tmp_path, backend, repo, ai)

    result = delegate.ProjectContinueCommand().execute(
        Plan(intent="project_continue", target="jkc")
    )

    assert result.status == Status.NEEDS_CLARIFICATION
    assert "Alles abgeschlossen." in result.message
    assert backend.calls == []


# --- Ampel-Gating + Auto-Commit (ADR-056 Scheibe 4) -------------------------

def _configure_write_autocommit(tmp_path: Path, backend, repo: Path) -> None:
    """Wie _configure_write, aber mit freigeschaltetem Auto-Commit."""
    delegate.configure(
        SimpleNamespace(
            agent_repos=[],
            agent_write_repos=[{"alias": "jkc", "path": str(repo)}],
            memory_dir=tmp_path,
            agent_timeout=120.0,
            agent_cost_warn_usd=2.0,
            agent_auto_commit=True,
        ),
        backend=backend,
    )


def test_auto_commit_disabled_by_default_commits_nothing(tmp_path: Path):
    """Fail-closed: ohne agent_auto_commit bleibt alles beim bisherigen
    Verhalten - Vorlage + Freigabe, nichts committet."""
    backend = FakeWorkBackend(
        AgentResult(text="fertig", ok=True, duration_seconds=1.0),
        on_work=lambda repo: (repo / "feature.py").write_text("x=1\n", encoding="utf-8"),
    )
    repo = _write_repo(tmp_path)
    _configure_write(tmp_path, backend, repo)  # Flag NICHT gesetzt

    result = delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "Feature bauen"}))

    assert result.status == Status.SUCCESS
    assert result.data["committed"] is None
    assert "nichts committet" in result.message
    porcelain = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True, check=True).stdout
    assert porcelain.strip() != ""  # Aenderung liegt im Arbeitsbaum


def test_auto_commit_green_commits_itself(tmp_path: Path):
    """GRUEN (unkritische Aenderung + gruene Selbstpruefung): Jarvis committet
    selbst; der Arbeitsbaum ist danach sauber, die Antwort nennt den SHA."""
    backend = FakeWorkBackend(
        AgentResult(text="Feature gebaut.", ok=True, duration_seconds=1.0),
        on_work=lambda repo: (repo / "feature.py").write_text("x=1\n", encoding="utf-8"),
    )
    repo = _write_repo(tmp_path)
    _configure_write_autocommit(tmp_path, backend, repo)

    result = delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "Feature bauen"}))

    assert result.status == Status.SUCCESS
    assert result.data["committed"]                    # SHA gesetzt
    assert "selbst committet" in result.message
    assert "Ampel GRUEN" in result.message
    # Arbeitsbaum sauber -> es wurde wirklich committet.
    porcelain = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True, check=True).stdout
    assert porcelain.strip() == ""
    # Die Commit-Message haelt Herkunft + Freigabe fest.
    body = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--pretty=%b"],
        capture_output=True, text=True, check=True).stdout
    assert "ADR-056 Scheibe 4" in body


def test_auto_commit_sensitive_file_stays_uncommitted(tmp_path: Path):
    """GELB: beruehrt der Diff eine folgenreiche Flaeche (hier eine ADR),
    committet Jarvis NICHT - Vorlage + Freigabe, Diff bleibt liegen."""
    def touches_adr(repo: Path) -> None:
        (repo / "feature.py").write_text("x=1\n", encoding="utf-8")
        (repo / "docs" / "adr").mkdir(parents=True)
        (repo / "docs" / "adr" / "ADR-007.md").write_text("# ADR-007\n", encoding="utf-8")

    backend = FakeWorkBackend(
        AgentResult(text="fertig", ok=True, duration_seconds=1.0), on_work=touches_adr)
    repo = _write_repo(tmp_path)
    _configure_write_autocommit(tmp_path, backend, repo)

    result = delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "was mit ADR"}))

    assert result.status == Status.SUCCESS
    assert result.data["committed"] is None
    assert "Ampel gelb/rot" in result.message
    porcelain = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True, check=True).stdout
    assert porcelain.strip() != ""    # nichts committet, Diff liegt bereit


def test_auto_commit_skipped_when_self_check_red(tmp_path: Path, monkeypatch):
    """Notwendige Bedingung: rote Selbstpruefung -> kein Auto-Commit, auch bei
    sonst unkritischer Aenderung."""
    import core.verify
    monkeypatch.setattr(core.verify, "run_verification",
                        lambda repo, **kw: {"repo": Path(repo).name, "ok": False,
                                            "checks": [{"name": "Testsuite (pytest)", "ok": False}]})
    backend = FakeWorkBackend(
        AgentResult(text="fertig", ok=True, duration_seconds=1.0),
        on_work=lambda repo: (repo / "feature.py").write_text("x=1\n", encoding="utf-8"),
    )
    repo = _write_repo(tmp_path)
    _configure_write_autocommit(tmp_path, backend, repo)

    result = delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "Feature"}))

    assert result.status == Status.SUCCESS
    assert result.data["committed"] is None
    assert "Selbstpruefung ROT" in result.message


# --- Kuratierter Dev-Werkzeugkasten (ADR-056 Scheibe 4b) --------------------

def _configure_write_devtools(tmp_path: Path, backend, repo: Path) -> None:
    """Wie _configure_write, aber mit freigeschaltetem Dev-Werkzeugkasten."""
    delegate.configure(
        SimpleNamespace(
            agent_repos=[],
            agent_write_repos=[{"alias": "jkc", "path": str(repo)}],
            memory_dir=tmp_path,
            agent_timeout=120.0,
            agent_cost_warn_usd=2.0,
            agent_dev_tools=True,
        ),
        backend=backend,
    )


def test_dev_tools_disabled_by_default_uses_narrow_cage(tmp_path: Path):
    """Fail-closed: ohne agent_dev_tools bleibt der enge Schreib-Kaefig."""
    backend = FakeWorkBackend(AgentResult(text="ok", ok=True, duration_seconds=0.1))
    repo = _write_repo(tmp_path)
    _configure_write(tmp_path, backend, repo)  # Flag NICHT gesetzt

    delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "x"}))

    assert backend.wide_tools_calls[-1] is False


def test_dev_tools_widens_for_sandbox_repo(tmp_path: Path):
    """Freigeschaltet + Spielplatz-Repo (nicht Jarvis selbst) → erweiterter
    Werkzeugkasten wird an den Agenten durchgereicht."""
    backend = FakeWorkBackend(AgentResult(text="ok", ok=True, duration_seconds=0.1))
    repo = _write_repo(tmp_path)
    _configure_write_devtools(tmp_path, backend, repo)

    delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "x"}))

    assert backend.wide_tools_calls[-1] is True


def test_dev_tools_never_widens_for_self_repo(tmp_path: Path, monkeypatch):
    """Pflock 1 (ADR-056): Jarvis' eigener Kern bleibt EXTRA gesperrt - selbst
    bei freigeschaltetem Dev-Werkzeugkasten NIE erweiterte Rechte im
    Selbst-Repo (nie den Ast absaegen)."""
    backend = FakeWorkBackend(AgentResult(text="ok", ok=True, duration_seconds=0.1))
    repo = _write_repo(tmp_path)
    _configure_write_devtools(tmp_path, backend, repo)
    # Ziel-Repo IST das Jarvis-Repo: Selbst-Repo-Waechter muss greifen.
    monkeypatch.setattr(delegate, "BASE_DIR", repo)

    delegate.DelegateWorkCommand().execute(
        Plan(intent="delegate_work", target="jkc", parameters={"task": "x"}))

    assert backend.wide_tools_calls[-1] is False


# --- "bau mir X": anlegen + freigeben + bauen (ADR-059) ---------------------

def _build_ai():
    return FakeAI(payload={"name": "pomodoro", "kurzfassung": "Ein Timer-CLI.",
                           "auftrag": "Baue einen Pomodoro-Timer als Python-CLI mit Start/Pause, inkl. Tests."})


def test_build_project_scaffolds_grants_and_builds(tmp_path, monkeypatch):
    """Kette (ADR-059): Beschreibung -> Name/Auftrag (LLM) -> Geruest anlegen
    -> sitzungs-lokale Schreib-Freigabe -> Bau ueber delegate_work."""
    import core.agent_grants as agent_grants

    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    monkeypatch.setattr(agent_grants, "BASE_DIR", tmp_path / "jarvis")  # separates Kern-Repo

    def fake_scaffold(root, name, framework):
        p = Path(root) / name
        p.mkdir()
        (p / "README.md").write_text(f"# {name}\n", encoding="utf-8")
        _run_git(p, "init", "-b", "main")
        _run_git(p, "add", "-A")
        _run_git(p, "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-m", "init")
        return p

    monkeypatch.setattr(delegate, "scaffold_project", fake_scaffold)
    backend = FakeWorkBackend(AgentResult(text="gebaut", ok=True, duration_seconds=1.0))
    delegate.configure(
        SimpleNamespace(agent_repos=[], agent_write_repos=[], memory_dir=tmp_path,
                        agent_timeout=120.0, agent_cost_warn_usd=2.0,
                        projects_root=str(projects_root), framework_repo=str(tmp_path / "fw")),
        backend=backend, ai=_build_ai(),
    )

    result = delegate.BuildProjectCommand().execute(
        Plan(intent="build_project", raw_input="bau mir einen Pomodoro-Timer"))

    assert result.status == Status.SUCCESS
    assert result.data["project"] == "pomodoro"
    assert "pomodoro" in delegate._write_allowlist          # wurde freigegeben
    assert backend.calls                                    # der Agent hat gebaut
    assert (projects_root / "pomodoro").is_dir()            # Geruest steht
    assert "pomodoro" in delegate._skills.names()           # als Skill registriert (A1)


def test_build_project_denies_grant_for_self_repo(tmp_path, monkeypatch):
    """Waechter (ADR-059): laege das Geruest in Jarvis' eigenem Repo, verweigert
    die Freigabe - und es wird NICHTS gebaut (fail-closed)."""
    import core.agent_grants as agent_grants

    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    self_like = projects_root / "pomodoro"

    def fake_scaffold(root, name, framework):
        p = Path(root) / name
        p.mkdir()
        return p

    monkeypatch.setattr(delegate, "scaffold_project", fake_scaffold)
    # Der Waechter sieht genau dieses Geruest als Jarvis' Kern:
    monkeypatch.setattr(agent_grants, "BASE_DIR", self_like)
    backend = FakeWorkBackend(AgentResult(text="", ok=True, duration_seconds=0.1))
    delegate.configure(
        SimpleNamespace(agent_repos=[], agent_write_repos=[], memory_dir=tmp_path,
                        agent_timeout=120.0, agent_cost_warn_usd=2.0,
                        projects_root=str(projects_root), framework_repo=str(tmp_path / "fw")),
        backend=backend, ai=_build_ai(),
    )

    result = delegate.BuildProjectCommand().execute(
        Plan(intent="build_project", raw_input="bau mir einen Pomodoro-Timer"))

    assert result.status == Status.FAILED
    assert "freigegeben" in result.message.lower() or "waechter" in result.message.lower()
    assert backend.calls == []                              # NICHT gebaut


def _make_scaffold_dir(root, name, with_marker=True):
    """Ein bereits vorhandenes Projektverzeichnis (Framework-Struktur + git)."""
    proj = Path(root) / name
    (proj / "docs").mkdir(parents=True)
    (proj / "docs" / "PROJECT_STATE.md").write_text("---\nversion: x\n---\n", encoding="utf-8")
    marker = ("Abgeleitet aus AI Project Framework Commit `abc` am 2026-07-12.\n"
              if with_marker else "kein Marker hier\n")
    (proj / "docs" / "logbook.md").write_text(f"# Logbook\n\n{marker}", encoding="utf-8")
    _run_git(proj, "init", "-b", "main")
    _run_git(proj, "add", "-A")
    _run_git(proj, "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-m", "init")
    return proj


def test_build_project_recovers_existing_jarvis_scaffold(tmp_path, monkeypatch):
    """PO-Reibung 12.07. / ADR-069: ein bereits von Jarvis angelegtes Geruest wird
    WIEDER AUFGEGRIFFEN (Freigabe + Bau) statt an 'existiert bereits' zu enden -
    scaffold_project laeuft dabei NICHT erneut."""
    import core.agent_grants as agent_grants

    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    monkeypatch.setattr(agent_grants, "BASE_DIR", tmp_path / "jarvis")
    _make_scaffold_dir(projects_root, "pomodoro", with_marker=True)

    def boom_scaffold(root, name, framework):
        raise AssertionError("scaffold_project darf beim Wiedereinstieg NICHT laufen")

    monkeypatch.setattr(delegate, "scaffold_project", boom_scaffold)
    backend = FakeWorkBackend(AgentResult(text="gebaut", ok=True, duration_seconds=1.0))
    delegate.configure(
        SimpleNamespace(agent_repos=[], agent_write_repos=[], memory_dir=tmp_path,
                        agent_timeout=120.0, agent_cost_warn_usd=2.0,
                        projects_root=str(projects_root), framework_repo=str(tmp_path / "fw")),
        backend=backend, ai=_build_ai(),
    )

    result = delegate.BuildProjectCommand().execute(
        Plan(intent="build_project", raw_input="bau mir einen Pomodoro-Timer"))

    assert result.status == Status.SUCCESS
    assert "pomodoro" in delegate._write_allowlist          # freigegeben
    assert backend.calls                                    # der Agent hat gebaut


def test_build_project_refuses_existing_nonscaffold_dir(tmp_path, monkeypatch):
    """Ein bestehender Nachbarordner OHNE Framework-Marker (z. B. der oeffentliche
    Export) wird NICHT aufgegriffen - nichts wird freigegeben oder gebaut."""
    import core.agent_grants as agent_grants

    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    monkeypatch.setattr(agent_grants, "BASE_DIR", tmp_path / "jarvis")
    _make_scaffold_dir(projects_root, "pomodoro", with_marker=False)

    def boom_scaffold(root, name, framework):
        raise AssertionError("scaffold_project darf hier nicht laufen (Ordner existiert)")

    monkeypatch.setattr(delegate, "scaffold_project", boom_scaffold)
    backend = FakeWorkBackend(AgentResult(text="", ok=True, duration_seconds=0.1))
    delegate.configure(
        SimpleNamespace(agent_repos=[], agent_write_repos=[], memory_dir=tmp_path,
                        agent_timeout=120.0, agent_cost_warn_usd=2.0,
                        projects_root=str(projects_root), framework_repo=str(tmp_path / "fw")),
        backend=backend, ai=_build_ai(),
    )

    result = delegate.BuildProjectCommand().execute(
        Plan(intent="build_project", raw_input="bau mir einen Pomodoro-Timer"))

    assert result.status == Status.FAILED
    assert "baue dort nichts" in result.message.lower() or "geruest" in result.message.lower()
    assert backend.calls == []                              # NICHT gebaut
    assert "pomodoro" not in delegate._write_allowlist


def test_build_project_preview_shows_name_and_stores_task(tmp_path, monkeypatch):
    """preview() baut Name/Auftrag vor und zeigt die Kurzfassung in der Rueckfrage."""
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    delegate.configure(
        SimpleNamespace(agent_repos=[], agent_write_repos=[], memory_dir=tmp_path,
                        agent_timeout=120.0, agent_cost_warn_usd=2.0,
                        projects_root=str(projects_root), framework_repo=str(tmp_path / "fw")),
        backend=FakeWorkBackend(AgentResult(text="", ok=True, duration_seconds=0.1)), ai=_build_ai(),
    )
    plan_obj = Plan(intent="build_project", raw_input="bau mir einen Pomodoro-Timer")

    text = delegate.BuildProjectCommand().preview(plan_obj)

    assert "pomodoro" in text
    assert plan_obj.parameters["task"]                      # Auftrag liegt fertig im Plan
    assert plan_obj.parameters["name"] == "pomodoro"


def test_project_continue_skips_confirmation_only_in_own_cage(monkeypatch, tmp_path):
    """Bestaetigungs-Diaet (PO 14.07., Ampel-Prinzip): Weiterarbeit fragt nur
    dann NICHT, wenn ALLE strukturellen Sicherungen stehen - eigenes
    Framework-Kaefig-Projekt unter projects_root UND Erlaubnis-Haken aktiv.
    Kuratierte Fremd-Repos (jkc) und Haken-aus fragen weiter (fail-closed)."""
    import commands.delegate as delegate_mod

    cmd = delegate_mod.ProjectContinueCommand()
    eigenes = tmp_path / "eigenes"
    monkeypatch.setattr(delegate_mod, "_write_allowlist",
                        {"eigenes": str(eigenes), "jkc": str(tmp_path / "jkc")})
    monkeypatch.setattr(delegate_mod, "_projects_root", str(tmp_path))
    monkeypatch.setattr(delegate_mod, "_hook_settings", object())
    monkeypatch.setattr(delegate_mod, "is_framework_scaffold",
                        lambda p: p.name == "eigenes")
    monkeypatch.setattr(delegate_mod, "may_grant", lambda p, root: True)

    assert cmd.needs_confirmation(Plan(intent="project_continue", target="eigenes")) is False
    assert cmd.needs_confirmation(Plan(intent="project_continue", target="jkc")) is True

    monkeypatch.setattr(delegate_mod, "_hook_settings", None)   # Haken aus -> fragen
    assert cmd.needs_confirmation(Plan(intent="project_continue", target="eigenes")) is True
