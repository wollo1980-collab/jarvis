"""Tests fuer memory/episodic.py - das einsehbare Ereignis-Tagebuch (Gedaechtnis
Stufe 1). Lokal, append-only JSONL je Tag, Secrets redigiert, fail-safe."""
from __future__ import annotations

from datetime import date, datetime

from core.redaction import REDACTED
from memory.episodic import EpisodicMemory


def test_record_and_read_back_for_day(tmp_path):
    em = EpisodicMemory(tmp_path)
    day = date(2026, 7, 12)
    em.record(user_input="wie wird das wetter?", intents=["get_weather"],
              response="Heute sonnig.", source="telegram",
              ts=datetime(2026, 7, 12, 8, 0))
    em.record(user_input="danke", intents=["chat"], response="Gern, Sir.",
              ts=datetime(2026, 7, 12, 8, 1))

    eps = em.for_day(day)

    assert len(eps) == 2
    assert eps[0]["user_input"] == "wie wird das wetter?"
    assert eps[0]["intents"] == ["get_weather"]
    assert eps[0]["source"] == "telegram"
    assert eps[0]["response"] == "Heute sonnig."
    assert eps[0]["ts"].startswith("2026-07-12T08:00")
    assert eps[1]["intents"] == ["chat"]


def test_redacts_secrets_before_writing(tmp_path):
    em = EpisodicMemory(tmp_path)
    em.record(user_input="mein passwort ist supergeheim123456", intents=["chat"],
              response="Notiert.", ts=datetime(2026, 7, 12, 9, 0))

    ep = em.for_day(date(2026, 7, 12))[0]

    assert "supergeheim123456" not in ep["user_input"]
    assert REDACTED in ep["user_input"]
    # Das rohe Secret darf auch nicht auf Platte stehen:
    raw = (tmp_path / "episodes" / "2026-07-12.jsonl").read_text(encoding="utf-8")
    assert "supergeheim123456" not in raw


def test_for_day_missing_returns_empty(tmp_path):
    assert EpisodicMemory(tmp_path).for_day(date(2020, 1, 1)) == []


def test_recent_across_days_returns_youngest(tmp_path):
    em = EpisodicMemory(tmp_path)
    em.record(user_input="gestern", intents=["chat"], response="a",
              ts=datetime(2026, 7, 11, 10, 0))
    em.record(user_input="heute-1", intents=["chat"], response="b",
              ts=datetime(2026, 7, 12, 10, 0))
    em.record(user_input="heute-2", intents=["chat"], response="c",
              ts=datetime(2026, 7, 12, 11, 0))

    recent = em.recent(limit=2)

    assert [e["user_input"] for e in recent] == ["heute-1", "heute-2"]  # juengste 2, Reihenfolge alt->neu


def test_record_is_failsafe_on_bad_path(tmp_path):
    # base_dir ist eine DATEI -> mkdir(episodes) scheitert; record darf NICHT werfen.
    bad = tmp_path / "not_a_dir"
    bad.write_text("x", encoding="utf-8")
    em = EpisodicMemory(bad)

    em.record(user_input="x", intents=["chat"], response="y")  # kein Absturz

    assert em.for_day(date.today()) == []  # nichts geschrieben, aber sauber
