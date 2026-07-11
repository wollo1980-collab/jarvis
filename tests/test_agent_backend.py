"""Tests fuer core/agent_backend.py - die Popen-Factory ist injiziert,
es wird KEIN echter `claude` aufgerufen (kein Netzwerk, keine Kosten).
Seit ADR-035 ist der Lauf cancelbar (Kill-Switch)."""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

from core.agent_backend import (
    AgentLimits, ClaudeCodeBackend, RedirectChannel, _user_message_json,
)


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


def test_session_limit_429_gives_friendly_detail(tmp_path: Path):
    # 429/Session-Limit: claude beendet sich mit Exit != 0 und meldet den
    # Fehler als JSON. Die menschenlesbare result-Meldung (mit Reset-Hinweis)
    # muss beim Nutzer ankommen - keine Roh-JSON-Wand (Dogfooding-Fund
    # 2026-07-08). Auch der irrefuehrende subtype="success" darf nicht greifen.
    payload = {
        "type": "result",
        "subtype": "success",
        "is_error": True,
        "api_error_status": 429,
        "num_turns": 1,
        "result": "You've hit your session limit · resets 10:20am (Europe/Berlin)",
    }
    backend = _backend_returning(
        FakePopen(output=(json.dumps(payload), ""), returncode=1)
    )
    result = backend.analyze(tmp_path, "frage", AgentLimits())

    assert result.ok is False
    assert "resets 10:20am" in result.detail  # Reset-Hinweis bleibt erhalten
    assert "Session-Limit" in result.detail    # freundliche Rahmung
    assert "{" not in result.detail            # keine Roh-JSON-Wand
    assert "is_error" not in result.detail
    assert "success" != result.detail          # nicht der irrefuehrende subtype


def test_nonzero_exit_with_json_error_surfaces_result(tmp_path: Path):
    # Exit != 0, aber verstehbares Fehler-JSON: die result-Meldung wird
    # herausgezogen, statt das rohe JSON durchzureichen.
    payload = {
        "is_error": True,
        "subtype": "error_during_execution",
        "result": "Etwas ging schief",
    }
    backend = _backend_returning(
        FakePopen(output=(json.dumps(payload), ""), returncode=1)
    )
    result = backend.analyze(tmp_path, "frage", AgentLimits())

    assert result.ok is False
    assert "Etwas ging schief" in result.detail
    assert "{" not in result.detail


def test_work_argv_scopes_writes_to_repo_and_forbids_bash(tmp_path: Path):
    """ADR-050: Schreib-Kaefig - Edit/Write sind PFADGEBUNDEN aufs Ziel-Repo,
    Bash existiert nicht (kein git, keine Ausfuehrung)."""
    captured = {}
    popen = FakePopen(output=(json.dumps({"is_error": False, "result": "ok"}), ""))
    backend = _backend_returning(popen, captured)

    backend.work(tmp_path, "lege die CONTRIBUTING.md an", AgentLimits(timeout_seconds=42.0))

    argv = captured["argv"]
    scope = str(tmp_path).replace("\\", "/")
    assert f"Edit({scope}/**)" in argv
    assert f"Write({scope}/**)" in argv
    assert "Bash" not in argv          # exakte Tool-Namen, kein Bash
    assert "Edit" not in argv          # nur die GEBUNDENE Form, nie pauschal
    assert "Write" not in argv
    # Auftrag steckt im Kaefig-Rahmen (Grenzen explizit benannt):
    prompt = argv[argv.index("-p") + 1]
    assert "lege die CONTRIBUTING.md an" in prompt
    assert "AUSSCHLIESSLICH" in prompt
    assert "Dokumentationspflichten" in prompt  # Befund 10.07.: Gate kam ohne logbook
    assert captured["kwargs"]["cwd"] == str(tmp_path)


# --- Durchsicht / Streaming (ADR-056 Scheibe 1) ----------------------------


