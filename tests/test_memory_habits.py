"""Tests fuer memory/habits.py (ADR-053) - Zaehlwerte ohne Inhalte,
fail-safe Erhebung, Vermutungs-Kandidaten."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from memory.habits import HabitStats


_MONDAY_7 = datetime(2026, 7, 13, 7, 30)  # Montag (weekday 0), 07:xx


def test_record_counts_into_weekday_hour_bucket(tmp_path: Path):
    stats = HabitStats(tmp_path)
    stats.record("get_news", when=_MONDAY_7)
    stats.record("get_news", when=_MONDAY_7)

    data = json.loads((tmp_path / "habit_stats.json").read_text(encoding="utf-8"))
    assert data["counts"]["get_news"]["0-07"] == 2
    # NUR Zaehlwerte in der Datei - keine Inhalte, keine Targets:
    assert set(data.keys()) == {"counts", "since"}


def test_ignored_intents_are_never_collected(tmp_path: Path):
    """Datenminimierung: was nie Vermutung werden darf, wird nicht erhoben."""
    stats = HabitStats(tmp_path)
    for intent in ("chat", "stop_runtime", "restart_runtime", "shutdown_pc", ""):
        stats.record(intent, when=_MONDAY_7)

    assert not (tmp_path / "habit_stats.json").exists() or json.loads(
        (tmp_path / "habit_stats.json").read_text(encoding="utf-8")
    )["counts"] == {}


def test_suspects_threshold_and_sorting(tmp_path: Path):
    stats = HabitStats(tmp_path)
    for _ in range(4):
        stats.record("get_news", when=_MONDAY_7)
    for _ in range(3):
        stats.record("get_weather", when=datetime(2026, 7, 14, 8, 5))  # Di 08
    stats.record("search_web", when=_MONDAY_7)  # nur 1x -> kein Kandidat

    suspects = stats.suspects(min_count=3)

    assert [s["intent"] for s in suspects] == ["get_news", "get_weather"]
    assert suspects[0] == {"intent": "get_news", "weekday": 0, "hour": 7, "count": 4}
    assert stats.suspects(min_count=5) == []


def test_record_is_failsafe_when_write_breaks(tmp_path: Path, monkeypatch):
    """Die Statistik darf die Nachrichten-Verarbeitung NIE stoeren."""
    import memory.habits as habits_module

    stats = HabitStats(tmp_path)
    monkeypatch.setattr(
        habits_module, "write_json_atomic",
        lambda *a, **k: (_ for _ in ()).throw(OSError("Platte voll")),
    )
    stats.record("get_news", when=_MONDAY_7)  # darf nicht werfen


def test_runtime_records_habit_after_planning(tmp_path: Path, monkeypatch):
    """Integration: der Runtime-Hook zaehlt den geplanten Intent."""
    import commands.web as web_commands
    from core.web_search import SearchResult
    from tests.test_jarvis_runtime import FakeAI, _make_config
    from jarvis_runtime import JarvisRuntime

    monkeypatch.setattr(
        web_commands, "_searcher",
        lambda query, max_results, timeout_seconds: [
            SearchResult(title="t", url="https://example.com", snippet="s")
        ],
    )
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    replies = []
    runtime._process_inner("recherchiere mal was", replies.append)  # -> search_web

    suspects_file = tmp_path / "memory_data" / "habit_stats.json"
    data = json.loads(suspects_file.read_text(encoding="utf-8"))
    assert sum(data["counts"].get("search_web", {}).values()) == 1
    # chat-Nachrichten werden NICHT erhoben:
    runtime._process_inner("hallo", replies.append)
    data = json.loads(suspects_file.read_text(encoding="utf-8"))
    assert "chat" not in data["counts"]
