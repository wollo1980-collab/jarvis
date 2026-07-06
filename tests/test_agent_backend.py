"""Tests fuer core/agent_backend.py - der Subprozess-Runner ist injiziert,
es wird KEIN echter `claude` aufgerufen (kein Netzwerk, keine Kosten)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from core.agent_backend import AgentLimits, ClaudeCodeBackend


def _completed(returncode=0, stdout="", stderr=""):
    """Minimaler Ersatz fuer subprocess.CompletedProcess."""
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_argv_enforces_read_only_and_json(tmp_path: Path):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _completed(stdout=json.dumps({"is_error": False, "result": "ok"}))

    backend = ClaudeCodeBackend(runner=fake_run)
    backend.analyze(tmp_path, "wie funktioniert der Executor?", AgentLimits(timeout_seconds=42.0))

    argv = captured["argv"]
    assert argv[0] == "claude"
    assert "-p" in argv
    assert "wie funktioniert der Executor?" in argv
    # Read-only: genau die drei lesenden Tools, kein Bash/Edit/Write.
    assert "--allowedTools" in argv
    for tool in ("Read", "Grep", "Glob"):
        assert tool in argv
    for forbidden in ("Bash", "Edit", "Write"):
        assert forbidden not in argv
    assert "--output-format" in argv and "json" in argv
    # cwd + harter Timeout werden an den Subprozess durchgereicht.
    assert captured["kwargs"]["cwd"] == str(tmp_path)
    assert captured["kwargs"]["timeout"] == 42.0
    # UTF-8 explizit: sonst zerschiesst Windows (cp1252) die Umlaute der
    # claude-Ausgabe (Live-Fund Rauchtest 2026-07-06).
    assert captured["kwargs"]["encoding"] == "utf-8"


def test_json_success_maps_text_turns_cost(tmp_path: Path):
    payload = {
        "is_error": False,
        "subtype": "success",
        "result": "Der Executor laeuft die Schritte seriell ab.",
        "num_turns": 7,
        "total_cost_usd": 0.0123,
    }
    backend = ClaudeCodeBackend(runner=lambda *a, **k: _completed(stdout=json.dumps(payload)))
    result = backend.analyze(tmp_path, "frage", AgentLimits())

    assert result.ok is True
    assert result.text == "Der Executor laeuft die Schritte seriell ab."
    assert result.num_turns == 7
    assert result.cost_usd == 0.0123


def test_timeout_is_reported_not_raised(tmp_path: Path):
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout"))

    backend = ClaudeCodeBackend(runner=fake_run)
    result = backend.analyze(tmp_path, "frage", AgentLimits(timeout_seconds=1.0))

    assert result.ok is False
    assert "Zeitlimit" in result.detail
    assert result.text == ""


def test_nonzero_exit_is_failure_with_detail(tmp_path: Path):
    backend = ClaudeCodeBackend(
        runner=lambda *a, **k: _completed(returncode=1, stderr="boom")
    )
    result = backend.analyze(tmp_path, "frage", AgentLimits())

    assert result.ok is False
    assert "boom" in result.detail


def test_broken_json_is_failure_but_keeps_raw_text(tmp_path: Path):
    backend = ClaudeCodeBackend(
        runner=lambda *a, **k: _completed(stdout="das ist kein json")
    )
    result = backend.analyze(tmp_path, "frage", AgentLimits())

    assert result.ok is False
    assert "kein gueltiges JSON" in result.detail
    assert result.text == "das ist kein json"


def test_is_error_flag_maps_to_failure(tmp_path: Path):
    payload = {"is_error": True, "subtype": "error_max_turns", "result": ""}
    backend = ClaudeCodeBackend(runner=lambda *a, **k: _completed(stdout=json.dumps(payload)))
    result = backend.analyze(tmp_path, "frage", AgentLimits())

    assert result.ok is False
    assert result.detail == "error_max_turns"


def test_missing_binary_is_reported(tmp_path: Path):
    def fake_run(*a, **k):
        raise FileNotFoundError()

    backend = ClaudeCodeBackend(runner=fake_run)
    result = backend.analyze(tmp_path, "frage", AgentLimits())

    assert result.ok is False
    assert "nicht gefunden" in result.detail
