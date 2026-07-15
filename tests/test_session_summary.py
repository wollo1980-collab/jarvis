"""Tests fuer memory/session_summary.py (ADR-065 B1) - Faltung rein/injiziert."""
from __future__ import annotations

from core.models import Message
from memory.session_summary import SessionSummary


def _msgs(n: int) -> list[Message]:
    return [Message(role="user" if i % 2 == 0 else "assistant", content=f"m{i}") for i in range(n)]


def _fake_summarize(prev: str, messages: list[Message]) -> str:
    # deterministisch: haengt die eingefalteten Inhalte an die bisherige Summary
    folded = ",".join(m.content for m in messages)
    return (prev + "|" + folded) if prev else folded


def test_no_fold_below_threshold():
    s = SessionSummary(recent_window=20, chunk=8)
    s.maybe_update(_msgs(25), _fake_summarize)   # target=5 < chunk=8 -> nichts
    assert s.summary() == ""


def test_folds_overflow_beyond_recent_window():
    s = SessionSummary(recent_window=20, chunk=8)
    s.maybe_update(_msgs(40), _fake_summarize)   # target=20 -> faltet m0..m19
    assert s.summary() == ",".join(f"m{i}" for i in range(20))


def test_recent_window_is_never_folded():
    s = SessionSummary(recent_window=20, chunk=8)
    s.maybe_update(_msgs(40), _fake_summarize)
    # die letzten 20 (m20..m39) sind NICHT in der Zusammenfassung
    for i in range(20, 40):
        assert f"m{i}" not in s.summary()


def test_incremental_folding_appends():
    s = SessionSummary(recent_window=10, chunk=5)
    s.maybe_update(_msgs(20), _fake_summarize)   # target=10 -> m0..m9
    first = s.summary()
    assert first == ",".join(f"m{i}" for i in range(10))
    s.maybe_update(_msgs(30), _fake_summarize)   # target=20 -> m10..m19 angehaengt
    assert s.summary() == first + "|" + ",".join(f"m{i}" for i in range(10, 20))


def test_shrunk_buffer_resets_safely():
    s = SessionSummary(recent_window=10, chunk=5)
    s.maybe_update(_msgs(30), _fake_summarize)   # folded=20
    assert s.summary()
    s.maybe_update(_msgs(12), _fake_summarize)   # Puffer geschrumpft -> Reset, target=2<chunk -> leer
    assert s.summary() == ""


def test_empty_summary_result_keeps_state():
    s = SessionSummary(recent_window=10, chunk=5)
    s.maybe_update(_msgs(30), lambda prev, msgs: "")   # summarize liefert leer
    assert s.summary() == ""
    assert s._folded == 0   # kein Fortschritt verbucht, wird spaeter erneut versucht


def test_async_folds_in_background_thread():
    """Latenz-Fix 13.07.: maybe_update_async faltet im Hintergrund - der
    Aufrufer wartet nicht. Nach join ist die Faltung identisch zur synchronen."""
    s = SessionSummary(recent_window=20, chunk=8)
    thread = s.maybe_update_async(_msgs(40), _fake_summarize)

    assert thread is not None
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert s.summary() == ",".join(f"m{i}" for i in range(20))


def test_concurrent_fold_runs_only_once():
    """Ein-Falter-Garde: waehrend ein (langsamer) LLM-Call faltet, kehrt ein
    zweiter maybe_update sofort zurueck - nie gestapelte LLM-Calls."""
    import threading

    started = threading.Event()
    release = threading.Event()
    calls = []

    def slow_summarize(prev, msgs):
        calls.append(len(msgs))
        started.set()
        release.wait(timeout=5)
        return _fake_summarize(prev, msgs)

    s = SessionSummary(recent_window=10, chunk=5)
    thread = s.maybe_update_async(_msgs(20), slow_summarize)
    assert started.wait(timeout=5)

    s.maybe_update(_msgs(20), slow_summarize)   # waehrend der Faltung: Garde greift
    release.set()
    thread.join(timeout=5)

    assert calls == [10]                        # genau EIN LLM-Call
    assert s.summary() == ",".join(f"m{i}" for i in range(10))
