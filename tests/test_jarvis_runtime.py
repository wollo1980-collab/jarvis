"""Tests für jarvis_runtime.py - JarvisRuntime (Queue+Worker-Thread),
_RuntimeSpeech (fail-closed) und ConsoleDummyChannel (ADR-025). AIEngine
gemockt (FakeAI, gleiches Muster wie tests/test_integration.py), kein
echter API-Key/Netzwerk nötig."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import commands.delegate as delegate_commands
import commands.web as web_commands
import jarvis_runtime
from core.agent_backend import AgentResult
from core.config import Config
from core.models import Plan
from core.web_search import SearchResult
from jarvis_runtime import ConsoleDummyChannel, JarvisRuntime, _RuntimeSpeech


class FakeAI:
    """Gleiches Muster wie tests/test_integration.py::FakeAI."""

    def get_plan(self, user_input, history):
        text = user_input.lower()
        if "kritisch" in text:
            return Plan(intent="shutdown_pc", raw_input=user_input, confidence=1.0)
        if "web" in text or "internet" in text or "recherch" in text:
            return Plan(
                intent="search_web",
                target="Wetter Berlin",
                raw_input=user_input,
                confidence=1.0,
            )
        return Plan(intent="chat", raw_input=user_input, confidence=1.0)

    def answer(self, user_input, history, long_term_summary=""):
        return f"Antwort auf: {user_input}"


def _make_config(tmp_path: Path) -> Config:
    memory_dir = tmp_path / "memory_data"
    log_dir = tmp_path / "logs"
    memory_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    return Config(memory_dir=memory_dir, log_dir=log_dir, max_history_entries=20)


def _wait(event: threading.Event, timeout: float = 2.0) -> None:
    assert event.wait(timeout=timeout), "Timeout - Worker hat nicht rechtzeitig geantwortet"


def test_runtime_wires_core_stack(tmp_path):
    config = _make_config(tmp_path)
    ai = FakeAI()

    runtime = JarvisRuntime(config, ai=ai)

    assert runtime.ai is ai
    assert runtime.planner is not None
    assert runtime.executor is not None
    assert runtime.memory is not None
    assert runtime.long_term is not None


def test_runtime_configures_mail(tmp_path, monkeypatch):
    # Regressionsanker: das Mail-Briefing muss auch im Runtime-Stack
    # konfiguriert werden, damit check_mail ueber den Runtime-Telegram-Kanal
    # nicht ins Leere laeuft (Arbeitspaket B, ADR-031-Nachtrag).
    calls = []
    monkeypatch.setattr(
        jarvis_runtime.mail_commands, "configure", lambda config: calls.append(config)
    )
    JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    assert len(calls) == 1


def test_submit_and_process_single_message(tmp_path):
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("hallo", reply_callback)
        _wait(done)

        assert replies == ["Antwort auf: hallo"]
    finally:
        runtime.stop()


def test_runtime_handles_search_web(tmp_path, monkeypatch):
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    monkeypatch.setattr(
        web_commands,
        "_searcher",
        lambda query, max_results, timeout_seconds: [
            SearchResult(
                title="Wetter Berlin",
                url="https://example.com/wetter-berlin",
                snippet="Mild und trocken.",
            )
        ],
    )
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("suche im web nach wetter berlin", reply_callback)
        _wait(done)

        assert "Quellen:" in replies[0]
        assert "https://example.com/wetter-berlin" in replies[0]
    finally:
        runtime.stop()


def test_submit_without_plan_filter_is_unchanged(tmp_path):
    """Regressionsanker (ADR-027): der bisherige 2-Arg-Aufruf verhaelt
    sich exakt wie in Runtime v1 - plan_filter ist optional."""
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("hallo", reply_callback)
        _wait(done)

        assert replies == ["Antwort auf: hallo"]
    finally:
        runtime.stop()


def test_plan_filter_allows_plan_executes_normally(tmp_path):
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        def allow_all(steps):
            return steps, None

        runtime.submit("hallo", reply_callback, plan_filter=allow_all)
        _wait(done)

        assert replies == ["Antwort auf: hallo"]
        history = runtime.memory.get_history()
        assert [m.content for m in history] == ["hallo", "Antwort auf: hallo"]
    finally:
        runtime.stop()


def test_plan_filter_rejects_plan_without_calling_executor(tmp_path):
    """Sicherheitskritisch (ADR-027): eine Ablehnung darf den Executor
    nicht erreichen - sonst waeren Sicherheitsstufe-2/3-unabhaengige
    Einschraenkungen (z. B. eine Intent-Whitelist) wirkungslos."""
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.executor.run = MagicMock(side_effect=AssertionError("Executor haette nicht laufen duerfen"))
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        def reject_all(steps):
            return [], "Anfrage abgelehnt: nicht erlaubt"

        runtime.submit("hallo", reply_callback, plan_filter=reject_all)
        _wait(done)

        assert replies == ["Anfrage abgelehnt: nicht erlaubt"]
        runtime.executor.run.assert_not_called()
    finally:
        runtime.stop()


def test_plan_filter_rejection_does_not_write_history(tmp_path):
    """Parität zu telegram_main.py::JarvisBridge.handle_message: eine
    Ablehnung wird nicht ins Gespraechsgedaechtnis geschrieben."""
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        def reject_all(steps):
            return [], "Anfrage abgelehnt: nicht erlaubt"

        runtime.submit("hallo", reply_callback, plan_filter=reject_all)
        _wait(done)

        assert replies == ["Anfrage abgelehnt: nicht erlaubt"]
        assert runtime.memory.get_history() == []
    finally:
        runtime.stop()


def test_messages_processed_sequentially_in_order(tmp_path):
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        order = []
        all_done = threading.Event()
        lock = threading.Lock()
        expected = 5

        def make_callback(i):
            def callback(text):
                with lock:
                    order.append(i)
                    if len(order) == expected:
                        all_done.set()

            return callback

        for i in range(expected):
            runtime.submit(f"nachricht {i}", make_callback(i))

        _wait(all_done)
        assert order == list(range(expected))
    finally:
        runtime.stop()


def test_concurrent_submits_from_multiple_threads_not_lost(tmp_path):
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        received = []
        lock = threading.Lock()
        all_done = threading.Event()
        expected = 6

        def callback(text):
            with lock:
                received.append(text)
                if len(received) == expected:
                    all_done.set()

        def submitter(i):
            runtime.submit(f"kanal-{i}", callback)

        threads = [threading.Thread(target=submitter, args=(i,)) for i in range(expected)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        _wait(all_done)
        assert len(received) == expected
        assert len(set(received)) == expected  # keine doppelten/verlorenen Antworten
    finally:
        runtime.stop()


def test_stop_cleanly_terminates_worker_thread(tmp_path):
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()

    runtime.stop()

    assert runtime._worker.is_alive() is False


def test_shutdown_hook_is_wired_to_runtime(tmp_path):
    # Der stop_runtime-Befehl bekommt beim Runtime-Aufbau den Hook injiziert
    # (Verdrahtungsschicht) - genau wie delegate/plan ihr Backend.
    import commands.shutdown as shutdown_commands

    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())

    assert shutdown_commands._shutdown_hook == runtime._request_shutdown


def test_request_shutdown_stops_worker(tmp_path):
    # _request_shutdown legt nur das Stop-Sentinel in die Queue (kein
    # Selbst-Join) -> der Worker beendet sich sauber in der naechsten Runde.
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    runtime.start()

    runtime._request_shutdown()
    runtime._worker.join(timeout=5.0)

    assert runtime._worker.is_alive() is False


def test_stufe2_commands_are_fail_closed(tmp_path):
    """Sicherheitsstufe-2/3-Commands duerfen ueber die Runtime nicht
    ausgefuehrt werden - _RuntimeSpeech.listen() liefert "" (fail
    closed), der Executor bricht die Bestaetigung ab (ADR-025)."""
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("mach etwas kritisches", reply_callback)
        _wait(done)

        # shutdown_pc erfordert eine exakte Bestaetigungsphrase (Stufe 3)
        # - _RuntimeSpeech.listen() liefert "" statt der Phrase, der
        # Executor lehnt ab statt eine Bestaetigung zu erfinden.
        assert "Abgebrochen" in replies[0]
    finally:
        runtime.stop()


def test_worker_does_not_die_on_unexpected_exception(tmp_path):
    """Ein unerwarteter Fehler bei der Verarbeitung einer Nachricht darf
    den Worker-Thread nicht beenden - nachfolgende Nachrichten muessen
    weiterhin verarbeitet werden (explizite Vorgabe, ADR-025)."""
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())

    original_process = runtime._process
    call_count = {"n": 0}

    def flaky_process(text, reply_callback, plan_filter=None, allow_async=False):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulierter Absturz")
        original_process(text, reply_callback, plan_filter, allow_async)

    runtime._process = flaky_process
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("erste nachricht (schlaegt fehl)", lambda t: None)
        runtime.submit("zweite nachricht", reply_callback)

        _wait(done)
        assert replies == ["Antwort auf: zweite nachricht"]
        assert runtime._worker.is_alive() is True
    finally:
        runtime.stop()


def test_broken_reply_callback_does_not_kill_worker(tmp_path):
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        def broken_callback(text):
            raise RuntimeError("Kanal bereits weg")

        done = threading.Event()
        replies = []

        def ok_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("erste nachricht", broken_callback)
        runtime.submit("zweite nachricht", ok_callback)

        _wait(done)
        assert replies == ["Antwort auf: zweite nachricht"]
        assert runtime._worker.is_alive() is True
    finally:
        runtime.stop()


# --- Audit-Fixes: Fehlerrobustheit (P1a/P1b) ----------------------------------


def test_worker_exception_still_sends_error_reply(tmp_path):
    """Audit-Fix P1a: wirft _process, MUSS der Kanal trotzdem eine Antwort
    bekommen - sonst wartet ein synchroner Kanal ewig auf reply_callback."""
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    runtime._process = MagicMock(side_effect=RuntimeError("boom"))
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("irgendwas", reply_callback)
        _wait(done)
        assert "unerwarteter Fehler" in replies[0]
        assert runtime._worker.is_alive() is True
    finally:
        runtime._process = JarvisRuntime._process.__get__(runtime)  # Original zurueck
        runtime.stop()


def test_console_handle_returns_on_timeout_instead_of_hanging(monkeypatch, capsys):
    """Audit-Fix P1a: bleibt reply_callback aus, darf die Konsole nicht endlos
    haengen - nach dem Sicherheitsnetz-Timeout kehrt _handle zurueck."""
    monkeypatch.setattr(jarvis_runtime, "_CONSOLE_REPLY_TIMEOUT", 0.05)
    runtime = MagicMock()
    runtime.submit.side_effect = lambda *a, **k: None  # ruft reply_callback NIE
    channel = ConsoleDummyChannel(runtime)

    channel._handle("hallo")  # darf nicht haengen

    assert "keine Antwort erhalten" in capsys.readouterr().out


def test_async_delegation_pushes_error_on_backend_exception(tmp_path):
    """Audit-Fix P1b: wirft der Hintergrundlauf, folgt nach der Quittung ein
    finaler Fehler-Push (nicht nur ein Log-Eintrag)."""
    backend = RuntimeFakeBackend(raises=True)
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        replies = []
        lock = threading.Lock()
        two = threading.Event()

        def cb(text):
            with lock:
                replies.append(text)
                if len(replies) == 2:
                    two.set()

        runtime.submit("analysiere jarvis: frage", cb, allow_async=True)
        assert two.wait(timeout=5.0)
        assert replies[0].startswith("Verstanden")       # Quittung
        assert "fehlgeschlagen" in replies[1]             # finaler Fehler-Push
    finally:
        runtime.stop()


def test_runtime_speech_is_fail_closed():
    speech = _RuntimeSpeech()
    assert speech.listen() == ""
    speech.say("sollte nicht crashen")  # darf keine Exception werfen


def test_console_dummy_channel_forwards_input_and_prints_reply(monkeypatch, capsys):
    runtime = MagicMock()

    def fake_submit(text, reply_callback):
        reply_callback(f"Echo: {text}")

    runtime.submit.side_effect = fake_submit
    channel = ConsoleDummyChannel(runtime)

    inputs = iter(["hallo", "exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    channel.run()

    out = capsys.readouterr().out
    assert "Echo: hallo" in out
    runtime.submit.assert_called_once()


def test_console_dummy_channel_ignores_empty_input(monkeypatch):
    runtime = MagicMock()
    channel = ConsoleDummyChannel(runtime)

    inputs = iter(["", "   ", "exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    channel.run()

    runtime.submit.assert_not_called()


# --- setup_logging: Konsolen-Handler nur bei vorhandener Konsole (ADR-028) --
# logging.basicConfig() selbst wird gemockt statt den echten Root-Logger zu
# mutieren - vermeidet globalen Testzustand/Seiteneffekte auf andere Tests.


def test_setup_logging_adds_stream_handler_when_stderr_available(tmp_path, monkeypatch):
    monkeypatch.setattr(jarvis_runtime.sys, "stderr", MagicMock())
    captured = {}
    monkeypatch.setattr(
        jarvis_runtime.logging, "basicConfig", lambda **kwargs: captured.update(kwargs)
    )
    config = _make_config(tmp_path)

    jarvis_runtime.setup_logging(config)

    handlers = captured["handlers"]
    try:
        assert len(handlers) == 2
        assert isinstance(handlers[0], logging.FileHandler)
        assert isinstance(handlers[1], logging.StreamHandler)
        assert not isinstance(handlers[1], logging.FileHandler)
    finally:
        for h in handlers:
            h.close()


def test_setup_logging_skips_stream_handler_when_stderr_is_none(tmp_path, monkeypatch):
    """ADR-028: pythonw.exe (Jarvis-Eigenstart ohne Konsolenfenster) setzt
    sys.stderr auf None - ein StreamHandler wuerde beim ersten Log-Aufruf
    abstuerzen. Der FileHandler bleibt in jedem Fall aktiv."""
    monkeypatch.setattr(jarvis_runtime.sys, "stderr", None)
    captured = {}
    monkeypatch.setattr(
        jarvis_runtime.logging, "basicConfig", lambda **kwargs: captured.update(kwargs)
    )
    config = _make_config(tmp_path)

    jarvis_runtime.setup_logging(config)

    handlers = captured["handlers"]
    try:
        assert len(handlers) == 1
        assert isinstance(handlers[0], logging.FileHandler)
    finally:
        for h in handlers:
            h.close()


def test_dampen_http_loggers_protects_token_by_setting_warning():
    """Sicherheit: httpx/httpcore loggen sonst den Telegram-Request-URL
    inkl. Bot-Token auf INFO - _dampen_http_loggers() hebt sie auf WARNING,
    damit der Token nie in Logdatei/Konsole landet."""
    loggers = [logging.getLogger("httpx"), logging.getLogger("httpcore")]
    orig = [lg.level for lg in loggers]
    try:
        for lg in loggers:
            lg.setLevel(logging.INFO)
        jarvis_runtime._dampen_http_loggers()
        assert all(lg.level == logging.WARNING for lg in loggers)
    finally:
        for lg, lvl in zip(loggers, orig):
            lg.setLevel(lvl)


# --- Asynchrone Repo-Analyse (ADR-035) -------------------------------------


class DelegatingFakeAI:
    """Wie FakeAI, erkennt aber 'analysiere ...' als delegate_analysis."""

    def get_plan(self, user_input, history):
        text = user_input.lower()
        if text.startswith("analysiere"):
            return Plan(
                intent="delegate_analysis",
                target="jarvis",
                parameters={"question": "frage"},
                raw_input=user_input,
                confidence=1.0,
            )
        if text.startswith("plane"):
            return Plan(intent="plan_next_step", raw_input=user_input, confidence=1.0)
        return Plan(intent="chat", raw_input=user_input, confidence=1.0)

    def answer(self, user_input, history, long_term_summary=""):
        return f"Antwort auf: {user_input}"


class RuntimeFakeBackend:
    """AgentBackend-Ersatz fuer die Runtime-Tests. Kann blockieren (block),
    auf den Cancel warten (wait_cancel) oder werfen (raises)."""

    name = "TestBackend"

    def __init__(self, *, result=None, block=None, raises=False, wait_cancel=False):
        self.result = result or AgentResult(text="Analyse fertig.", ok=True, duration_seconds=0.1)
        self.block = block
        self.raises = raises
        self.wait_cancel = wait_cancel
        self.calls = 0
        self.started = threading.Event()

    def analyze(self, repo, question, limits, cancel_event=None):
        self.calls += 1
        self.started.set()
        if self.raises:
            raise RuntimeError("backend boom")
        if self.wait_cancel and cancel_event is not None:
            cancel_event.wait(timeout=5.0)
            return AgentResult(text="", ok=False, duration_seconds=0.1, detail="abgebrochen")
        if self.block is not None:
            self.block.wait(timeout=5.0)
        return self.result


def _delegation_runtime(tmp_path: Path, backend) -> JarvisRuntime:
    """Runtime mit freigegebenem Repo 'jarvis' und injiziertem Backend.
    configure() laeuft NACH der Runtime-Konstruktion (die den echten Backend
    verdrahtet) und ueberschreibt ihn mit dem Fake."""
    repo = tmp_path / "jarvis"
    repo.mkdir(exist_ok=True)
    config = _make_config(tmp_path)
    config.agent_repos = [{"alias": "jarvis", "path": str(repo)}]
    runtime = JarvisRuntime(config, ai=DelegatingFakeAI())
    delegate_commands.configure(config, backend=backend)
    return runtime


def test_async_delegation_sends_quittung_then_push(tmp_path):
    backend = RuntimeFakeBackend(
        result=AgentResult(text="Ergebnis XY.", ok=True, duration_seconds=0.1)
    )
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        replies = []
        lock = threading.Lock()
        two = threading.Event()

        def cb(text):
            with lock:
                replies.append(text)
                if len(replies) == 2:
                    two.set()

        runtime.submit("analysiere jarvis: frage", cb, allow_async=True)
        assert two.wait(timeout=5.0)
        assert replies[0].startswith("Verstanden")  # sofortige Quittung
        assert "Ergebnis XY." in replies[1]          # spaeterer Ergebnis-Push
    finally:
        runtime.stop()


def test_message_worker_free_during_delegation(tmp_path):
    """Der Nachrichten-Worker darf waehrend einer laufenden Delegation NICHT
    blockieren - ein normaler Chat muss sofort beantwortet werden."""
    block = threading.Event()
    backend = RuntimeFakeBackend(block=block)
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        chat_done = threading.Event()
        replies = []
        lock = threading.Lock()

        def cb(text):
            with lock:
                replies.append(text)
            if "Antwort auf: hallo" in text:
                chat_done.set()

        runtime.submit("analysiere jarvis: frage", cb, allow_async=True)
        assert backend.started.wait(timeout=5.0)  # Delegation laeuft (blockiert)
        runtime.submit("hallo", cb)                # normaler Chat
        assert chat_done.wait(timeout=5.0)         # trotz laufender Delegation
    finally:
        block.set()
        runtime.stop()


def test_second_delegation_while_busy_is_rejected(tmp_path):
    block = threading.Event()
    backend = RuntimeFakeBackend(block=block)
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        replies = []
        lock = threading.Lock()
        busy = threading.Event()

        def cb(text):
            with lock:
                replies.append(text)
            if "läuft bereits" in text:
                busy.set()

        runtime.submit("analysiere jarvis: frage1", cb, allow_async=True)
        assert backend.started.wait(timeout=5.0)
        runtime.submit("analysiere jarvis: frage2", cb, allow_async=True)
        assert busy.wait(timeout=5.0)
        assert backend.calls == 1  # zweite Delegation erreicht das Backend nicht
    finally:
        block.set()
        runtime.stop()


def test_stop_cancels_running_delegation(tmp_path):
    backend = RuntimeFakeBackend(wait_cancel=True)
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()

    runtime.submit("analysiere jarvis: frage", lambda t: None, allow_async=True)
    assert backend.started.wait(timeout=5.0)

    runtime.stop()  # setzt Kill-Switch -> Backend kehrt zurueck -> Thread endet

    assert runtime._delegation_thread is not None
    assert runtime._delegation_thread.is_alive() is False


def test_delegation_without_allow_async_runs_synchronously(tmp_path):
    """Regressionsanker (ADR-035 Entscheidung 5): ohne allow_async laeuft die
    Analyse synchron im Nachrichten-Worker - genau eine Antwort, keine
    separate Quittung."""
    backend = RuntimeFakeBackend(
        result=AgentResult(text="Sync-Ergebnis.", ok=True, duration_seconds=0.1)
    )
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        replies = []
        done = threading.Event()

        def cb(text):
            replies.append(text)
            done.set()

        runtime.submit("analysiere jarvis: frage", cb)  # allow_async=False (Default)
        assert done.wait(timeout=5.0)
        assert len(replies) == 1
        assert "Sync-Ergebnis." in replies[0]
    finally:
        runtime.stop()


def test_busy_flag_reset_after_background_exception(tmp_path):
    """Wirft der Hintergrundlauf, muss der Busy-Slot im finally freigegeben
    werden - eine nachfolgende Delegation darf nicht dauerhaft 'busy' sein."""
    backend = RuntimeFakeBackend(raises=True)
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        replies = []
        lock = threading.Lock()

        def cb(text):
            with lock:
                replies.append(text)

        runtime.submit("analysiere jarvis: frage1", cb, allow_async=True)
        assert backend.started.wait(timeout=5.0)
        # Erster Hintergrund-Thread (wirft) sauber abwarten.
        runtime._delegation_thread.join(timeout=5.0)

        backend.started.clear()
        runtime.submit("analysiere jarvis: frage2", cb, allow_async=True)
        # Zweite Delegation wird angenommen und erreicht das Backend erneut.
        assert backend.started.wait(timeout=5.0)
        deadline = time.time() + 5.0
        while backend.calls < 2 and time.time() < deadline:
            time.sleep(0.02)
        assert backend.calls == 2
        assert not any("läuft bereits" in r for r in replies)
    finally:
        runtime.stop()


def test_async_delegation_writes_consistent_history(tmp_path):
    backend = RuntimeFakeBackend(
        result=AgentResult(text="Ergebnis.", ok=True, duration_seconds=0.1)
    )
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        replies = []
        lock = threading.Lock()
        two = threading.Event()

        def cb(text):
            with lock:
                replies.append(text)
                if len(replies) == 2:
                    two.set()

        runtime.submit("analysiere jarvis: frage", cb, allow_async=True)
        assert two.wait(timeout=5.0)

        history = runtime.memory.get_history()
        assert [m.role for m in history] == ["user", "assistant"]
        assert history[0].content == "analysiere jarvis: frage"
        assert "Ergebnis." in history[1].content
        # Die transiente Quittung wird NICHT persistiert.
        assert all("Verstanden" not in m.content for m in history)
    finally:
        runtime.stop()


def test_async_plan_next_step_reuses_the_async_path(tmp_path):
    """Ein ZWEITER long_running-Command (plan_next_step) nutzt denselben
    Async-Pfad wie delegate_analysis - Quittung + Push, ohne Runtime-Aenderung."""
    import commands.plan as plan_commands

    backend = RuntimeFakeBackend(
        result=AgentResult(text="# Titel\n## Empfehlung\nScheibe X.", ok=True, duration_seconds=0.1)
    )
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=DelegatingFakeAI())
    plan_commands.configure(config, backend=backend)  # echten Backend durch Fake ersetzen
    runtime.start()
    try:
        replies = []
        lock = threading.Lock()
        two = threading.Event()

        def cb(text):
            with lock:
                replies.append(text)
                if len(replies) == 2:
                    two.set()

        runtime.submit("plane den nächsten schritt", cb, allow_async=True)
        assert two.wait(timeout=5.0)
        assert replies[0].startswith("Verstanden")   # generische Quittung
        assert "Scheibe X." in replies[1]             # Push mit dem Vorschlag
    finally:
        runtime.stop()


def test_async_and_sync_history_not_lost_under_concurrency(tmp_path):
    """RLock im MemoryStore: Delegations-Thread und Nachrichten-Worker
    schreiben gleichzeitig History - kein Eintrag darf verloren gehen."""
    block = threading.Event()
    backend = RuntimeFakeBackend(
        block=block, result=AgentResult(text="Analyse.", ok=True, duration_seconds=0.1)
    )
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        replies = []
        lock = threading.Lock()
        push = threading.Event()
        chat = threading.Event()

        def cb(text):
            with lock:
                replies.append(text)
            if "Analyse." in text:
                push.set()
            if "Antwort auf: hallo" in text:
                chat.set()

        runtime.submit("analysiere jarvis: frage", cb, allow_async=True)
        assert backend.started.wait(timeout=5.0)  # Delegation laeuft (blockiert)
        runtime.submit("hallo", cb)                # paralleler Chat schreibt History
        assert chat.wait(timeout=5.0)
        block.set()                                # Delegation abschliessen
        assert push.wait(timeout=5.0)

        contents = [m.content for m in runtime.memory.get_history()]
        assert len(contents) == 4  # 2x Chat + 2x Delegation, nichts verloren
        assert "analysiere jarvis: frage" in contents
        assert "hallo" in contents
    finally:
        block.set()
        runtime.stop()
