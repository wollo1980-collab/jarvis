"""Tests fuer start_project (ADR-049) - Geruest nach PROJECT_INIT.

Das "Framework" ist ein Mini-Git-Repo in tmp_path (echtes git, kein Mock -
die Pflichtzeile braucht einen realen Commit-Hash)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import commands.project as project_commands
from core.models import Plan, Status
from core.project_scaffold import scaffold_project, validate_name


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
        encoding="utf-8",
    ).stdout.strip()


@pytest.fixture()
def framework(tmp_path: Path) -> Path:
    fw = tmp_path / "framework"
    (fw / "docs" / "adr").mkdir(parents=True)
    (fw / "docs" / "PROJECT_INIT.md").write_text("Projektstart-Kontrakt", encoding="utf-8")
    (fw / "docs" / "adr" / "ADR-TEMPLATE.md").write_text("# ADR-NNN: Titel\n", encoding="utf-8")
    (fw / "CONTRIBUTING.md").write_text("---\ncharter_version: 9.9\n---\n", encoding="utf-8")
    _git(["init", "-b", "main"], fw)
    _git(["add", "-A"], fw)
    _git(["-c", "user.name=T", "-c", "user.email=t@t", "commit", "-m", "init"], fw)
    return fw


def test_validate_name_normalizes_and_rejects():
    assert validate_name("  JKC ") == "jkc"
    for bad in ("", "a", "UPPER ONLY!", "../evil", "a" * 41, "1abc"):
        with pytest.raises(ValueError):
            validate_name(bad)


def test_scaffold_creates_repo_with_pflichtzeile(tmp_path, framework):
    root = tmp_path / "projekte"
    root.mkdir()

    target = scaffold_project(root, "jkc", framework)

    assert target == (root / "jkc").resolve()
    for rel in (
        "README.md", "docs/PROJECT_STATE.md", "docs/CHANGELOG.md",
        "docs/logbook.md", "docs/framework_feedback.md",
        "docs/adr/ADR-TEMPLATE.md", ".gitignore", "pytest.ini",
        "tests/test_smoke.py",
    ):
        assert (target / rel).exists(), rel

    logbook = (target / "docs" / "logbook.md").read_text(encoding="utf-8")
    fw_hash = _git(["rev-parse", "--short", "HEAD"], framework)
    assert f"Abgeleitet aus AI Project Framework Commit `{fw_hash}`" in logbook
    assert "charter_version 9.9" in logbook
    assert "Onboarding" in logbook  # ehrlich: Inhalte kommen aus dem Interview

    # Eigenes Git-Repo mit fruehem ersten Commit (PROJECT_INIT):
    assert (target / ".git").is_dir()
    assert "Projektstart" in _git(["log", "--format=%s", "-1"], target)
    assert _git(["status", "--porcelain"], target) == ""  # alles committet


def test_scaffold_refuses_existing_directory(tmp_path, framework):
    root = tmp_path / "projekte"
    (root / "jkc").mkdir(parents=True)
    with pytest.raises(ValueError, match="existiert bereits"):
        scaffold_project(root, "jkc", framework)
    # Nichts im existierenden Verzeichnis angefasst:
    assert list((root / "jkc").iterdir()) == []


def test_scaffold_requires_real_framework(tmp_path):
    root = tmp_path / "projekte"
    root.mkdir()
    with pytest.raises(ValueError, match="Framework"):
        scaffold_project(root, "jkc", tmp_path / "kein-framework")


def test_command_is_stufe_2_and_failed_when_unconfigured():
    cmd = project_commands.StartProjectCommand()
    # PO 14.07. (Bestaetigungs-Diaet, ADR-068): Geruest anlegen ist umkehrbar
    # (Ordner loeschen) und fragt nicht mehr - der BAU fragt mit Vorschau.
    assert cmd.requires_confirmation is False
    project_commands.configure("", "")
    result = cmd.execute(Plan(intent="start_project", target="jkc"))
    assert result.status == Status.FAILED
    assert "nicht konfiguriert" in result.message


def test_command_end_to_end(tmp_path, framework):
    root = tmp_path / "projekte"
    root.mkdir()
    project_commands.configure(str(root), str(framework))
    try:
        result = project_commands.StartProjectCommand().execute(
            Plan(intent="start_project", target="JKC")
        )
    finally:
        project_commands.configure("", "")

    assert result.status == Status.SUCCESS
    assert result.data["path"] == str((root / "jkc").resolve())
    assert "Onboarding" in result.message  # der naechste Pflichtschritt wird benannt


def test_command_asks_for_name_when_missing():
    result = project_commands.StartProjectCommand().execute(Plan(intent="start_project"))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_start_project_is_registered():
    """Live-Befund 10.07.2026: 'Dafuer habe ich keinen passenden Befehl' -
    _register_all() hat eine EXPLIZITE Modulliste (keine Auto-Discovery),
    und project fehlte darin. Dieser Test prueft den echten Dispatch-Weg."""
    from commands import REGISTRY

    assert "start_project" in REGISTRY
    assert REGISTRY["start_project"].requires_confirmation is False  # PO 14.07.
