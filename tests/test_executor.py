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


# --- optionaler preview()-Hook (v0.7 Phase 4, ADR-023) ---------------------
#
# WICHTIG: MagicMock() ohne spec= erzeugt automatisch JEDES angefragte
# Attribut (auch .preview) - das wuerde den Rueckwaertskompatibilitaets-
# Test unbrauchbar machen (getattr(command, "preview", None) faende
# faelschlich immer ein aufrufbares Mock-Objekt). spec=[...] schliesst
# .preview bewusst aus, damit getattr(...) wirklich None liefert, wenn
# das Command (wie alle bisherigen Commands) preview() nicht kennt.


def test_executor_confirmation_unchanged_when_command_has_no_preview():
    """Rueckwaertskompatibilitaet: ein Command ohne preview() zeigt exakt
    denselben Bestaetigungstext wie vor dem preview()-Hook."""
    speech = MagicMock()
    speech.listen.return_value = "ja"
    ai = MagicMock()
    command = MagicMock(
        spec=["requires_confirmation", "confirmation_phrase", "execute"],
        requires_confirmation=True,
        confirmation_phrase=None,
    )
    command.execute.return_value = Result(status=Status.SUCCESS, message="ok")
    tool_manager = MagicMock(resolve=MagicMock(return_value=command))
    executor = Executor(speech, ai, tool_manager=tool_manager)

    report = executor.run([Plan(intent="x", raw_input="tu etwas kritisches")])

    speech.say.assert_called_once_with("Ich würde jetzt ausführen: 'tu etwas kritisches'. Bestätigen?")
    assert report.all_ok


def test_executor_stufe3_confirmation_unchanged_when_command_has_no_preview():
    speech = MagicMock()
    speech.listen.return_value = "HERUNTERFAHREN"
    ai = MagicMock()
    command = MagicMock(
        spec=["requires_confirmation", "confirmation_phrase", "execute"],
        requires_confirmation=True,
        confirmation_phrase="HERUNTERFAHREN",
    )
    command.execute.return_value = Result(status=Status.SUCCESS, message="ok")
    tool_manager = MagicMock(resolve=MagicMock(return_value=command))
    executor = Executor(speech, ai, tool_manager=tool_manager)

    executor.run([Plan(intent="shutdown_pc", raw_input="fahr den pc runter")])

    speech.say.assert_called_once_with(
        "Ich würde jetzt ausführen: 'fahr den pc runter'. Das ist eine kritische "
        "Aktion (Sicherheitsstufe 3). Bitte tippe zur Bestätigung genau: HERUNTERFAHREN"
    )


def test_executor_shows_preview_text_before_stufe2_confirmation():
    speech = MagicMock()
    speech.listen.return_value = "ja"
    ai = MagicMock()
    command = MagicMock(
        spec=["requires_confirmation", "confirmation_phrase", "execute", "preview"],
        requires_confirmation=True,
        confirmation_phrase=None,
    )
    command.preview.return_value = "Ich würde 10 Dateien mit 2.0 GB löschen."
    command.execute.return_value = Result(status=Status.SUCCESS, message="ok")
    tool_manager = MagicMock(resolve=MagicMock(return_value=command))
    executor = Executor(speech, ai, tool_manager=tool_manager)

    executor.run([Plan(intent="clean_temp_files", raw_input="bereinige temp")])

    speech.say.assert_called_once_with(
        "Ich würde jetzt ausführen: 'bereinige temp'. Ich würde 10 Dateien mit "
        "2.0 GB löschen. Bestätigen?"
    )
    command.preview.assert_called_once()


def test_executor_shows_preview_text_before_stufe3_confirmation():
    speech = MagicMock()
    speech.listen.return_value = "BEREINIGEN"
    ai = MagicMock()
    command = MagicMock(
        spec=["requires_confirmation", "confirmation_phrase", "execute", "preview"],
        requires_confirmation=True,
        confirmation_phrase="BEREINIGEN",
    )
    command.preview.return_value = "Ich würde 10 Dateien mit 2.0 GB löschen."
    command.execute.return_value = Result(status=Status.SUCCESS, message="ok")
    tool_manager = MagicMock(resolve=MagicMock(return_value=command))
    executor = Executor(speech, ai, tool_manager=tool_manager)

    report = executor.run([Plan(intent="clean_temp_files", raw_input="bereinige temp")])

    say_text = speech.say.call_args.args[0]
    assert "Ich würde 10 Dateien mit 2.0 GB löschen." in say_text
    assert "BEREINIGEN" in say_text
    assert report.all_ok


def test_executor_falls_back_to_old_text_when_preview_returns_none():
    speech = MagicMock()
    speech.listen.return_value = "ja"
    ai = MagicMock()
    command = MagicMock(
        spec=["requires_confirmation", "confirmation_phrase", "execute", "preview"],
        requires_confirmation=True,
        confirmation_phrase=None,
    )
    command.preview.return_value = None
    command.execute.return_value = Result(status=Status.SUCCESS, message="ok")
    tool_manager = MagicMock(resolve=MagicMock(return_value=command))
    executor = Executor(speech, ai, tool_manager=tool_manager)

    executor.run([Plan(intent="x", raw_input="tu etwas")])

    speech.say.assert_called_once_with("Ich würde jetzt ausführen: 'tu etwas'. Bestätigen?")


def test_executor_calls_preview_before_execute_and_execute_runs_independently():
    """execute() darf nicht von preview() abhaengen - beide werden vom
    Executor unabhaengig aufgerufen (ADR-023: execute() scannt immer
    frisch, verlaesst sich nie auf preview())."""
    speech = MagicMock()
    speech.listen.return_value = "BEREINIGEN"
    ai = MagicMock()
    call_order = []
    command = MagicMock(
        spec=["requires_confirmation", "confirmation_phrase", "execute", "preview"],
        requires_confirmation=True,
        confirmation_phrase="BEREINIGEN",
    )
    command.preview.side_effect = lambda plan: call_order.append("preview") or "Vorschau-Text."
    command.execute.side_effect = lambda plan: call_order.append("execute") or Result(
        status=Status.SUCCESS, message="ok"
    )
    tool_manager = MagicMock(resolve=MagicMock(return_value=command))
    executor = Executor(speech, ai, tool_manager=tool_manager)

    executor.run([Plan(intent="clean_temp_files", raw_input="bereinige temp")])

    assert call_order == ["preview", "execute"]
    command.preview.assert_called_once()
    command.execute.assert_called_once()
