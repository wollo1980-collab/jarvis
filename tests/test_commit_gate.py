"""Tests fuer core/commit_gate.py - Ampel-Klassifikator + Auto-Commit
(ADR-056 Scheibe 4, Sicherheitskern). Die Klassifikation ist rein und wird
gegen porcelain-Status + Selbstpruefungs-Report geprueft; der Auto-Commit
laeuft gegen ein echtes temporaeres git-Repo."""
from __future__ import annotations

import subprocess

import pytest

from core.commit_gate import (
    build_commit_message,
    classify_commit,
    perform_auto_commit,
)

_GREEN_REPORT = {"ok": True, "checks": [{"name": "Testsuite (pytest)", "ok": True}]}
_RED_REPORT = {"ok": False, "checks": [{"name": "Testsuite (pytest)", "ok": False}]}


# --- Klassifikation: GRUEN nur unter allen Bedingungen -----------------------

def test_green_when_change_and_selfcheck_green():
    v = classify_commit(" M core/foo.py\n?? core/new.py", _GREEN_REPORT)
    assert v.green is True
    assert not v.blockers


def test_not_green_without_changes():
    v = classify_commit("", _GREEN_REPORT)
    assert v.green is False
    assert "keine Aenderungen" in v.reason


def test_not_green_when_selfcheck_red():
    v = classify_commit(" M core/foo.py", _RED_REPORT)
    assert v.green is False
    assert "Selbstpruefung" in v.reason


def test_not_green_when_selfcheck_missing():
    # None oder ok!=True (z. B. Pruefung nicht durchfuehrbar) blockiert.
    assert classify_commit(" M core/foo.py", None).green is False
    assert classify_commit(" M core/foo.py", {"ok": None}).green is False


def test_deletion_blocks_auto_commit():
    # Schaerfung b: eine Loeschung trifft im Clean-Tree-Lauf eine vorgefundene
    # Datei -> 🟡, nie Auto-Commit.
    v = classify_commit(" D core/gone.py", _GREEN_REPORT)
    assert v.green is False
    assert "Loeschung" in v.reason


def test_rename_blocks_auto_commit():
    v = classify_commit("R  alt.py -> neu.py", _GREEN_REPORT)
    assert v.green is False


@pytest.mark.parametrize(
    "path",
    [
        "docs/handbook/HANDBOOK.md",
        "CONTRIBUTING.md",
        "docs/adr/ADR-099.md",
    ],
)
def test_sensitive_paths_block_auto_commit(path):
    v = classify_commit(f" M {path}", _GREEN_REPORT)
    assert v.green is False
    assert path in v.reason


def test_kernel_guard_only_when_self_repo():
    status = " M jarvis_runtime.py"
    # Fremd-Repo (jkc): eine zufaellig gleichnamige Datei ist unkritisch.
    assert classify_commit(status, _GREEN_REPORT, guard_kernel=False).green is True
    # Eigenes Repo: Kern/Neustart bleibt extra gesperrt.
    v = classify_commit(status, _GREEN_REPORT, guard_kernel=True)
    assert v.green is False
    assert "Kern" in v.reason


def test_mixed_change_with_one_blocker_is_not_green():
    status = " M core/foo.py\n M docs/handbook/HANDBOOK.md\n?? core/new.py"
    v = classify_commit(status, _GREEN_REPORT)
    assert v.green is False
    assert any("Handbook" in b for b in v.blockers)


# --- Commit-Message ----------------------------------------------------------

def test_commit_message_subject_from_task_and_references_freigabe():
    subject, body = build_commit_message("Implementiere die Suche in jkc AP3")
    assert subject == "Implementiere die Suche in jkc AP3"
    assert "ADR-056" in body
    assert "PO-freigegebenes Arbeitspaket" in body
    assert "Auftrag: Implementiere die Suche in jkc AP3" in body


def test_commit_message_subject_capped_and_fallback():
    long_task = "x" * 200
    subject, _ = build_commit_message(long_task)
    assert len(subject) <= 80  # gekappt (72 + Ellipse)
    subject2, _ = build_commit_message("")
    assert subject2  # neutraler Fallback statt leer


# --- Auto-Commit gegen ein echtes temporaeres git-Repo -----------------------

def _init_repo(path):
    def git(*args):
        subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True, text=True, check=True,
        )
    git("init")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    git("commit", "--allow-empty", "-m", "init")
    return git


def test_perform_auto_commit_commits_worktree(tmp_path):
    git = _init_repo(tmp_path)
    (tmp_path / "feature.py").write_text("print('hi')\n", encoding="utf-8")

    ok, sha = perform_auto_commit(tmp_path, "Feature X umsetzen")

    assert ok is True
    assert sha and sha != "?"
    # Der Arbeitsbaum ist nach dem Commit sauber, und die Message steht drin.
    status = subprocess.run(
        ["git", "-C", str(tmp_path), "status", "--porcelain"],
        capture_output=True, text=True,
    )
    assert status.stdout.strip() == ""
    log = subprocess.run(
        ["git", "-C", str(tmp_path), "log", "-1", "--pretty=%s%n%b"],
        capture_output=True, text=True,
    )
    assert "Feature X umsetzen" in log.stdout
    assert "ADR-056 Scheibe 4" in log.stdout


def test_perform_auto_commit_failsafe_on_non_git(tmp_path):
    # Kein git-Repo -> ehrlicher Fehlschlag statt Exception.
    ok, detail = perform_auto_commit(tmp_path, "irgendwas")
    assert ok is False
    assert detail
