"""Tests für memory/store.py - JsonMemoryStore arbeitet auf tmp_path,
keine Berührung des echten memory_data-Ordners."""
from __future__ import annotations

import threading
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
    store.set("name", "Alex")
    assert store.get("name") == "Alex"


def test_get_history_with_limit(tmp_path: Path):
    store = JsonMemoryStore(tmp_path)
    for i in range(10):
        store.append_history(Message(role="user", content=str(i)))

    history = store.get_history(limit=3)
    assert [m.content for m in history] == ["7", "8", "9"]


def test_corrupt_history_is_preserved_not_silently_deleted(tmp_path: Path):
    """Audit-Fix P2b: kaputtes history.json wird zur Seite gelegt (bewahrt) und
    auf den leeren Default zurueckgefallen - nicht unbemerkt geloescht."""
    store = JsonMemoryStore(tmp_path)
    (tmp_path / "history.json").write_text("{ kaputt ", encoding="utf-8")

    history = store.get_history()

    assert history == []
    backups = list(tmp_path.glob("history.json.corrupt-*"))
    assert len(backups) == 1
    assert "kaputt" in backups[0].read_text(encoding="utf-8")


def test_parallel_append_history_loses_no_entries(tmp_path: Path):
    """ADR-035: seit der asynchronen Repo-Analyse schreiben Delegations-Thread
    und Nachrichten-Worker gleichzeitig History. Das RLock im Store muss die
    read-modify-write-Zugriffe serialisieren - kein Eintrag darf verloren
    gehen."""
    store = JsonMemoryStore(tmp_path, max_history_entries=1000)
    threads_count = 8
    per_thread = 25
    start = threading.Event()

    def worker(tid: int) -> None:
        start.wait()
        for i in range(per_thread):
            store.append_history(Message(role="user", content=f"{tid}-{i}"))

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(threads_count)]
    for t in threads:
        t.start()
    start.set()
    for t in threads:
        t.join()

    history = store.get_history()
    assert len(history) == threads_count * per_thread
    assert len({m.content for m in history}) == threads_count * per_thread
