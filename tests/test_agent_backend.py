"""Tests fuer core/agent_backend.py - die Popen-Factory ist injiziert,
es wird KEIN echter `claude` aufgerufen (kein Netzwerk, keine Kosten).
Seit ADR-035 ist der Lauf cancelbar (Kill-Switch)."""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

from core.agent_backend import AgentLimits, ClaudeCodeBackend


class FakePopen:
    """Minimaler subprocess.Popen-Ersatz. `blocks=True` simuliert einen noch
    laufenden Prozess (communicate wirft TimeoutExpired), bis kill() ihn
    beendet - so lassen sich Timeout und Cancel deterministisch testen."""

    def __init__(self, *, output=("", ""), returncode=0, blocks=False):
        self._output = output
        self.returncode = returncode
        self._blocks = blocks
        self.killed = False
        self.kill_count = 0

    def communicate(self, timeout=None):
        if self.killed:
            return ("", "")
        if self._blocks:
            raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout)
        return self._output

    def kill(self):
        self.kill_count += 1
        self.killed = True


def _backend_returning(popen: FakePopen, captured=None) -> ClaudeCodeBackend:
    def factory(argv, **kwargs):
        if captured is not None:
            captured["argv"] = argv
            captured["kwargs"] = kwargs
        return popen

    return ClaudeCodeBackend(popen=factory)


def test_backend_exposes_display_name():
    # ADR-036: der Adapter kennt seinen Namen; die Fachlogik liest ihn nur.
    assert ClaudeCodeBackend.name == "Claude Code"


def test_argv_enforces_read_only_and_utf8(tmp_path: Path):
    captured = {}
    popen = FakePopen(output=(json.dumps({"is_error": False, "result": "ok"}), ""))
    backend = _backend_returning(popen, captured)

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
    assert captured["kwargs"]["cwd"] == str(tmp_path)
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
    backend = _backend_returning(FakePopen(output=(json.dumps(payload), "")))
    result = backend.analyze(tmp_path, "frage", AgentLimits())

    assert result.ok is True
    assert result.text == "Der Executor laeuft die Schritte seriell ab."
    assert result.num_turns == 7
    assert result.cost_usd == 0.0123


def test_timeout_kills_process_and_reports(tmp_path: Path):
    popen = FakePopen(blocks=True)
    backend = _backend_returning(popen)
    # timeout_seconds=0 -> erste Iteration erkennt sofort das Zeitlimit.
    result = backend.analyze(tmp_path, "frage", AgentLimits(timeout_seconds=0.0))

    assert result.ok is False
    assert "Zeitlimit" in result.detail
    assert popen.kill_count == 1  # Kill-Switch/Timeout hat den Prozess beendet


def test_cancel_event_aborts_running_process(tmp_path: Path):
    popen = FakePopen(blocks=True)
    backend = _backend_returning(popen)
    cancel = threading.Event()
    cancel.set()  # bereits gesetzt: erste Iteration bricht ab

    result = backend.analyze(
        tmp_path, "frage", AgentLimits(timeout_seconds=300.0), cancel_event=cancel
    )

    assert result.ok is False
    assert "abgebrochen" in result.detail.lower()
    assert popen.kill_count == 1


def test_natural_completion_wins_over_pending_cancel(tmp_path: Path):
    # Prozess ist bereits fertig (blocks=False) -> Ergebnis gewinnt, auch wenn
    # gleichzeitig ein Cancel gesetzt ist (die Arbeit liegt vor).
    payload = {"is_error": False, "result": "fertig"}
    popen = FakePopen(output=(json.dumps(payload), ""))
    backend = _backend_returning(popen)
    cancel = threading.Event()
    cancel.set()

    result = backend.analyze(tmp_path, "frage", AgentLimits(), cancel_event=cancel)

    assert result.ok is True
    assert result.text == "fertig"
    assert popen.kill_count == 0  # kein Kill noetig


def test_nonzero_exit_is_failure_with_detail(tmp_path: Path):
    backend = _backend_returning(FakePopen(output=("", "boom"), returncode=1))
    result = backend.analyze(tmp_path, "frage", AgentLimits())

    assert result.ok is False
    assert "boom" in result.detail


def test_broken_json_is_failure_but_keeps_raw_text(tmp_path: Path):
    backend = _backend_returning(FakePopen(output=("das ist kein json", "")))
    result = backend.analyze(tmp_path, "frage", AgentLimits())

    assert result.ok is False
    assert "kein gueltiges JSON" in result.detail
    assert result.text == "das ist kein json"


def test_is_error_flag_maps_to_failure(tmp_path: Path):
    payload = {"is_error": True, "subtype": "error_max_turns", "result": ""}
    backend = _backend_returning(FakePopen(output=(json.dumps(payload), "")))
    result = backend.analyze(tmp_path, "frage", AgentLimits())

    assert result.ok is False
    assert result.detail == "error_max_turns"


def test_missing_binary_is_reported(tmp_path: Path):
    def factory(*a, **k):
        raise FileNotFoundError()

    backend = ClaudeCodeBackend(popen=factory)
    result = backend.analyze(tmp_path, "frage", AgentLimits())

    assert result.ok is False
    assert "nicht gefunden" in result.detail
