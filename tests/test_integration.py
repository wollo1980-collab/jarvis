"""End-to-End-Smoke-Test der kompletten Pipeline (Planner -> Executor
-> Memory), wie sie main.py verdrahtet - mit einer gefälschten
AIEngine statt einem echten OpenAI-Aufruf. Deckt die im Handbook
geforderten Smoke-Test-Fälle ab:
- "Jarvis antwortet auf 'Jarvis, wie spät ist es?'"
- "Jarvis erinnert sich an frühere Aussagen im Gespräch"
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from core.models import Message, Plan
from core.planner import Planner
from core.speech import SpeechEngine
from executor.executor import Executor
from memory.store import JsonMemoryStore


class FakeAI:
    """Ersetzt AIEngine 1:1 (gleiche öffentliche Methoden) - kein
    echter API-Key, kein Netzwerk nötig."""

    def get_plan(self, user_input: str, history: list[Message]) -> Plan:
        if "excel" in user_input.lower():
            return Plan(intent="open_program", target="excel", raw_input=user_input, confidence=1.0)
        return Plan(intent="chat", raw_input=user_input, confidence=1.0)

    def answer(self, user_input: str, history: list[Message], long_term_summary: str = "") -> str:
        if "wie spät" in user_input.lower():
            return "Ich habe keinen Zugriff auf die Uhrzeit, aber ich kann das gerne nachrüsten."
        if "weißt du über mich" in user_input.lower() and long_term_summary:
            return f"Ich weiß noch: {long_term_summary}"
        if history:
            letzte_user_nachricht = next(
                (m.content for m in reversed(history) if m.role == "user"), None
            )
            return f"Du hattest vorhin gefragt: {letzte_user_nachricht!r}"
        return "Alles klar."


def _run_turn(
    user_input: str,
    planner: Planner,
    executor: Executor,
    memory: JsonMemoryStore,
    long_term_summary: str = "",
) -> str:
    history = memory.get_history(limit=20)
    steps = planner.plan(user_input, history)
    report = executor.run(steps, history, long_term_summary)
    response_text = "\n".join(report.summary_lines()) or "Alles klar."

    memory.append_history(Message(role="user", content=user_input))
    memory.append_history(Message(role="assistant", content=response_text))
    return response_text


def test_end_to_end_chat_and_memory(tmp_path: Path):
    ai = FakeAI()
    planner = Planner(ai)
    speech = MagicMock(spec=SpeechEngine)
    executor = Executor(speech, ai)
    memory = JsonMemoryStore(tmp_path, max_history_entries=20)

    # Smoke Test aus dem Handbook: Jarvis muss auf eine einfache Frage antworten.
    response_1 = _run_turn("Jarvis, wie spät ist es?", planner, executor, memory)
    assert "Uhrzeit" in response_1

    # Gedächtnis-Test: die zweite Antwort muss sich auf die erste Aussage beziehen.
    response_2 = _run_turn("erinnerst du dich an meine letzte Frage?", planner, executor, memory)
    assert "wie spät ist es" in response_2

    history = memory.get_history()
    assert len(history) == 4  # 2x user + 2x assistant


def test_end_to_end_tool_execution(tmp_path: Path):
    ai = FakeAI()
    planner = Planner(ai)
    speech = MagicMock(spec=SpeechEngine)
    executor = Executor(speech, ai)
    memory = JsonMemoryStore(tmp_path, max_history_entries=20)

    with patch("commands.system.shutil.which", return_value="/usr/bin/excel"), patch(
        "commands.system.subprocess.Popen"
    ):
        response = _run_turn("öffne excel", planner, executor, memory)

    assert response.startswith("✓")
    assert "geöffnet" in response


def test_end_to_end_remembers_and_recalls_long_term_fact(tmp_path: Path):
    """v0.4 (ADR-009): remember_fact merkt einen Fakt dauerhaft, eine
    spätere Chat-Antwort kann sich darauf beziehen - end-to-end über
    Planner -> Executor -> commands.memory -> LongTermMemory."""
    import commands.memory as memory_commands
    from memory.long_term import LongTermMemory

    memory_dir = tmp_path / "memory_data"
    memory_dir.mkdir()
    memory_commands.configure(memory_dir)
    long_term = LongTermMemory(memory_dir)

    class RememberingFakeAI(FakeAI):
        def get_plan(self, user_input: str, history: list[Message]) -> Plan:
            if user_input.lower().startswith("merk dir"):
                fact = user_input.split(",", 1)[-1].strip()
                return Plan(
                    intent="remember_fact",
                    target=fact,
                    parameters={"category": "gewohnheit"},
                    raw_input=user_input,
                    confidence=1.0,
                )
            return super().get_plan(user_input, history)

    ai = RememberingFakeAI()
    planner = Planner(ai)
    speech = MagicMock(spec=SpeechEngine)
    executor = Executor(speech, ai)
    memory = JsonMemoryStore(memory_dir, max_history_entries=20)

    remember_response = _run_turn(
        "merk dir, dass ich montags Reports mache", planner, executor, memory
    )
    assert "montags Reports" in remember_response

    recall_response = _run_turn(
        "was weißt du über mich?", planner, executor, memory, long_term.summary_text()
    )
    assert "montags Reports" in recall_response