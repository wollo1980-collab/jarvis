"""Tests fuer den Verifikations-Harnisch (Kampagne B Stufe 3, ADR-055):
core/verify.py (sicherer Whitelist-Executor) und commands/verify.py
(Alias-Aufloesung + Bericht). Echte Subprozesse nur fuer den Executor-
Kern (schnell, trivial); die Kommando-Ebene mockt run_verification."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import core.verify as verify
from commands import REGISTRY
from core.models import Plan, Status


# --- core/verify.py: sicherer Executor ------------------------------------

def test_run_command_captures_success():
    result = verify._run_command([sys.executable, "-c", "print('hallo')"], cwd=".", timeout=30)
    assert result["ok"] is True
    assert result["returncode"] == 0
    assert "hallo" in result["tail"]


def test_run_command_reports_nonzero():
    result = verify._run_command([sys.executable, "-c", "import sys; sys.exit(3)"], cwd=".", timeout=30)
    assert result["ok"] is False
    assert result["returncode"] == 3


def test_run_command_timeout_is_failsafe():
    result = verify._run_command(
        [sys.executable, "-c", "import time; time.sleep(5)"], cwd=".", timeout=0.5
    )
    assert result["ok"] is False
    assert "Zeitlimit" in result["tail"]


def test_run_command_missing_executable_is_failsafe():
    result = verify._run_command(["dieses-programm-gibt-es-nicht-xyz"], cwd=".", timeout=5)
    assert result["ok"] is False
    assert "Konnte Befehl nicht starten" in result["tail"]


def test_run_verification_skips_gate_when_absent(tmp_path, monkeypatch):
    # Kein Gate-Skript im Repo -> Gate uebersprungen, nur pytest zaehlt.
    calls = []

    def fake_run(argv, cwd, timeout):
        calls.append(argv)
        return {"ok": True, "returncode": 0, "tail": "1 passed"}

    monkeypatch.setattr(verify, "_run_command", fake_run)
    report = verify.run_verification(tmp_path)

    gate = next(c for c in report["checks"] if c["name"] == "Konsistenz-Gate")
    assert gate.get("skipped") is True
    assert report["ok"] is True
    # Nur der pytest-Aufruf ging an den Executor (Gate uebersprungen).
    assert any("pytest" in " ".join(map(str, a)) for a in calls)


def test_run_verification_runs_gate_when_present(tmp_path, monkeypatch):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_consistency.py").write_text("print('ok')", encoding="utf-8")

    monkeypatch.setattr(verify, "_run_command",
                        lambda argv, cwd, timeout: {"ok": True, "returncode": 0, "tail": "ok"})
    report = verify.run_verification(tmp_path)

    names = [c["name"] for c in report["checks"]]
    assert "Konsistenz-Gate" in names and "Testsuite (pytest)" in names
    assert all(not c.get("skipped") for c in report["checks"])
    assert report["ok"] is True


def test_run_verification_fails_when_a_check_fails(tmp_path, monkeypatch):
    def fake_run(argv, cwd, timeout):
        ok = "pytest" not in " ".join(map(str, argv))  # Tests fallen durch
        return {"ok": ok, "returncode": 0 if ok else 1, "tail": "FAILED" if not ok else "ok"}

    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_consistency.py").write_text("x", encoding="utf-8")
    monkeypatch.setattr(verify, "_run_command", fake_run)

    report = verify.run_verification(tmp_path)
    assert report["ok"] is False


# --- commands/verify.py: Alias-Aufloesung + Bericht -----------------------

def _config(tmp_path):
    return SimpleNamespace(
        agent_repos=[{"alias": "jarvis", "path": str(tmp_path)}],
        agent_write_repos=[{"alias": "jkc", "path": str(tmp_path)}],
    )


def test_command_registered_stufe0_longrunning():
    cmd = REGISTRY["verify_repo"]
    assert cmd.name == "verify_repo"
    assert cmd.requires_confirmation is False
    assert cmd.long_running is True


def test_configure_builds_allowlist_from_both_repo_lists(tmp_path):
    import commands.verify as vcmd
    vcmd.configure(_config(tmp_path))
    assert set(vcmd._allowlist) == {"jarvis", "jkc"}  # lesend UND schreibend


def test_verify_command_reports_success(tmp_path, monkeypatch):
    import commands.verify as vcmd
    vcmd.configure(_config(tmp_path))
    monkeypatch.setattr(vcmd, "run_verification", lambda repo: {
        "repo": "jkc", "ok": True,
        "checks": [{"name": "Konsistenz-Gate", "ok": True}, {"name": "Testsuite (pytest)", "ok": True}],
    })

    result = vcmd.VerifyRepoCommand().execute(Plan(intent="verify_repo", target="jkc"))

    assert result.status == Status.SUCCESS
    assert "bestanden" in result.message
    assert result.data["ok"] is True


def test_verify_command_reports_failure_with_snippet(tmp_path, monkeypatch):
    import commands.verify as vcmd
    vcmd.configure(_config(tmp_path))
    monkeypatch.setattr(vcmd, "run_verification", lambda repo: {
        "repo": "jkc", "ok": False,
        "checks": [{"name": "Testsuite (pytest)", "ok": False, "tail": "1 failed\nE assert 0"}],
    })

    result = vcmd.VerifyRepoCommand().execute(Plan(intent="verify_repo", target="jkc"))

    assert result.status == Status.FAILED
    assert "durchgefallen" in result.message
    assert "assert 0" in result.message  # Anriss der Fehlausgabe


def test_verify_command_unknown_repo_fails(tmp_path):
    import commands.verify as vcmd
    vcmd.configure(_config(tmp_path))

    result = vcmd.VerifyRepoCommand().execute(Plan(intent="verify_repo", target="fremd"))

    assert result.status == Status.FAILED
    assert "nicht freigegeben" in result.message


def test_verify_command_no_repos_configured_asks(tmp_path):
    import commands.verify as vcmd
    vcmd.configure(SimpleNamespace(agent_repos=[], agent_write_repos=[]))

    result = vcmd.VerifyRepoCommand().execute(Plan(intent="verify_repo", target="jkc"))

    assert result.status == Status.NEEDS_CLARIFICATION


def test_verify_repo_in_planner_prompt():
    from core.ai import build_system_prompt
    prompt = build_system_prompt()
    assert "verify_repo" in prompt
    assert "pruefe das Repo" in prompt
