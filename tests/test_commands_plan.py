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
    # Status-Konzept (PO-Go 11.07.2026): neue Entwuerfe starten offen -
    # nur so erscheinen sie als Vorschlags-Karte im UI.
    assert "<!-- status: offen -->" in body
    assert result.data["artifact"] == str(proposals[0])


def test_new_proposal_auto_supersedes_older_open_ones(tmp_path: Path):
    """Audit-Fund 2 (PO-Entscheidung 11.07.2026: Automatik): ein neuer
    naechster Schritt loest alle bisher OFFENEN Vorschlaege automatisch ab -
    sonst blieb ein umgesetzter Vorschlag fuer immer als 'offen'-Karte
    sichtbar (kein Code-Pfad aenderte je den Status)."""
    backend = FakeBackend(AgentResult(text="# T\n## Empfehlung\nX", ok=True, duration_seconds=0.1))
    _configure(tmp_path, backend)
    cmd = plan.PlanNextStepCommand()

    cmd.execute(Plan(intent="plan_next_step"))          # erster: offen
    import time as _t
    _t.sleep(1.1)                                       # anderer Zeitstempel-Dateiname
    cmd.execute(Plan(intent="plan_next_step"))          # zweiter: offen, erster -> abgeloest

    files = sorted((tmp_path / "proposals").glob("*.md"))
    assert len(files) == 2
    contents = [f.read_text(encoding="utf-8") for f in files]
    open_count = sum("<!-- status: offen -->" in c for c in contents)
    superseded = sum("status: abgeloest" in c for c in contents)
    assert open_count == 1        # genau der juengste bleibt offen
    assert superseded == 1        # der aeltere wurde automatisch abgeloest


def test_two_runs_same_timestamp_do_not_overwrite(tmp_path: Path, monkeypatch):
    """Audit-Fix P2a: zwei Vorschläge in derselben Sekunde erzeugen zwei Dateien
    (create-only) - das explizite Versprechen 'kein Überschreiben' hält."""
    import datetime as _dt

    class _FixedDT:
        @staticmethod
        def now():
            return _dt.datetime(2026, 7, 7, 18, 58, 24)

    monkeypatch.setattr(plan, "datetime", _FixedDT)
    backend = FakeBackend(AgentResult(text="# T\n## Empfehlung\nX", ok=True, duration_seconds=0.1))
    _configure(tmp_path, backend)
    cmd = plan.PlanNextStepCommand()

    cmd.execute(Plan(intent="plan_next_step"))
    cmd.execute(Plan(intent="plan_next_step"))

    files = sorted(p.name for p in (tmp_path / "proposals").glob("*.md"))
    assert len(files) == 2  # kein Überschreiben trotz gleicher Sekunde


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
    # der Projektstand wird kuratiert MITGEGEBEN (Stufe 1); Quellen bleiben benannt
    assert "PROJECT_STATE.md" in prompt and "HANDBOOK.md" in prompt and "docs/adr/" in prompt
    assert "mitgegeben" in prompt
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


# --- Kontext-Optimierung Stufe 1: kuratierter Kontext -------------------------