class FakeStreamPopen:
    """Popen-Ersatz fuer den Stream-Modus: stdout liefert die Ereignis-Zeilen
    (stream-json), stderr ist leer, wait() setzt den Exit-Code."""

    def __init__(self, lines, returncode=0):
        self.stdout = iter(list(lines))
        self.stderr = iter([])
        self.returncode = None
        self._rc = returncode
        self.killed = False

    def wait(self, timeout=None):
        self.returncode = self._rc
        return self._rc

    def kill(self):
        self.killed = True
        self.returncode = -9

    def communicate(self, timeout=None):
        return ("", "")


def _stream_lines(events):
    return [json.dumps(e) + "\n" for e in events]


_SUCCESS_STREAM = _stream_lines([
    {"type": "system", "subtype": "init"},
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "Ich lese die Datei."}]}},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "jkc/cli.py"}}]}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "content": "..."}]}},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "jkc/cli.py"}}]}},
    {"type": "result", "subtype": "success", "is_error": False, "result": "Fertig.", "num_turns": 5, "total_cost_usd": 0.42},
])


def test_streaming_emits_normalized_events_and_final_result(tmp_path: Path):
    events = []
    backend = ClaudeCodeBackend(popen=lambda argv, **kw: FakeStreamPopen(_SUCCESS_STREAM))

    result = backend.work(tmp_path, "tu was", AgentLimits(timeout_seconds=10), on_event=events.append)

    # Ergebnis kommt weiterhin sauber (Stapel-Logik geteilt).
    assert result.ok and result.text == "Fertig."
    assert result.num_turns == 5 and result.cost_usd == 0.42
    # Generische Ereignisse pro Schritt; tool_result (Rauschen) uebersprungen.
    assert [e["kind"] for e in events] == ["start", "text", "tool", "tool", "done"]
    assert events[2] == {"kind": "tool", "label": "Read", "detail": "jkc/cli.py"}
    assert events[3]["label"] == "Edit"
    assert events[4]["kind"] == "done" and events[4]["label"] == "fertig"


def test_streaming_uses_stream_json_argv_only_with_on_event(tmp_path: Path):
    cap = {}
    backend = _backend_returning(FakeStreamPopen(_SUCCESS_STREAM), cap)
    backend.analyze(tmp_path, "frage", AgentLimits(), on_event=lambda e: None)
    assert "stream-json" in cap["argv"] and "--verbose" in cap["argv"]

    cap2 = {}
    backend2 = _backend_returning(FakePopen(output=(json.dumps({"is_error": False, "result": "ok"}), "")), cap2)
    backend2.analyze(tmp_path, "frage", AgentLimits())            # ohne on_event
    assert "json" in cap2["argv"] and "stream-json" not in cap2["argv"]


def test_streaming_error_result_is_failure(tmp_path: Path):
    events = []
    lines = _stream_lines([
        {"type": "system", "subtype": "init"},
        {"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "kaputt", "num_turns": 2},
    ])
    backend = ClaudeCodeBackend(popen=lambda argv, **kw: FakeStreamPopen(lines))

    result = backend.work(tmp_path, "x", AgentLimits(timeout_seconds=10), on_event=events.append)

    assert result.ok is False
    assert events[-1]["kind"] == "done" and events[-1]["label"] == "abgebrochen"


def test_streaming_without_result_event_fails_safe(tmp_path: Path):
    lines = _stream_lines([
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "hm"}]}},
    ])
    backend = ClaudeCodeBackend(popen=lambda argv, **kw: FakeStreamPopen(lines))

    result = backend.work(tmp_path, "x", AgentLimits(timeout_seconds=10), on_event=lambda e: None)

    assert result.ok is False and "ohne Ergebnis-Ereignis" in result.detail


