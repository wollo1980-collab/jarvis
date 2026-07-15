"""Tests fuer den Neustart-Voll-Automaten (PO-Entscheidung Nachtmodus 13.07.):
JarvisRuntime._maybe_auto_restart als ungebundene Methode gegen ein Fake-Objekt
- geprueft werden die Leerlauf-Garden, ohne den echten Stack zu starten."""
from __future__ import annotations

import queue
import time
from types import SimpleNamespace

from jarvis_runtime import JarvisRuntime


def _fake(**overrides):
    """Fake-Runtime im 'sicher neustartbar'-Zustand; Overrides kippen je
    genau eine Garde."""
    calls = []
    fake = SimpleNamespace(
        _auto_restart_enabled=True,
        _startup_git_head="alt1234",
        _version_hint_seen_head="neu5678",
        _auto_restart_attempted_head="",
        _started_monotonic=time.monotonic() - 3600.0,
        _last_message_monotonic=time.monotonic() - 3600.0,
        _delegation_thread=None,
        _queue=queue.Queue(),
        _AUTO_RESTART_IDLE_SECONDS=JarvisRuntime._AUTO_RESTART_IDLE_SECONDS,
        _AUTO_RESTART_MIN_UPTIME_SECONDS=JarvisRuntime._AUTO_RESTART_MIN_UPTIME_SECONDS,
        _request_restart=lambda: calls.append("restart") or True,
    )
    for key, value in overrides.items():
        setattr(fake, key, value)
    return fake, calls


def test_auto_restart_fires_when_idle_with_new_version():
    fake, calls = _fake()
    JarvisRuntime._maybe_auto_restart(fake)
    assert calls == ["restart"]
    assert fake._auto_restart_attempted_head == "neu5678"


def test_auto_restart_only_one_attempt_per_head():
    """Kein Spawn-Pingpong: je neuem Stand genau EIN Versuch - auch wenn der
    Neustart fehlschlaegt, wird derselbe Stand nicht erneut probiert."""
    attempts: list[str] = []
    fake, _ = _fake(_request_restart=lambda: attempts.append("x") or False)
    JarvisRuntime._maybe_auto_restart(fake)
    JarvisRuntime._maybe_auto_restart(fake)
    assert attempts == ["x"]


def test_auto_restart_guards_hold():
    """Jede Garde einzeln: aus / kein neuer Stand / Gespraech zu frisch /
    eigener Start zu frisch / Delegation laeuft / Queue nicht leer."""
    blockers = [
        {"_auto_restart_enabled": False},
        {"_version_hint_seen_head": ""},
        {"_version_hint_seen_head": "alt1234"},          # kein NEUER Stand
        {"_last_message_monotonic": time.monotonic()},   # Gespraech zu frisch
        {"_started_monotonic": time.monotonic()},        # Start zu frisch
        {"_delegation_thread": SimpleNamespace(is_alive=lambda: True)},
    ]
    for overrides in blockers:
        fake, calls = _fake(**overrides)
        JarvisRuntime._maybe_auto_restart(fake)
        assert calls == [], f"Garde versagt bei {overrides}"

    busy_queue = queue.Queue()
    busy_queue.put("nachricht")
    fake, calls = _fake(_queue=busy_queue)
    JarvisRuntime._maybe_auto_restart(fake)
    assert calls == []