def _make_docs(tmp_path: Path, *, project_state="STATE-INHALT", adr_numbers=(1, 2, 3, 4, 5),
               changelog="CHANGELOG-INHALT", logbook="LOGBOOK-INHALT") -> None:
    docs = tmp_path / "docs"
    (docs / "adr").mkdir(parents=True)
    (docs / "PROJECT_STATE.md").write_text(project_state, encoding="utf-8")
    (docs / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (docs / "logbook.md").write_text(logbook, encoding="utf-8")
    for n in adr_numbers:
        (docs / "adr" / f"ADR-{n:03d}.md").write_text(f"ADR-NR-{n}", encoding="utf-8")


def test_assemble_context_picks_newest_adrs_and_labels_paths(tmp_path: Path):
    _make_docs(tmp_path)
    ctx = plan._assemble_context(tmp_path)

    # Jeder Block ist eindeutig mit seinem Repo-Pfad ueberschrieben (Auflage 1).
    assert "===== docs/PROJECT_STATE.md =====" in ctx and "STATE-INHALT" in ctx
    assert "===== docs/CHANGELOG.md =====" in ctx and "CHANGELOG-INHALT" in ctx
    assert "===== docs/logbook.md =====" in ctx and "LOGBOOK-INHALT" in ctx
    assert "===== docs/adr/ADR-005.md =====" in ctx
    # Nur die 3 juengsten ADRs (5,4,3) - nicht die aelteren.
    assert "ADR-NR-5" in ctx and "ADR-NR-4" in ctx and "ADR-NR-3" in ctx
    assert "ADR-NR-2" not in ctx and "ADR-NR-1" not in ctx


def test_assemble_context_caps_per_source_and_tolerates_missing(tmp_path: Path):
    docs = tmp_path / "docs"
    (docs / "adr").mkdir(parents=True)
    # PROJECT_STATE ueber dem Per-Quelle-Cap -> gekuerzt; CHANGELOG/logbook fehlen.
    (docs / "PROJECT_STATE.md").write_text("X" * (plan._CAP_PROJECT_STATE + 500), encoding="utf-8")

    ctx = plan._assemble_context(tmp_path)

    assert "…[gekürzt]" in ctx          # Cap pro Quelle greift
    assert "(nicht lesbar)" in ctx       # fehlende Dateien fail-safe toleriert


def test_assemble_context_enforces_total_cap(tmp_path: Path):
    # Alle Quellen ueber ihren Cap (inkl. der ADRs) -> Summe der Per-Quelle-Caps
    # (6000 + 3x3500 + 2500 + 2500 = 21500) sprengt den Gesamt-Cap.
    docs = tmp_path / "docs"
    (docs / "adr").mkdir(parents=True)
    big = "Y" * 10000
    (docs / "PROJECT_STATE.md").write_text(big, encoding="utf-8")
    (docs / "CHANGELOG.md").write_text(big, encoding="utf-8")
    (docs / "logbook.md").write_text(big, encoding="utf-8")
    for n in (1, 2, 3):
        (docs / "adr" / f"ADR-{n:03d}.md").write_text(big, encoding="utf-8")

    ctx = plan._assemble_context(tmp_path)

    assert len(ctx) <= plan._CAP_TOTAL + 40  # Gesamt-Cap (+ Kuerzungsmarker)
    assert "Gesamtkontext gekürzt" in ctx


def test_prompt_includes_curated_context(tmp_path: Path, monkeypatch):
    # Verdrahtung entkoppelt vom echten Repo pruefen: Sentinel statt echtem Kontext.
    monkeypatch.setattr(plan, "_assemble_context", lambda repo: "KURATIERTER-SENTINEL")
    backend = FakeBackend(AgentResult(text="# T\n## Empfehlung\nX", ok=True, duration_seconds=0.1))
    _configure(tmp_path, backend)

    plan.PlanNextStepCommand().execute(Plan(intent="plan_next_step"))

    question = backend.calls[0][1]
    assert "KURATIERTER-SENTINEL" in question       # Kontext landet im Prompt
    assert "AKTUELLER PROJEKTKONTEXT" in question    # abgesetzter Kontextblock


def test_dismiss_proposal_command_marks_open_proposal(tmp_path: Path):
    """Chat-Gegenstueck zum ✕ (PO-Reibung 2026-07-11): verwirft den offenen
    Eigenvorschlag -> Status 'verworfen', Karte verschwindet."""
    _configure(tmp_path, FakeBackend(AgentResult(text="x", ok=True, duration_seconds=0.1)))
    prop_dir = tmp_path / "proposals"
    prop_dir.mkdir()
    (prop_dir / "20260711-plan.md").write_text(
        "# Mein Schritt\n\n<!-- status: offen -->\n\nerstellt 2026-07-11T07:56\n", encoding="utf-8"
    )

    result = plan.DismissProposalCommand().execute(Plan(intent="dismiss_proposal"))

    assert result.status == Status.SUCCESS
    assert "verworfen" in result.message and "Mein Schritt" in result.message
    from core.dashboard_data import open_proposal
    assert open_proposal(tmp_path) is None   # danach kein offener Vorschlag mehr


def test_dismiss_proposal_command_without_open_proposal(tmp_path: Path):
    """Kein offener Vorschlag -> freundlicher Hinweis, kein Fehler (und ganz
    sicher kein Herunterfahren)."""
    _configure(tmp_path, FakeBackend(AgentResult(text="x", ok=True, duration_seconds=0.1)))
    (tmp_path / "proposals").mkdir()

    result = plan.DismissProposalCommand().execute(Plan(intent="dismiss_proposal"))

    assert result.status == Status.SUCCESS
    assert "kein offener Vorschlag" in result.message
