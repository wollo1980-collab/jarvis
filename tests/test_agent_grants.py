"""Tests fuer core/agent_grants.py - die vier Waechter der Schreib-Freigabe-
Bruecke (ADR-059). BASE_DIR wird pro Test auf ein Test-Verzeichnis gesetzt."""
from __future__ import annotations

import core.agent_grants as agent_grants
from core.agent_grants import is_framework_scaffold, may_grant


def _make_scaffold(path, with_marker: bool = True):
    """Legt ein minimales Framework-Geruest (docs/PROJECT_STATE.md + logbook) an."""
    (path / "docs").mkdir(parents=True)
    (path / "docs" / "PROJECT_STATE.md").write_text("---\nversion: x\n---\n", encoding="utf-8")
    marker = "Abgeleitet aus AI Project Framework Commit `abc` am 2026-07-12.\n" if with_marker else "kein Marker\n"
    (path / "docs" / "logbook.md").write_text(f"# Logbook\n\n{marker}", encoding="utf-8")


def _setup(tmp_path, monkeypatch):
    """projects_root + ein separates Jarvis-Repo (BASE_DIR) unter tmp_path."""
    root = tmp_path / "projects"
    base = tmp_path / "jarvis"
    root.mkdir()
    base.mkdir()
    monkeypatch.setattr(agent_grants, "BASE_DIR", base)
    return root, base


def test_allows_fresh_subproject_under_root(tmp_path, monkeypatch):
    root, _ = _setup(tmp_path, monkeypatch)
    proj = root / "pomodoro"
    proj.mkdir()
    assert may_grant(proj, str(root)) is True


def test_denies_jarvis_own_repo(tmp_path, monkeypatch):
    """Waechter 3: nie Jarvis' eigenes Repo (auch wenn es unter root laege)."""
    base = tmp_path / "jarvis"
    base.mkdir()
    monkeypatch.setattr(agent_grants, "BASE_DIR", base)
    # root = tmp_path, base liegt also UNTER root
    assert may_grant(base, str(tmp_path)) is False


def test_denies_under_jarvis_repo(tmp_path, monkeypatch):
    base = tmp_path / "jarvis"
    (base / "core").mkdir(parents=True)
    monkeypatch.setattr(agent_grants, "BASE_DIR", base)
    assert may_grant(base / "core", str(tmp_path)) is False


def test_denies_root_itself(tmp_path, monkeypatch):
    """Waechter 2: projects_root selbst ist kein Unterprojekt."""
    root, _ = _setup(tmp_path, monkeypatch)
    assert may_grant(root, str(root)) is False


def test_denies_outside_root(tmp_path, monkeypatch):
    root, _ = _setup(tmp_path, monkeypatch)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    assert may_grant(outside, str(root)) is False


def test_failclosed_without_projects_root(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert may_grant(tmp_path / "projects" / "x", "") is False


# --- is_framework_scaffold (ADR-069): Wiedereinstieg nur bei echtem Jarvis-Geruest

def test_scaffold_detected_with_marker(tmp_path):
    proj = tmp_path / "erinnerungs-manager"
    _make_scaffold(proj, with_marker=True)
    assert is_framework_scaffold(proj) is True


def test_scaffold_rejected_without_marker(tmp_path):
    """Ein Nachbarordner mit PROJECT_STATE, aber OHNE die Pflichtzeile (z. B. der
    oeffentliche Export) ist KEIN aufgreifbares Geruest."""
    proj = tmp_path / "jarvis-public-export"
    _make_scaffold(proj, with_marker=False)
    assert is_framework_scaffold(proj) is False


def test_scaffold_rejected_when_state_missing(tmp_path):
    proj = tmp_path / "nur-logbook"
    (proj / "docs").mkdir(parents=True)
    (proj / "docs" / "logbook.md").write_text("Abgeleitet aus AI Project Framework\n", encoding="utf-8")
    assert is_framework_scaffold(proj) is False


def test_scaffold_rejected_for_nonexistent(tmp_path):
    assert is_framework_scaffold(tmp_path / "gibt-es-nicht") is False
