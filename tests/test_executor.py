"""Tests für executor/executor.py - Tool Manager, Speech und AI
gemockt, es wird nur die Ausführungslogik (Bestätigung, Abbruch bei
Fehler, Chat-Fallback) geprüft."""
from __future__ import annotations

from unittest.mock import MagicMock

from core.models import Plan, Result, Status
from executor.executor import Executor


def test_executor_runs_chat_step_via_ai_answer():
    speech = MagicMock()
    ai = MagicMock()
    ai.answer.return_value = "Hallo!"
    tool_manager = MagicMock(resolve=MagicMock(return_value=None))
    executor = Executor(speech, ai, tool_manager=tool_manager)

    report = executor.run([Plan(intent="chat", raw_input="hallo")])

    assert report.all_ok
    assert report.results[0].message == "Hallo!"
    assert report.summary_lines() == ["Hallo!"]  # kein Symbol bei Chat-Antworten


def test_executor_passes_history_to_ai_answer():
    from core.models import Message

    speech = MagicMock()
    ai = MagicMock()
    ai.answer.return_value = "..."
    tool_manager = MagicMock(resolve=MagicMock(return_value=None))
    executor = Executor(speech, ai, tool_manager=tool_manager)
    history = [Message(role="user", content="vorher")]

    executor.run([Plan(intent="chat", raw_input="hallo")], history)

    ai.answer.assert_called_once_with("hallo", history, "")


def test_executor_passes_long_term_summary_to_ai_answer():
    """v0.4 (ADR-009): Langzeitgedächtnis-Zusammenfassung muss bei
    Chat-Schritten an ai.answer() durchgereicht werden."""
    speech = MagicMock()
    ai = MagicMock()
    ai.answer.return_value = "..."
    tool_manager = MagicMock(resolve=MagicMock(return_value=None))
    executor = Executor(speech, ai, tool_manager=tool_manager)

    executor.run(
        [Plan(intent="chat", raw_input="hallo")],
        history=[],
        long_term_summary="- (projekt) arbeitet an Jarvis",
    )

    ai.answer.assert_called_once_with("hallo", [], "- (projekt) arbeitet an Jarvis")


def test_executor_runs_tool_success():
    speech = MagicMock()
    ai = MagicMock()
    command = MagicMock(requires_confirmation=False)
    command.execute.return_value = Result(status=Status.SUCCESS, message="excel wurde geöffnet.")
    tool_manager = MagicMock(resolve=MagicMock(return_value=command))
    executor = Executor(speech, ai, tool_manager=tool_manager)

    report = executor.run([Plan(intent="open_program", target="excel", raw_input="öffne excel")])

    assert report.all_ok
    command.execute.assert_called_once()
    assert report.summary_lines() == ["✓ excel wurde geöffnet."]


def test_executor_asks_for_confirmation_before_critical_action():
    """Stufe 2 (kein confirmation_phrase gesetzt): einfaches Ja/Nein reicht."""
    speech = MagicMock()
    speech.listen.return_value = "ja"
    ai = MagicMock()
    command = MagicMock(requires_confirmation=True, confirmation_phrase=None)
    command.execute.return_value = Result(
        status=Status.SUCCESS, message="PC wird heruntergefahren."
    )
    tool_manager = MagicMock(resolve=MagicMock(return_value=command))
    executor = Executor(speech, ai, tool_manager=tool_manager)

    report = executor.run([Plan(intent="shutdown_pc", raw_input="fahr den pc runter")])

    speech.say.assert_called()
    speech.listen.assert_called()
    command.execute.assert_called_once()
    assert report.all_ok


def test_executor_aborts_when_confirmation_denied():
    speech = MagicMock()
    speech.listen.return_value = "nein"
    ai = MagicMock()
    command = MagicMock(requires_confirmation=True, confirmation_phrase=None)
    tool_manager = MagicMock(resolve=MagicMock(return_value=command))
    executor = Executor(speech, ai, tool_manager=tool_manager)

    report = executor.run([Plan(intent="shutdown_pc", raw_input="fahr den pc runter")])

    command.execute.assert_not_called()
    assert not report.all_ok
    assert report.results[0].status == Status.NEEDS_CLARIFICATION


def test_executor_stufe3_requires_exact_phrase_not_just_ja():
    """Lesson Learned 2026-07-01: ein einfaches 'ja' darf bei einer
    Stufe-3-Aktion (confirmation_phrase gesetzt) NICHT reichen."""
    speech = MagicMock()
    speech.listen.return_value = "ja"  # bewusst NUR "ja", keine Phrase
    ai = MagicMock()
    command = MagicMock(requires_confirmation=True, confirmation_phrase="HERUNTERFAHREN")
    tool_manager = MagicMock(resolve=MagicMock(return_value=command))
    executor = Executor(speech, ai, tool_manager=tool_manager)

    report = executor.run([Plan(intent="shutdown_pc", raw_input="Ende")])

    command.execute.assert_not_called()
    assert not report.all_ok
    assert report.results[0].status == Status.NEEDS_CLARIFICATION


def test_executor_stufe3_proceeds_with_exact_phrase():
    speech = MagicMock()
    speech.listen.return_value = "HERUNTERFAHREN"
    ai = MagicMock()
    command = MagicMock(requires_confirmation=True, confirmation_phrase="HERUNTERFAHREN")
    command.execute.return_value = Result(
        status=Status.SUCCESS, message="PC wird heruntergefahren."
    )
    tool_manager = MagicMock(resolve=MagicMock(return_value=command))
    executor = Executor(speech, ai, tool_manager=tool_manager)

    report = executor.run([Plan(intent="shutdown_pc", raw_input="fahr den pc wirklich runter")])

    command.execute.assert_called_once()
    assert report.all_ok


def test_executor_stops_after_failure_in_multi_step_plan():
    speech = MagicMock()
    ai = MagicMock()
    failing = MagicMock(requires_confirmation=False)
    failing.execute.return_value = Result(status=Status.FAILED, message="Fehler.")
    never_called = MagicMock(requires_confirmation=False)
    tool_manager = MagicMock(resolve=MagicMock(side_effect=[failing, never_called]))
    executor = Executor(speech, ai, tool_manager=tool_manager)

    steps = [Plan(intent="a", raw_input="a"), Plan(intent="b", raw_input="b")]
    report = executor.run(steps)

    assert not report.all_ok
    never_called.execute.assert_not_called()
    assert len(report.results) == 1


def test_executor_catches_command_exceptions():
    speech = MagicMock()
    ai = MagicMock()
    command = MagicMock(requires_confirmation=False)
    command.execute.side_effect = RuntimeError("boom")
    tool_manager = MagicMock(resolve=MagicMock(return_value=command))
    executor = Executor(speech, ai, tool_manager=tool_manager)

    report = executor.run([Plan(intent="broken", raw_input="tu etwas")])

    assert not report.all_ok
    assert report.results[0].status == Status.FAILED
