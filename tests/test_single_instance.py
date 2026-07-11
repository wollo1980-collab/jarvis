"""Tests für core/single_instance.py - SingleInstanceLock (ADR-026).
psutil gemockt (gleiches Muster wie tests/test_commands_monitor.py),
kein echter zweiter Prozess nötig."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

import core.single_instance as single_instance
from core.single_instance import InstanceAlreadyRunningError, SingleInstanceLock


class _FakeProcess:
    def __init__(self, cmdline):
        self._cmdline = cmdline

    def cmdline(self):
        return self._cmdline


def _make_memory_dir(tmp_path: Path) -> Path:
    d = tmp_path / "memory_data"
    d.mkdir(parents=True)
    return d


def _read_locked_content(lock: SingleInstanceLock) -> dict:
    """Liest den Lock-Inhalt ueber das eigene, bereits offene Datei-
    Handle - ein frischer Path.read_text() waere durch msvcrt.locking()
    blockiert (PermissionError), auch innerhalb desselben Prozesses."""
    lock._fh.seek(0)
    return json.loads(lock._fh.read())


def test_acquire_creates_lock_file_with_pid_entry_point_timestamp(tmp_path):
    memory_dir = _make_memory_dir(tmp_path)
    lock = SingleInstanceLock(memory_dir, entry_point="main.py")
    lock.acquire()
    try:
        lock_path = memory_dir / single_instance.LOCK_FILENAME
        assert lock_path.exists()
        content = _read_locked_content(lock)
        assert content["pid"] == os.getpid()
        assert content["entry_point"] == "main.py"
        datetime.fromisoformat(content["timestamp"])
    finally:
        lock.release()


def test_release_removes_lock_file(tmp_path):
    memory_dir = _make_memory_dir(tmp_path)
    lock = SingleInstanceLock(memory_dir, entry_point="main.py")
    lock.acquire()
    lock.release()
    assert not (memory_dir / single_instance.LOCK_FILENAME).exists()


def test_release_without_acquire_is_a_no_op(tmp_path):
    memory_dir = _make_memory_dir(tmp_path)
    lock = SingleInstanceLock(memory_dir, entry_point="main.py")
    lock.release()  # darf nicht werfen


def test_context_manager_acquires_and_releases(tmp_path):
    memory_dir = _make_memory_dir(tmp_path)
    lock_path = memory_dir / single_instance.LOCK_FILENAME
    with SingleInstanceLock(memory_dir, entry_point="main.py"):
        assert lock_path.exists()
    assert not lock_path.exists()


def test_different_memory_dirs_do_not_block_each_other(tmp_path):
    dir_a = _make_memory_dir(tmp_path / "a")
    dir_b = _make_memory_dir(tmp_path / "b")

    lock_a = SingleInstanceLock(dir_a, entry_point="main.py")
    lock_b = SingleInstanceLock(dir_b, entry_point="telegram_main.py")
    lock_a.acquire()
    try:
        lock_b.acquire()  # darf nicht blockieren - anderes memory_dir
        lock_b.release()
    finally:
        lock_a.release()


def test_actively_held_lock_survives_a_second_acquire_attempt(tmp_path):
    """Regressionstest fuer einen real gefundenen Bug: msvcrt.locking()
    verweigert das Lesen der Lock-Datei ueber ein frisches Handle
    (PermissionError) - auch innerhalb desselben Prozesses. Eine fruehere
    Implementierung interpretierte diesen Lesefehler faelschlich als
    "verwaist" und loeschte die aktive Lock-Datei. Kein psutil-Mock
    noetig: der zweite Erwerbsversuch scheitert bereits beim Lesen, bevor
    die PID-Pruefung ueberhaupt greift."""
    memory_dir = _make_memory_dir(tmp_path)
    lock1 = SingleInstanceLock(memory_dir, entry_point="main.py")
    lock1.acquire()
    try:
        lock2 = SingleInstanceLock(memory_dir, entry_point="main.py")
        with pytest.raises(InstanceAlreadyRunningError):
            lock2.acquire()
        assert lock2._fh is None

        # Der erste Lock ist weiterhin intakt und lesbar - wurde NICHT
        # durch den gescheiterten zweiten Versuch geloescht.
        content = _read_locked_content(lock1)
        assert content["pid"] == os.getpid()
        assert content["entry_point"] == "main.py"
    finally:
        lock1.release()


def test_second_instance_blocked_while_first_is_genuinely_active(tmp_path, monkeypatch):
    memory_dir = _make_memory_dir(tmp_path)
    fake_pid = 999999
    monkeypatch.setattr(single_instance.psutil, "pid_exists", lambda pid: pid == fake_pid)
    monkeypatch.setattr(
        single_instance.psutil,
        "Process",
        lambda pid: _FakeProcess(["C:\\Python\\python.exe", "C:\\jarvis\\main.py"]),
    )

    lock_path = memory_dir / single_instance.LOCK_FILENAME
    lock_path.write_text(
        json.dumps(
            {"pid": fake_pid, "entry_point": "main.py", "timestamp": "2026-07-02T10:00:00"}
        ),
        encoding="utf-8",
    )

    lock = SingleInstanceLock(memory_dir, entry_point="main.py")
    with pytest.raises(InstanceAlreadyRunningError) as exc_info:
        lock.acquire()

    assert exc_info.value.pid == fake_pid
    assert exc_info.value.entry_point == "main.py"
    assert str(fake_pid) in str(exc_info.value)
    assert "main.py" in str(exc_info.value)
    # Kein Lock-Erwerb - keine Datei-Handle-Leiche zurücklassen.
    assert lock._fh is None


def test_stale_lock_from_dead_pid_is_self_healed(tmp_path, monkeypatch):
    memory_dir = _make_memory_dir(tmp_path)
    dead_pid = 999998
    monkeypatch.setattr(single_instance.psutil, "pid_exists", lambda pid: False)

    lock_path = memory_dir / single_instance.LOCK_FILENAME
    lock_path.write_text(
        json.dumps(
            {"pid": dead_pid, "entry_point": "main.py", "timestamp": "2026-07-01T09:00:00"}
        ),
        encoding="utf-8",
    )

    lock = SingleInstanceLock(memory_dir, entry_point="jarvis_runtime.py")
    lock.acquire()  # darf nicht scheitern - verwaiste Lock-Datei wird entfernt
    try:
        content = _read_locked_content(lock)
        assert content["pid"] == os.getpid()
        assert content["entry_point"] == "jarvis_runtime.py"
    finally:
        lock.release()


def test_pid_reuse_is_treated_as_stale(tmp_path, monkeypatch):
    """PID existiert (z. B. durch Windows wiederverwendet), aber der
    tatsaechlich laufende Prozess ist erkennbar kein Jarvis-Prozess -
    die Lock-Datei muss trotzdem als verwaist gelten (ADR-026)."""
    memory_dir = _make_memory_dir(tmp_path)
    reused_pid = 999997
    monkeypatch.setattr(single_instance.psutil, "pid_exists", lambda pid: pid == reused_pid)
    monkeypatch.setattr(
        single_instance.psutil,
        "Process",
        lambda pid: _FakeProcess(["C:\\Windows\\explorer.exe"]),
    )

    lock_path = memory_dir / single_instance.LOCK_FILENAME
    lock_path.write_text(
        json.dumps(
            {"pid": reused_pid, "entry_point": "main.py", "timestamp": "2026-07-01T09:00:00"}
        ),
        encoding="utf-8",
    )

    lock = SingleInstanceLock(memory_dir, entry_point="main.py")
    lock.acquire()
    lock.release()


def test_entry_point_substring_does_not_cause_false_match(tmp_path, monkeypatch):
    """"main.py" ist Substring von "telegram_main.py" - ein Vergleich
    ueber String-Enthaltensein waere hier falsch-positiv. Der laufende
    Prozess ist tatsaechlich telegram_main.py, die Lock-Datei behauptet
    aber main.py - muss als verwaist gelten (exakter Dateiname-Abgleich)."""
    memory_dir = _make_memory_dir(tmp_path)
    fake_pid = 999994
    monkeypatch.setattr(single_instance.psutil, "pid_exists", lambda pid: pid == fake_pid)
    monkeypatch.setattr(
        single_instance.psutil,
        "Process",
        lambda pid: _FakeProcess(["C:\\Python\\python.exe", "C:\\jarvis\\telegram_main.py"]),
    )

    lock_path = memory_dir / single_instance.LOCK_FILENAME
    lock_path.write_text(
        json.dumps(
            {"pid": fake_pid, "entry_point": "main.py", "timestamp": "2026-07-01T09:00:00"}
        ),
        encoding="utf-8",
    )

    lock = SingleInstanceLock(memory_dir, entry_point="jarvis_runtime.py")
    lock.acquire()  # darf nicht als "aktiv" fehlinterpretiert werden
    lock.release()


def test_access_denied_when_checking_process_is_treated_as_stale(tmp_path, monkeypatch):
    memory_dir = _make_memory_dir(tmp_path)
    guarded_pid = 999995
    monkeypatch.setattr(single_instance.psutil, "pid_exists", lambda pid: pid == guarded_pid)

    def _raise_access_denied(pid):
        raise single_instance.psutil.AccessDenied(pid=pid)

    monkeypatch.setattr(single_instance.psutil, "Process", _raise_access_denied)

    lock_path = memory_dir / single_instance.LOCK_FILENAME
    lock_path.write_text(
        json.dumps(
            {"pid": guarded_pid, "entry_point": "main.py", "timestamp": "2026-07-01T09:00:00"}
        ),
        encoding="utf-8",
    )

    lock = SingleInstanceLock(memory_dir, entry_point="main.py")
    lock.acquire()
    lock.release()


def test_corrupt_lock_file_is_treated_as_stale(tmp_path):
    memory_dir = _make_memory_dir(tmp_path)
    lock_path = memory_dir / single_instance.LOCK_FILENAME
    lock_path.write_text("{not valid json", encoding="utf-8")

    lock = SingleInstanceLock(memory_dir, entry_point="main.py")
    lock.acquire()
    lock.release()


def test_retry_acquire_takes_over_after_predecessor_releases(tmp_path):
    """Neustart-Staffelstab (restart_runtime, Welle 3.4): der Nachfolger
    wartet mit retry_seconds auf die Lock-Freigabe des Vorgaengers und
    uebernimmt dann - statt sofort zu sterben."""
    import threading

    memory_dir = _make_memory_dir(tmp_path)
    predecessor = SingleInstanceLock(memory_dir, entry_point="jarvis_runtime.py")
    predecessor.acquire()

    releaser = threading.Timer(0.3, predecessor.release)
    releaser.start()
    try:
        successor = SingleInstanceLock(memory_dir, entry_point="jarvis_runtime.py")
        successor.acquire(retry_seconds=5.0, poll_interval=0.05)  # darf nicht werfen
        try:
            assert _read_locked_content(successor)["pid"] == os.getpid()
        finally:
            successor.release()
    finally:
        releaser.join()


def test_retry_acquire_gives_up_after_timeout(tmp_path):
    """Haengt der Vorgaenger, gibt der Nachfolger nach dem Warte-Budget mit
    der normalen Fehlermeldung auf - kein Endlos-Warten."""
    memory_dir = _make_memory_dir(tmp_path)
    holder = SingleInstanceLock(memory_dir, entry_point="jarvis_runtime.py")
    holder.acquire()
    try:
        waiter = SingleInstanceLock(memory_dir, entry_point="jarvis_runtime.py")
        with pytest.raises(InstanceAlreadyRunningError):
            waiter.acquire(retry_seconds=0.2, poll_interval=0.05)
        assert waiter._fh is None
    finally:
        holder.release()


def test_acquire_default_still_fails_immediately(tmp_path):
    """Ohne retry_seconds bleibt das heutige Verhalten exakt erhalten -
    ein versehentlicher Doppelstart stirbt sofort (ADR-026 unangetastet)."""
    import time

    memory_dir = _make_memory_dir(tmp_path)
    holder = SingleInstanceLock(memory_dir, entry_point="main.py")
    holder.acquire()
    try:
        started = time.monotonic()
        with pytest.raises(InstanceAlreadyRunningError):
            SingleInstanceLock(memory_dir, entry_point="main.py").acquire()
        assert time.monotonic() - started < 0.4  # kein verstecktes Warten
    finally:
        holder.release()


def test_acquire_after_clean_release_succeeds_again(tmp_path):
    memory_dir = _make_memory_dir(tmp_path)
    lock = SingleInstanceLock(memory_dir, entry_point="main.py")
    lock.acquire()
    lock.release()

    lock2 = SingleInstanceLock(memory_dir, entry_point="main.py")
    lock2.acquire()
    lock2.release()
