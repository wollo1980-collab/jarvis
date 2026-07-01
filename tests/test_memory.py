"""Tests für memory/store.py - JsonMemoryStore arbeitet auf tmp_path,
keine Berührung des echten memory_data-Ordners."""
from __future__ import annotations

from pathlib import Path

from core.models import Message
from memory.store import JsonMemoryStore


def test_creates_default_files(tmp_path: Path):
    JsonMemoryStore(tmp_path)
    assert (tmp_path / "preferences.json").exists()
    assert (tmp_path / "history.json").exists()
    assert (tmp_path / "context.json").exists()


def test_history_roundtrip(tmp_path: Path):
    store = JsonMemoryStore(tmp_path, max_history_entries=200)
    store.append_history(Message(role="user", content="hallo"))
    store.append_history(Message(role="assistant", content="hi"))

    history = store.get_history()
    assert [m.content for m in history] == ["hallo", "hi"]


def test_history_limit_enforced(tmp_path: Path):
    store = JsonMemoryStore(tmp_path, max_history_entries=3)
    for i in range(5):
        store.append_history(Message(role="user", content=str(i)))

    history = store.get_history()
    assert [m.content for m in history] == ["2", "3", "4"]


def test_history_limit_applies_after_reload(tmp_path: Path):
    store_a = JsonMemoryStore(tmp_path, max_history_entries=200)
    store_a.append_history(Message(role="user", content="alt"))

    store_b = JsonMemoryStore(tmp_path, max_history_entries=200)
    history = store_b.get_history()
    assert [m.content for m in history] == ["alt"]


def test_preferences_roundtrip(tmp_path: Path):
    store = JsonMemoryStore(tmp_path)
    store.set("name", "Wolfgang")
    assert store.get("name") == "Wolfgang"


def test_get_history_with_limit(tmp_path: Path):
    store = JsonMemoryStore(tmp_path)
    for i in range(10):
        store.append_history(Message(role="user", content=str(i)))

    history = store.get_history(limit=3)
    assert [m.content for m in history] == ["7", "8", "9"]
