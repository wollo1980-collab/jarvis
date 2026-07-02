"""Tests für jarvis_runtime.py - JarvisRuntime (Queue+Worker-Thread),
_RuntimeSpeech (fail-closed) und ConsoleDummyChannel (ADR-025). AIEngine
gemockt (FakeAI, gleiches Muster wie tests/test_integration.py), kein
echter API-Key/Netzwerk nötig."""
from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

from core.config import Config
from core.models import Plan
from jarvis_runtime import ConsoleDummyChannel, JarvisRuntime, _RuntimeSpeech


class FakeAI:
    """Gleiches Muster wie tests/test_integration.py::FakeAI."""

    def get_plan(self, user_input, history):
        if "kritisch" in user_input.lower():
            return Plan(intent="shutdown_pc", raw_input=user_input, confidence=1.0)
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

    def flaky_process(text, reply_callback, plan_filter=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulierter Absturz")
        original_process(text, reply_callback, plan_filter)

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