def test_streaming_listener_exception_never_breaks_run(tmp_path: Path):
    def boom(_event):
        raise RuntimeError("Zuhoerer kaputt")

    backend = ClaudeCodeBackend(popen=lambda argv, **kw: FakeStreamPopen(_SUCCESS_STREAM))
    result = backend.work(tmp_path, "x", AgentLimits(timeout_seconds=10), on_event=boom)

    assert result.ok and result.text == "Fertig."   # Lauf laeuft trotz werfendem Zuhoerer durch


def test_normalize_events_mapping():
    n = ClaudeCodeBackend._normalize_events
    assert n({"type": "system", "subtype": "init"}) == [{"kind": "start", "label": "Agent gestartet", "detail": ""}]
    assert n({"type": "result", "is_error": False, "subtype": "success"})[0]["kind"] == "done"
    tool = n({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Grep", "input": {"pattern": "foo"}}]}})
    assert tool == [{"kind": "tool", "label": "Grep", "detail": "foo"}]
    # Werkzeug-Ergebnisse sind Rauschen -> kein Ereignis.
    assert n({"type": "user", "message": {"content": [{"type": "tool_result"}]}}) == []


# --- Umlenken / interaktiver stdin-Kanal (ADR-056 Scheibe 3) ---------------

class _FakeStdin:
    """stdin-Ersatz: merkt sich Schreibvorgaenge, laesst sich schliessen."""
    def __init__(self):
        self.writes = []
        self.closed = False

    def write(self, s):
        if self.closed:
            raise ValueError("stdin geschlossen")
        self.writes.append(s)

    def flush(self):
        pass

    def close(self):
        self.closed = True


class FakeInteractivePopen(FakeStreamPopen):
    """FakeStreamPopen + stdin (Eingabekanal). stdout liefert die Zeilen; der
    Reader-Thread erschoepft sie und beendet damit die Schleife."""
    def __init__(self, lines, returncode=0):
        super().__init__(lines, returncode)
        self.stdin = _FakeStdin()


def test_user_message_json_schema():
    line = _user_message_json("mach's anders")
    assert line.endswith("\n")
    obj = json.loads(line)
    assert obj == {"type": "user", "message": {"role": "user", "content": "mach's anders"}}


def test_redirect_channel_send_drain_clear():
    ch = RedirectChannel()
    ch.send("eins"); ch.send("  "); ch.send("zwei")  # leere werden verworfen
    assert ch.drain() == ["eins", "zwei"]
    assert ch.drain() == []                            # nach drain leer
    ch.send("drei"); ch.clear()
    assert ch.drain() == []                            # clear verwirft


def test_interactive_argv_has_input_format_only_with_redirect(tmp_path: Path):
    cap = {}
    backend = _backend_returning(FakeInteractivePopen(_stream_lines([
        {"type": "system", "subtype": "init"},
        {"type": "result", "subtype": "success", "is_error": False, "result": "ok"},
    ])), cap)
    backend.work(tmp_path, "tu was", AgentLimits(timeout_seconds=10),
                 on_event=lambda e: None, redirect=RedirectChannel())
    argv = cap["argv"]
    assert "--input-format" in argv and "stream-json" in argv
    assert "--replay-user-messages" in argv
    # Der Auftrag steht NICHT als Positions-Argument (er kommt ueber stdin).
    assert not any("tu was" in a for a in argv)


def test_interactive_sends_prompt_over_stdin_and_closes(tmp_path: Path):
    events = []
    popen = FakeInteractivePopen(_stream_lines([
        {"type": "system", "subtype": "init"},
        {"type": "result", "subtype": "success", "is_error": False,
         "result": "Fertig.", "num_turns": 1, "total_cost_usd": 0.1},
    ]))
    backend = ClaudeCodeBackend(popen=lambda argv, **kw: popen)

    result = backend.work(tmp_path, "baue X", AgentLimits(timeout_seconds=10),
                          on_event=events.append, redirect=RedirectChannel())

    assert result.ok and result.text == "Fertig."
    # Der Auftrag ging als erste stdin-Nachricht (JSON) ein, mit dem Task-Text.
    assert len(popen.stdin.writes) == 1
    first = json.loads(popen.stdin.writes[0])
    assert first["type"] == "user" and "baue X" in first["message"]["content"]
    # stdin wurde geschlossen (Lauf natuerlich beendet), genau EIN "fertig".
    assert popen.stdin.closed
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "start" and kinds.count("done") == 1
    assert events[-1]["kind"] == "done" and events[-1]["label"] == "fertig"


class _KeepThroughClearChannel(RedirectChannel):
    """Wie RedirectChannel, aber clear() verwirft NICHT - so simuliert der Test
    'der Nutzer lenkt waehrend des Laufs um', ohne die reale, korrekte
    clear()-Bereinigung (stale Nachrichten vor dem Lauf) nachbauen zu muessen."""
    def clear(self):
        pass


def test_interactive_injects_pending_redirect_as_second_message(tmp_path: Path):
    events = []
    channel = _KeepThroughClearChannel()
    channel.send("mach's anders: nimm Y")   # bleibt trotz clear() erhalten
    popen = FakeInteractivePopen(_stream_lines([
        {"type": "system", "subtype": "init"},
        {"type": "result", "subtype": "success", "is_error": False, "result": "Zug 1"},
        {"type": "system", "subtype": "init"},
        {"type": "result", "subtype": "success", "is_error": False,
         "result": "Zug 2 nach Korrektur", "num_turns": 2},
    ]))
    backend = ClaudeCodeBackend(popen=lambda argv, **kw: popen)

    result = backend.work(tmp_path, "baue X", AgentLimits(timeout_seconds=10),
                          on_event=events.append, redirect=channel)

    # Zwei stdin-Nachrichten: Auftrag + Korrektur. Der Lauf endete NICHT nach
    # dem 1. Ergebnis (sent=2 > received=1), sondern erst nach dem 2.
    assert len(popen.stdin.writes) == 2
    second = json.loads(popen.stdin.writes[1])
    assert "mach's anders" in second["message"]["content"]
    assert result.text == "Zug 2 nach Korrektur"
    # Die Korrektur wurde als "redirect"-Ereignis fuer die Durchsicht gemeldet.
    assert any(e["kind"] == "redirect" and "mach's anders" in e["detail"] for e in events)
    # Nur EIN finales "fertig" trotz zweier Zuege.
    assert [e["kind"] for e in events].count("done") == 1


def test_interactive_finishes_cleanly_when_redirect_merged_into_one_turn(tmp_path: Path):
    """Regression (Live-Fund 2026-07-11): der Agent kann eine mid-turn-Korrektur
    in DENSELBEN Zug falten -> nur EIN result statt zwei. Der Abschluss darf
    NICHT auf ein zweites Ergebnis warten (sonst Haenger bis Timeout), sondern
    an der Zug-Grenze schliessen, sobald nichts mehr aussteht: sauberes ok."""
    events = []
    channel = _KeepThroughClearChannel()
    channel.send("zusaetzlich Y")
    popen = FakeInteractivePopen(_stream_lines([
        {"type": "system", "subtype": "init"},
        # nur EIN Ergebnis, obwohl eine Korrektur injiziert wurde:
        {"type": "result", "subtype": "success", "is_error": False,
         "result": "beides in einem Zug erledigt", "num_turns": 1},
    ]))
    backend = ClaudeCodeBackend(popen=lambda argv, **kw: popen)

    result = backend.work(tmp_path, "baue X", AgentLimits(timeout_seconds=10),
                          on_event=events.append, redirect=channel)

    assert result.ok is True                       # kein Haenger, sauberes Ergebnis
    assert result.text == "beides in einem Zug erledigt"
    assert len(popen.stdin.writes) == 2            # Auftrag + Korrektur gingen raus
    assert popen.stdin.closed
