"""Tests für jarvis_runtime.py - JarvisRuntime (Queue+Worker-Thread),
_RuntimeSpeech (fail-closed) und ConsoleDummyChannel (ADR-025). AIEngine
gemockt (FakeAI, gleiches Muster wie tests/test_integration.py), kein
echter API-Key/Netzwerk nötig."""
from __future__ import annotations

import logging
import sys
import threading
import time
import types
from pathlib import Path
from unittest.mock import MagicMock

import commands.delegate as delegate_commands
import commands.web as web_commands
import jarvis_runtime
from core.agent_backend import AgentResult
from core.config import Config
from core.models import Message, Plan, Result, Status
from core.web_search import SearchResult
from jarvis_runtime import ConsoleDummyChannel, JarvisRuntime, _RuntimeSpeech


class FakeAI:
    """Gleiches Muster wie tests/test_integration.py::FakeAI."""

    def get_plan(self, user_input, history):
        text = user_input.lower()
        if "kritisch" in text:
            return Plan(intent="shutdown_pc", raw_input=user_input, confidence=1.0)
        if "web" in text or "internet" in text or "recherch" in text:
            return Plan(
                intent="search_web",
                target="Wetter Berlin",
                raw_input=user_input,
                confidence=1.0,
            )
        return Plan(intent="chat", raw_input=user_input, confidence=1.0)

    def answer(self, user_input, history, long_term_summary=""):
        return f"Antwort auf: {user_input}"


def _make_config(tmp_path: Path) -> Config:
    memory_dir = tmp_path / "memory_data"
    log_dir = tmp_path / "logs"
    memory_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    return Config(memory_dir=memory_dir, log_dir=log_dir, max_history_entries=20)


def _wait(event: threading.Event, timeout: float = 2.0) -> None:
    assert event.wait(timeout=timeout), "Timeout - Worker hat nicht rechtzeitig geantwortet"


# --- Episodisches Gedaechtnis (Gedaechtnis-Kampagne Stufe 1) ------------

def test_episodic_records_an_episode_when_enabled(tmp_path):
    from datetime import date

    from memory.episodic import EpisodicMemory

    config = _make_config(tmp_path)
    config.episodic_memory_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())

    runtime._process_inner("hallo jarvis", lambda _msg: None)

    eps = EpisodicMemory(config.memory_dir).for_day(date.today())
    assert len(eps) == 1
    assert eps[0]["user_input"] == "hallo jarvis"
    assert eps[0]["intents"] == ["chat"]
    assert eps[0]["response"].startswith("Antwort auf:")


def test_episodic_off_by_default_writes_nothing(tmp_path):
    config = _make_config(tmp_path)  # episodic_memory_enabled Default False
    runtime = JarvisRuntime(config, ai=FakeAI())

    runtime._process_inner("hallo", lambda _msg: None)

    assert not (config.memory_dir / "episodes").exists()


# --- Naechtliche Reflexion ('dreaming', Gedaechtnis Stufe 2) ------------

def test_daily_reflection_writes_journal_when_enabled(tmp_path):
    from datetime import date

    from memory.reflection import ReflectionJournal

    config = _make_config(tmp_path)
    config.episodic_memory_enabled = True
    config.reflection_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())

    runtime._process_inner("erinnere mich an den zahnarzt", lambda _msg: None)  # eine Episode
    runtime.run_daily_reflection(date.today())

    journal = ReflectionJournal(config.memory_dir).read(date.today())
    assert journal.startswith("# Reflexion")
    # Die Episode floss in den Reflexions-Prompt (FakeAI.answer echot ihn):
    assert "zahnarzt" in journal


def test_daily_reflection_off_writes_nothing(tmp_path):
    from datetime import date

    config = _make_config(tmp_path)  # reflection_enabled Default False
    runtime = JarvisRuntime(config, ai=FakeAI())

    runtime.run_daily_reflection(date.today())

    assert not (config.memory_dir / "reflections").exists()


def _reflection_offer_runtime(tmp_path):
    config = _make_config(tmp_path)
    config.episodic_memory_enabled = True
    config.reflection_enabled = True
    config.memory_offers_enabled = True
    config.reflection_offers_enabled = True
    return JarvisRuntime(config, ai=FakeAI()), config


def test_reflection_suggestion_surfaced_once_and_yes_stores(tmp_path):
    """Stein 2b: eine schwebende Reflexions-Vermutung wird beim naechsten
    Gespraech als ja/nein-Merk-Angebot vorgeschlagen; 'ja' speichert sie."""
    from core.fileio import write_json_atomic

    runtime, config = _reflection_offer_runtime(tmp_path)
    write_json_atomic(config.memory_dir / "reflection_suggestion.json",
                      {"suggestion": "hoert abends oft Musik"})

    replies = []
    runtime._process_inner("wie spaet ist es", replies.append)
    assert "als Gewohnheit merken" in replies[0]
    assert "hoert abends oft Musik" in replies[0]

    # nur EINMAL - eine zweite Nachricht bietet es nicht erneut an:
    replies2 = []
    runtime._process_inner("ja", replies2.append)
    assert any("Musik" in f.text for f in runtime.long_term.all_facts())

    replies3 = []
    runtime._process_inner("noch was", replies3.append)
    assert "Gewohnheit merken" not in replies3[0]


def test_reflection_offers_off_does_not_surface(tmp_path):
    from core.fileio import write_json_atomic

    config = _make_config(tmp_path)
    config.episodic_memory_enabled = True
    config.reflection_enabled = True
    config.memory_offers_enabled = True
    # reflection_offers_enabled bleibt Default False
    runtime = JarvisRuntime(config, ai=FakeAI())
    write_json_atomic(config.memory_dir / "reflection_suggestion.json",
                      {"suggestion": "hoert abends oft Musik"})

    replies = []
    runtime._process_inner("hallo", replies.append)
    assert "Gewohnheit merken" not in replies[0]


# --- Proaktive Vorbereitung (ADR-063) ----------------------------------


def _proactive_runtime(tmp_path):
    config = _make_config(tmp_path)
    config.proactive_prep_enabled = True
    return JarvisRuntime(config, ai=FakeAI()), config


_PREP = {
    "subject": "Steuerberater", "event_time": "09:00",
    "reminder_text": "Steuerberater um 09:00",
    "reminder_when_iso": "2030-01-02T08:00:00", "reminder_time": "08:00",
    "nudge": ("Kleiner Blick voraus, Sir: Morgen um 09:00 steht «Steuerberater» an. "
              "Soll ich dich um 08:00 rechtzeitig daran erinnern? (ja/nein)"),
    "generated_for": "2030-01-02", "done": False,
}


def test_proactive_offer_surfaced_once_and_yes_creates_reminder(tmp_path):
    from core.fileio import write_json_atomic

    runtime, config = _proactive_runtime(tmp_path)
    write_json_atomic(config.memory_dir / "proactive_suggestion.json", dict(_PREP))

    replies = []
    runtime._process_inner("wie spaet ist es", replies.append)
    assert "Steuerberater" in replies[0] and "(ja/nein)" in replies[0]
    assert runtime._entry_store.list_open(keyword="Steuerberater") == []  # noch nichts angelegt

    runtime._process_inner("ja", replies.append)
    reminders = runtime._entry_store.list_open(keyword="Steuerberater")
    assert len(reminders) == 1                      # 'ja' legt die Erinnerung an
    assert reminders[0].when.startswith("2030-01-02T08:00")

    # nur EINMAL - eine weitere Nachricht bietet nicht erneut an:
    replies3 = []
    runtime._process_inner("noch was", replies3.append)
    assert "ja/nein" not in replies3[0]


def test_proactive_offer_no_declines_without_reminder(tmp_path):
    from core.fileio import write_json_atomic

    runtime, config = _proactive_runtime(tmp_path)
    write_json_atomic(config.memory_dir / "proactive_suggestion.json", dict(_PREP))

    replies = []
    runtime._process_inner("hallo", replies.append)
    runtime._process_inner("nein", replies.append)

    assert "erinnere ich nicht" in replies[1]
    assert runtime._entry_store.list_open(keyword="Steuerberater") == []


def test_proactive_off_does_not_surface(tmp_path):
    from core.fileio import write_json_atomic

    config = _make_config(tmp_path)   # proactive_prep_enabled Default False
    runtime = JarvisRuntime(config, ai=FakeAI())
    write_json_atomic(config.memory_dir / "proactive_suggestion.json", dict(_PREP))

    replies = []
    runtime._process_inner("hallo", replies.append)
    assert "ja/nein" not in replies[0]


def test_proactive_offer_is_channel_bound(tmp_path):
    from core.fileio import write_json_atomic

    runtime, config = _proactive_runtime(tmp_path)
    write_json_atomic(config.memory_dir / "proactive_suggestion.json", dict(_PREP))

    replies = []
    runtime._process_inner("hallo", replies.append, source="browser")
    assert "(ja/nein)" in replies[0]

    runtime._process_inner("ja", replies.append, source="telegram")   # fremder Kanal
    assert runtime._entry_store.list_open(keyword="Steuerberater") == []  # NICHT angelegt
    assert replies[1].startswith("Antwort auf:")                          # normal verarbeitet


def test_run_proactive_check_stores_from_calendar(tmp_path, monkeypatch):
    from datetime import date, datetime

    import commands.calendar as calendar_commands

    runtime, config = _proactive_runtime(tmp_path)
    monkeypatch.setattr(calendar_commands, "read_agenda", lambda day: [
        {"subject": "Steuerberater", "start": "2030-01-02T09:00:00",
         "end": "2030-01-02T10:00:00", "all_day": False},
    ])

    payload = runtime.run_proactive_check(date(2030, 1, 2), now=datetime(2030, 1, 1, 20, 0))

    assert payload is not None and payload["subject"] == "Steuerberater"
    pending = runtime._pending_proactive()
    assert pending["reminder_time"] == "08:00"
    assert "Steuerberater" in pending["nudge"]


# --- Merk-Angebot (ADR-051) --------------------------------------------


class SuggestingAI(FakeAI):
    """FakeAI, der bei 'kaffee' nebenbei einen dauerhaften Fakt erkennt."""

    def get_plan(self, user_input, history):
        plan = super().get_plan(user_input, history)
        if "kaffee" in user_input.lower():
            plan.memory_suggestion = "ich trinke meinen Kaffee schwarz"
        return plan


def _offers_runtime(tmp_path):
    config = _make_config(tmp_path)
    config.memory_offers_enabled = True
    return JarvisRuntime(config, ai=SuggestingAI()), config


def test_memory_offer_appended_and_yes_stores_fact(tmp_path):
    runtime, config = _offers_runtime(tmp_path)
    replies = []

    runtime._process_inner("Übrigens trinke ich meinen Kaffee schwarz", replies.append)
    assert "Soll ich mir dauerhaft merken" in replies[0]
    assert "Kaffee schwarz" in replies[0]
    assert runtime.long_term.all_facts() == []  # NIE vor dem Ja gespeichert

    runtime._process_inner("ja", replies.append)
    facts = runtime.long_term.all_facts()
    assert len(facts) == 1
    assert "Kaffee schwarz" in facts[0].text
    assert facts[0].category == "gewohnheit"


def test_memory_offer_no_lands_on_decline_list_and_never_returns(tmp_path):
    import json as json_module

    runtime, config = _offers_runtime(tmp_path)
    replies = []

    runtime._process_inner("kaffee schwarz, wie immer", replies.append)
    runtime._process_inner("nein", replies.append)

    assert "nicht wieder" in replies[1]
    assert runtime.long_term.all_facts() == []
    declined = json_module.loads(
        (config.memory_dir / "memory_declined.json").read_text(encoding="utf-8")
    )
    assert declined == ["ich trinke meinen Kaffee schwarz"]

    # Derselbe Fakt wird NIE wieder angeboten (Nerv-Schutz).
    replies.clear()
    runtime._process_inner("nochmal kaffee erwaehnt", replies.append)
    assert "Soll ich mir dauerhaft merken" not in replies[0]


def test_memory_offer_expires_silently_on_any_other_message(tmp_path):
    runtime, _ = _offers_runtime(tmp_path)
    replies = []

    runtime._process_inner("kaffee wie immer schwarz", replies.append)
    runtime._process_inner("was liegt heute an?", replies.append)

    # Die Zwischen-Nachricht wurde NORMAL verarbeitet, nichts gespeichert:
    assert replies[1].startswith("Antwort auf:")
    assert runtime.long_term.all_facts() == []
    # Ein spaetes "ja" trifft KEIN Angebot mehr - normaler Chat:
    runtime._process_inner("ja", replies.append)
    assert runtime.long_term.all_facts() == []
    assert replies[2].startswith("Antwort auf:")


def test_memory_offer_is_channel_bound(tmp_path):
    """Nacht-Audit-Fix A: ein 'ja' aus einem ANDEREN Kanal beantwortet nie
    ein fremdes Angebot - es laesst es verfallen und wird selbst normal
    verarbeitet (nie verschluckt)."""
    runtime, _ = _offers_runtime(tmp_path)
    replies = []

    runtime._process_inner("kaffee schwarz wie immer", replies.append, source="browser")
    assert "Soll ich mir dauerhaft merken" in replies[0]

    runtime._process_inner("ja", replies.append, source="telegram")

    assert runtime.long_term.all_facts() == []          # NICHT gespeichert
    assert replies[1].startswith("Antwort auf:")        # normal verarbeitet
    # Angebot ist verfallen - auch das eigene Kanal-"ja" trifft nichts mehr:
    runtime._process_inner("ja", replies.append, source="browser")
    assert runtime.long_term.all_facts() == []


def test_declined_offer_is_redacted_before_persist(tmp_path, monkeypatch):
    """Nacht-Audit-Fix C: auch die Nein-Liste faellt unter ADR-040."""
    import json as json_module

    import jarvis_runtime as runtime_module

    monkeypatch.setattr(runtime_module, "redact", lambda t: t.replace("geheim123", "[GEHEIM]"))
    runtime, config = _offers_runtime(tmp_path)
    runtime._memory_offer = ("", "mein Passwort ist geheim123")
    replies = []

    runtime._process_inner("nein", replies.append)

    declined = json_module.loads(
        (config.memory_dir / "memory_declined.json").read_text(encoding="utf-8")
    )
    assert declined == ["mein Passwort ist [GEHEIM]"]  # nie im Klartext


def test_memory_offer_not_made_for_known_fact(tmp_path):
    runtime, _ = _offers_runtime(tmp_path)
    runtime.long_term.remember("ich trinke meinen Kaffee schwarz", category="gewohnheit")
    replies = []

    runtime._process_inner("kaffee, schwarz wie immer", replies.append)

    assert "Soll ich mir dauerhaft merken" not in replies[0]


def test_memory_offer_disabled_by_default(tmp_path):
    runtime = JarvisRuntime(_make_config(tmp_path), ai=SuggestingAI())
    replies = []

    runtime._process_inner("kaffee schwarz bitte", replies.append)

    assert "Soll ich mir dauerhaft merken" not in replies[0]  # Default AUS


def test_runtime_wires_core_stack(tmp_path):
    config = _make_config(tmp_path)
    ai = FakeAI()

    runtime = JarvisRuntime(config, ai=ai)

    assert runtime.ai is ai
    assert runtime.planner is not None
    assert runtime.executor is not None
    assert runtime.memory is not None
    assert runtime.long_term is not None


def test_runtime_configures_mail(tmp_path, monkeypatch):
    # Regressionsanker: das Mail-Briefing muss auch im Runtime-Stack
    # konfiguriert werden, damit check_mail ueber den Runtime-Telegram-Kanal
    # nicht ins Leere laeuft (Arbeitspaket B, ADR-031-Nachtrag).
    calls = []
    monkeypatch.setattr(
        jarvis_runtime.mail_commands, "configure", lambda config, **kw: calls.append(config)
    )
    JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    assert len(calls) == 1


def test_submit_and_process_single_message(tmp_path):
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("hallo", reply_callback)
        _wait(done)

        assert replies == ["Antwort auf: hallo"]
    finally:
        runtime.stop()


def test_runtime_handles_search_web(tmp_path, monkeypatch):
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    monkeypatch.setattr(
        web_commands,
        "_searcher",
        lambda query, max_results, timeout_seconds: [
            SearchResult(
                title="Wetter Berlin",
                url="https://example.com/wetter-berlin",
                snippet="Mild und trocken.",
            )
        ],
    )
    # web v2 liest die Treffer-Seite - in Tests durch Platzhalter ersetzt (kein Netz).
    monkeypatch.setattr(web_commands, "_page_fetcher", lambda url, timeout: "Mild und trocken.")
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("suche im web nach wetter berlin", reply_callback)
        _wait(done)

        # A3: ohne Composer (Default aus) zeigt search_web die Fallback-Quellenzeile
        assert "Quellen gelesen" in replies[0]
        assert "example.com" in replies[0]   # kompakte Domain statt voller Link
    finally:
        runtime.stop()


def test_submit_without_plan_filter_is_unchanged(tmp_path):
    """Regressionsanker (ADR-027): der bisherige 2-Arg-Aufruf verhaelt
    sich exakt wie in Runtime v1 - plan_filter ist optional."""
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("hallo", reply_callback)
        _wait(done)

        assert replies == ["Antwort auf: hallo"]
    finally:
        runtime.stop()


def test_plan_filter_allows_plan_executes_normally(tmp_path):
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        def allow_all(steps):
            return steps, None

        runtime.submit("hallo", reply_callback, plan_filter=allow_all)
        _wait(done)

        assert replies == ["Antwort auf: hallo"]
        history = runtime.memory.get_history()
        assert [m.content for m in history] == ["hallo", "Antwort auf: hallo"]
    finally:
        runtime.stop()


def test_plan_filter_rejects_plan_without_calling_executor(tmp_path):
    """Sicherheitskritisch (ADR-027): eine Ablehnung darf den Executor
    nicht erreichen - sonst waeren Sicherheitsstufe-2/3-unabhaengige
    Einschraenkungen (z. B. eine Intent-Whitelist) wirkungslos."""
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.executor.run = MagicMock(side_effect=AssertionError("Executor haette nicht laufen duerfen"))
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        def reject_all(steps):
            return [], "Anfrage abgelehnt: nicht erlaubt"

        runtime.submit("hallo", reply_callback, plan_filter=reject_all)
        _wait(done)

        assert replies == ["Anfrage abgelehnt: nicht erlaubt"]
        runtime.executor.run.assert_not_called()
    finally:
        runtime.stop()


def test_plan_filter_rejection_does_not_write_history(tmp_path):
    """Parität zu telegram_main.py::JarvisBridge.handle_message: eine
    Ablehnung wird nicht ins Gespraechsgedaechtnis geschrieben."""
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        def reject_all(steps):
            return [], "Anfrage abgelehnt: nicht erlaubt"

        runtime.submit("hallo", reply_callback, plan_filter=reject_all)
        _wait(done)

        assert replies == ["Anfrage abgelehnt: nicht erlaubt"]
        assert runtime.memory.get_history() == []
    finally:
        runtime.stop()


def test_messages_processed_sequentially_in_order(tmp_path):
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        order = []
        all_done = threading.Event()
        lock = threading.Lock()
        expected = 5

        def make_callback(i):
            def callback(text):
                with lock:
                    order.append(i)
                    if len(order) == expected:
                        all_done.set()

            return callback

        for i in range(expected):
            runtime.submit(f"nachricht {i}", make_callback(i))

        _wait(all_done)
        assert order == list(range(expected))
    finally:
        runtime.stop()


def test_concurrent_submits_from_multiple_threads_not_lost(tmp_path):
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        received = []
        lock = threading.Lock()
        all_done = threading.Event()
        expected = 6

        def callback(text):
            with lock:
                received.append(text)
                if len(received) == expected:
                    all_done.set()

        def submitter(i):
            runtime.submit(f"kanal-{i}", callback)

        threads = [threading.Thread(target=submitter, args=(i,)) for i in range(expected)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        _wait(all_done)
        assert len(received) == expected
        assert len(set(received)) == expected  # keine doppelten/verlorenen Antworten
    finally:
        runtime.stop()


def test_stop_cleanly_terminates_worker_thread(tmp_path):
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()

    runtime.stop()

    assert runtime._worker.is_alive() is False


def test_scheduler_fires_due_entry_once(tmp_path, monkeypatch):
    """A2 (ADR-039): ein faelliger, ungemeldeter Eintrag wird GENAU EINMAL
    ueber den injizierten Notifier gemeldet und als notified markiert."""
    monkeypatch.setattr(jarvis_runtime, "_SCHEDULER_POLL_SECONDS", 0.05)
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    store = runtime._entry_store
    entry = store.add("Zahnarzt", when="2099-01-01T09:00")  # Zukunft -> unnotified
    # Zeit "verstreicht": when in die Vergangenheit ziehen, Flag bleibt False.
    data = store._read()
    data[0]["when"] = "2020-01-01T09:00"
    store._write(data)

    fired = []
    got_one = threading.Event()

    def notifier(text):
        fired.append(text)
        got_one.set()

    runtime.set_notifier(notifier)
    runtime.start_scheduler()
    try:
        assert got_one.wait(timeout=2.0), "Scheduler hat nicht gefeuert"
        time.sleep(0.2)  # weitere Ticks abwarten -> darf NICHT erneut feuern
        assert len(fired) == 1
        assert "Zahnarzt" in fired[0] and fired[0].startswith("🔔")
        assert store.due_unnotified() == []  # markiert
        assert entry.id  # Eintrag existiert weiter (nicht geloescht)
    finally:
        runtime.stop()


def test_scheduler_reschedules_repeating_entry_instead_of_retiring(tmp_path, monkeypatch):
    """ADR-052: ein taeglicher Eintrag feuert, verschwindet aber nicht -
    er rueckt aufs naechste Vorkommen vor und bleibt meldbar. Die Nachricht
    traegt den ↻-Hinweis und nennt den ALTEN Zeitpunkt."""
    from memory.entries import is_past

    monkeypatch.setattr(jarvis_runtime, "_SCHEDULER_POLL_SECONDS", 0.05)
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    store = runtime._entry_store
    entry = store.add("Zusammenfassung", when="2099-01-01T19:54", repeat="täglich")
    data = store._read()
    data[0]["when"] = "2020-01-01T19:54"  # Zeit "verstreicht"
    store._write(data)

    fired = []
    got_one = threading.Event()

    def notifier(text):
        fired.append(text)
        got_one.set()

    runtime.set_notifier(notifier)
    runtime.start_scheduler()
    try:
        assert got_one.wait(timeout=2.0), "Scheduler hat nicht gefeuert"
        time.sleep(0.2)  # weitere Ticks: das NAECHSTE Vorkommen liegt in der
        assert len(fired) == 1  # Zukunft -> kein erneutes Feuern jetzt
        assert "↻ täglich" in fired[0]
        assert "2020" in fired[0] or "01.01.2020" in fired[0]  # alter Zeitpunkt genannt
        refreshed = store.list_open()[0]
        assert refreshed.id == entry.id          # NICHT verschwunden
        assert not is_past(refreshed.when)       # vorgerueckt
        assert refreshed.notified is False       # bleibt meldbar
    finally:
        runtime.stop()


def test_scheduler_does_not_start_without_notifier_or_impulses(tmp_path):
    # Ohne Notifier UND ohne Impuls-Engine (ADR-054) gibt es nichts zu tun.
    config = _make_config(tmp_path)
    config.impulses_enabled = False
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start_scheduler()
    assert runtime._scheduler_thread is None
    runtime.stop()  # darf ohne Scheduler nicht haengen/werfen


def test_scheduler_starts_for_impulses_without_notifier(tmp_path):
    """Endsystem-Kampagne (ADR-054): der Scheduler laeuft jetzt auch ohne
    Push-Kanal, sobald die Impuls-Engine aktiv ist (impulses_enabled)."""
    config = _make_config(tmp_path)
    config.impulses_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())
    try:
        runtime.start_scheduler()
        assert runtime._scheduler_thread is not None
        assert runtime._impulse_engine is not None
    finally:
        runtime.stop()


def test_stop_terminates_scheduler_promptly(tmp_path, monkeypatch):
    monkeypatch.setattr(jarvis_runtime, "_SCHEDULER_POLL_SECONDS", 30.0)  # langer Tick
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    runtime.set_notifier(lambda text: None)
    runtime.start_scheduler()
    runtime.start()

    runtime.stop()  # Stop-Event bricht den 30s-wait sofort ab

    assert runtime._scheduler_thread.is_alive() is False


def test_format_due_message_late_and_star():
    from memory.entries import Entry

    on_time = Entry(text="Zahnarzt", when="2099-07-10T09:00")
    assert "verspätet" not in jarvis_runtime._format_due_message(on_time)

    late = Entry(text="Zahnarzt", when="2020-01-01T09:00")
    msg = jarvis_runtime._format_due_message(late)
    assert "verspätet" in msg and "01.01.2020 um 09:00" in msg

    # Ganztaegig (reines Datum) gilt nie als verspaetet - Tages-Erinnerung.
    day = Entry(text="Audit", when="2020-01-01", important=True)
    msg_day = jarvis_runtime._format_due_message(day)
    assert "verspätet" not in msg_day and "⭐" in msg_day


def test_runtime_speech_delegates_to_confirmer_when_set():
    """ADR-045: mit gesetztem confirmer laufen say/listen ueber den Kanal;
    ohne bleibt exakt das alte fail-closed-Verhalten."""
    speech = _RuntimeSpeech()
    said = []

    class FakeConfirmer:
        def say(self, text):
            said.append(text)

        def listen(self):
            return "ja"

    speech.confirmer = FakeConfirmer()
    speech.say("Bestätigen?")
    assert said == ["Bestätigen?"]
    assert speech.listen() == "ja"

    speech.confirmer = None
    assert speech.listen() == ""  # fail-closed unveraendert


class _ConfirmAI(FakeAI):
    """Planer-Fake: jede Nachricht wird zum Test-Bestaetigungs-Command."""

    def get_plan(self, user_input, history):
        return Plan(intent="__test_confirm", raw_input=user_input, confidence=1.0)


class _NeedsConfirmation:
    name = "__test_confirm"
    requires_confirmation = True

    def execute(self, plan):
        from core.models import Result, Status

        return Result(status=Status.SUCCESS, message="Ausgefuehrt.")


def _run_confirmation_roundtrip(tmp_path, listen_answer):
    """Submit mit confirmer -> Executor-Rueckfrage -> Antwort -> Ergebnis."""
    from commands import REGISTRY

    REGISTRY["__test_confirm"] = _NeedsConfirmation()
    runtime = JarvisRuntime(_make_config(tmp_path), ai=_ConfirmAI())
    runtime.start()
    try:
        replies = []
        done = threading.Event()

        class Confirmer:
            questions: list = []

            def say(self, text):
                self.questions.append(text)

            def listen(self):
                return listen_answer

        confirmer = Confirmer()
        runtime.submit(
            "mach das", lambda t: (replies.append(t), done.set()), confirmer=confirmer
        )
        _wait(done)
        return replies, confirmer
    finally:
        runtime.stop()
        REGISTRY.pop("__test_confirm", None)


def test_confirmed_stufe2_command_executes_over_runtime(tmp_path):
    """ADR-045 end-to-end: Rueckfrage kommt ueber den confirmer, 'ja'
    bestaetigt, der Befehl laeuft - was vorher strukturell unmoeglich war."""
    replies, confirmer = _run_confirmation_roundtrip(tmp_path, listen_answer="ja")

    assert confirmer.questions, "Executor-Rueckfrage kam nicht ueber den confirmer"
    assert any("Ausgefuehrt" in r for r in replies)


def test_denied_stufe2_command_is_aborted_over_runtime(tmp_path):
    replies, _confirmer = _run_confirmation_roundtrip(tmp_path, listen_answer="nein")

    assert any("Abgebrochen" in r for r in replies)
    assert not any("Ausgefuehrt" in r for r in replies)


def test_confirmer_is_cleared_after_each_message(tmp_path):
    """Der confirmer gilt NUR fuer seine Nachricht - kein Leck in die
    naechste (die z. B. von PTT ohne Bestaetigungsweg kommt)."""
    replies, _ = _run_confirmation_roundtrip(tmp_path, listen_answer="ja")
    assert replies  # Verarbeitung lief

    # Nach der Verarbeitung ist die Runtime-Speech wieder fail-closed.
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    assert runtime._speech.confirmer is None


def test_shutdown_hook_is_wired_to_runtime(tmp_path):
    # Der stop_runtime-Befehl bekommt beim Runtime-Aufbau den Hook injiziert
    # (Verdrahtungsschicht) - genau wie delegate/plan ihr Backend.
    import commands.shutdown as shutdown_commands

    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())

    assert shutdown_commands._shutdown_hook == runtime._request_shutdown


def test_restart_hook_is_wired_to_runtime(tmp_path):
    # Der restart_runtime-Befehl bekommt beim Runtime-Aufbau den Hook
    # injiziert (Verdrahtungsschicht) - gleiches Muster wie stop_runtime.
    import commands.restart as restart_commands

    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())

    assert restart_commands._restart_hook == runtime._request_restart


def test_request_restart_spawns_successor_then_stops_worker(tmp_path):
    # _request_restart startet ERST den Nachfolger (injizierter Spawner),
    # dann Stop-Sentinel - der Worker beendet sich in der naechsten Runde.
    # Dashboard-Abloeser IMMER injizieren - der echte wuerde im Test den
    # realen dashboard.py-Prozess der Maschine killen (Scheibe 6).
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    spawned = []
    dashboards = []
    runtime._spawn_successor = lambda: (spawned.append(True), True)[1]
    runtime._restart_dashboard = lambda: dashboards.append(True)
    runtime.start()

    assert runtime._request_restart() is True
    runtime._worker.join(timeout=5.0)

    assert spawned == [True]
    assert dashboards == [True]  # Scheibe 6: Dashboard zieht mit um
    assert runtime._worker.is_alive() is False


def test_request_restart_survives_broken_dashboard_restart(tmp_path):
    """Scheibe 6, fail-safe: ein kaputter Dashboard-Abloeser verhindert
    den Runtime-Neustart NICHT (Dashboard ist Beiwerk)."""
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    runtime._spawn_successor = lambda: True
    runtime._restart_dashboard = lambda: (_ for _ in ()).throw(RuntimeError("kaputt"))
    runtime.start()

    assert runtime._request_restart() is True  # Neustart laeuft trotzdem
    runtime._worker.join(timeout=5.0)
    assert runtime._worker.is_alive() is False


def test_request_restart_skips_dashboard_when_spawn_fails(tmp_path):
    """Scheibe 6: scheitert der Nachfolger, bleibt auch das Dashboard
    unangetastet (kein halber Umzug)."""
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    dashboards = []
    runtime._spawn_successor = lambda: False
    runtime._restart_dashboard = lambda: dashboards.append(True)
    runtime.start()
    try:
        assert runtime._request_restart() is False
        assert dashboards == []
    finally:
        runtime.stop()


def test_terminate_running_dashboards_waits_then_kills(monkeypatch):
    """Zombie-Bug 2026-07-11: der Abloeser muss auf den Tod der alten
    dashboard.py-Prozesse WARTEN (wait_procs) und Nachzuegler hart killen,
    BEVOR der neue startet - sonst haelt der Alte den Port und der neue stirbt
    still am bind(). Nur dashboard.py-Prozesse, nicht die Runtime selbst."""
    events = []

    class NoSuchProcess(Exception):
        pass

    class AccessDenied(Exception):
        pass

    class FakeProc:
        def __init__(self, cmdline):
            self.info = {"cmdline": cmdline}
            self.terminated = False
            self.killed = False

        def terminate(self):
            self.terminated = True
            events.append(("terminate", tuple(self.info["cmdline"])))

        def kill(self):
            self.killed = True
            events.append(("kill", tuple(self.info["cmdline"])))

    dash1 = FakeProc(["pythonw.exe", "dashboard.py", "--no-browser"])
    dash2 = FakeProc(["python", "dashboard.py"])  # spielt den zaehen Nachzuegler
    other = FakeProc(["python", "jarvis_runtime.py"])

    def wait_procs(procs, timeout=None):
        events.append(("wait", timeout))
        alive = [p for p in procs if p is dash2 and not p.killed]
        gone = [p for p in procs if p not in alive]
        return gone, alive

    fake_psutil = types.SimpleNamespace(
        process_iter=lambda attrs=None: [dash1, dash2, other],
        wait_procs=wait_procs,
        NoSuchProcess=NoSuchProcess,
        AccessDenied=AccessDenied,
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    jarvis_runtime._terminate_running_dashboards(timeout=0.01)

    assert dash1.terminated is True and dash2.terminated is True
    assert other.terminated is False  # nur dashboard.py-Prozesse angefasst
    assert other.killed is False
    assert dash2.killed is True  # Nachzuegler hart nachgesetzt
    assert ("wait", 0.01) in events  # es wurde tatsaechlich gewartet
    # terminate kam VOR dem finalen kill - genau das schliesst die Race
    assert events.index(("terminate", ("python", "dashboard.py"))) < events.index(
        ("kill", ("python", "dashboard.py"))
    )


def test_terminate_running_dashboards_survives_without_psutil(monkeypatch):
    """Fail-safe: fehlt psutil (optional), wirft die Abloesung nicht -
    der Runtime-Neustart hat Vorrang."""
    monkeypatch.setitem(sys.modules, "psutil", None)  # import psutil -> ImportError
    jarvis_runtime._terminate_running_dashboards()  # darf nicht werfen


def test_request_restart_stays_alive_when_spawn_fails(tmp_path):
    # Scheitert der Nachfolger-Start, wird NICHT heruntergefahren -
    # lieber im Dienst bleiben als tot (und ehrlich False melden).
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    runtime._spawn_successor = lambda: False
    runtime.start()
    try:
        assert runtime._request_restart() is False
        runtime._worker.join(timeout=0.5)
        assert runtime._worker.is_alive() is True  # laeuft weiter
    finally:
        runtime.stop()


def test_fanout_notifier_reaches_all_and_survives_broken_channel():
    """Live-Befund 2026-07-10: Erinnerungs-Push kam nur in Telegram an -
    jetzt an alle Kanaele, und ein kaputter haelt die anderen nie auf."""
    received = []

    def broken(text):
        raise RuntimeError("Kanal weg")

    notify = jarvis_runtime._fanout_notifier([broken, received.append])
    notify("🔔 Erinnerung, Sir")

    assert received == ["🔔 Erinnerung, Sir"]


def test_lock_wait_seconds_reads_env(monkeypatch):
    # Warte-Flag: nur vom Vorgaenger gesetzt; ungesetzt/kaputt -> 0.0
    # (Doppelstart-Schutz bleibt hart).
    monkeypatch.delenv(jarvis_runtime.WAIT_FOR_LOCK_ENV, raising=False)
    assert jarvis_runtime._lock_wait_seconds() == 0.0
    monkeypatch.setenv(jarvis_runtime.WAIT_FOR_LOCK_ENV, "30")
    assert jarvis_runtime._lock_wait_seconds() == 30.0
    monkeypatch.setenv(jarvis_runtime.WAIT_FOR_LOCK_ENV, "quatsch")
    assert jarvis_runtime._lock_wait_seconds() == 0.0
    monkeypatch.setenv(jarvis_runtime.WAIT_FOR_LOCK_ENV, "-5")
    assert jarvis_runtime._lock_wait_seconds() == 0.0


def test_request_shutdown_stops_worker(tmp_path):
    # _request_shutdown legt nur das Stop-Sentinel in die Queue (kein
    # Selbst-Join) -> der Worker beendet sich sauber in der naechsten Runde.
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    runtime.start()

    runtime._request_shutdown()
    runtime._worker.join(timeout=5.0)

    assert runtime._worker.is_alive() is False


def test_stufe2_commands_are_fail_closed(tmp_path):
    """Sicherheitsstufe-2/3-Commands duerfen ueber die Runtime nicht
    ausgefuehrt werden - _RuntimeSpeech.listen() liefert "" (fail
    closed), der Executor bricht die Bestaetigung ab (ADR-025)."""
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("mach etwas kritisches", reply_callback)
        _wait(done)

        # shutdown_pc erfordert eine Bestaetigung - ohne Bestaetigungsweg
        # wird NICHT ausgefuehrt; die Antwort erklaert seit Spektakulaer #2
        # den Weg (Chat/Handy) statt kryptisch abzubrechen.
        assert "Bestätigung" in replies[0]
        assert "Chat oder am Handy" in replies[0]
    finally:
        runtime.stop()


def test_worker_does_not_die_on_unexpected_exception(tmp_path):
    """Ein unerwarteter Fehler bei der Verarbeitung einer Nachricht darf
    den Worker-Thread nicht beenden - nachfolgende Nachrichten muessen
    weiterhin verarbeitet werden (explizite Vorgabe, ADR-025)."""
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())

    original_process = runtime._process
    call_count = {"n": 0}

    def flaky_process(text, reply_callback, plan_filter=None, allow_async=False, confirmer=None, source=""):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulierter Absturz")
        original_process(text, reply_callback, plan_filter, allow_async, confirmer, source)

    runtime._process = flaky_process
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("erste nachricht (schlaegt fehl)", lambda t: None)
        runtime.submit("zweite nachricht", reply_callback)

        _wait(done)
        assert replies == ["Antwort auf: zweite nachricht"]
        assert runtime._worker.is_alive() is True
    finally:
        runtime.stop()


def test_broken_reply_callback_does_not_kill_worker(tmp_path):
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime.start()
    try:
        def broken_callback(text):
            raise RuntimeError("Kanal bereits weg")

        done = threading.Event()
        replies = []

        def ok_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("erste nachricht", broken_callback)
        runtime.submit("zweite nachricht", ok_callback)

        _wait(done)
        assert replies == ["Antwort auf: zweite nachricht"]
        assert runtime._worker.is_alive() is True
    finally:
        runtime.stop()


# --- Audit-Fixes: Fehlerrobustheit (P1a/P1b) ----------------------------------


def test_worker_exception_still_sends_error_reply(tmp_path):
    """Audit-Fix P1a: wirft _process, MUSS der Kanal trotzdem eine Antwort
    bekommen - sonst wartet ein synchroner Kanal ewig auf reply_callback."""
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    runtime._process = MagicMock(side_effect=RuntimeError("boom"))
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("irgendwas", reply_callback)
        _wait(done)
        assert "unerwarteter Fehler" in replies[0]
        assert runtime._worker.is_alive() is True
    finally:
        runtime._process = JarvisRuntime._process.__get__(runtime)  # Original zurueck
        runtime.stop()


def test_console_handle_returns_on_timeout_instead_of_hanging(monkeypatch, capsys):
    """Audit-Fix P1a: bleibt reply_callback aus, darf die Konsole nicht endlos
    haengen - nach dem Sicherheitsnetz-Timeout kehrt _handle zurueck."""
    monkeypatch.setattr(jarvis_runtime, "_CONSOLE_REPLY_TIMEOUT", 0.05)
    runtime = MagicMock()
    runtime.submit.side_effect = lambda *a, **k: None  # ruft reply_callback NIE
    channel = ConsoleDummyChannel(runtime)

    channel._handle("hallo")  # darf nicht haengen

    assert "keine Antwort erhalten" in capsys.readouterr().out


def test_async_delegation_pushes_error_on_backend_exception(tmp_path):
    """Audit-Fix P1b: wirft der Hintergrundlauf, folgt nach der Quittung ein
    finaler Fehler-Push (nicht nur ein Log-Eintrag)."""
    backend = RuntimeFakeBackend(raises=True)
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        replies = []
        lock = threading.Lock()
        two = threading.Event()

        def cb(text):
            with lock:
                replies.append(text)
                if len(replies) == 2:
                    two.set()

        runtime.submit("analysiere jarvis: frage", cb, allow_async=True)
        assert two.wait(timeout=5.0)
        assert replies[0].startswith("Ich kümmere mich darum, Sir")       # Quittung
        assert "fehlgeschlagen" in replies[1]             # finaler Fehler-Push
    finally:
        runtime.stop()


def test_runtime_speech_is_fail_closed():
    speech = _RuntimeSpeech()
    assert speech.listen() == ""
    speech.say("sollte nicht crashen")  # darf keine Exception werfen


def test_console_dummy_channel_forwards_input_and_prints_reply(monkeypatch, capsys):
    runtime = MagicMock()

    def fake_submit(text, reply_callback, source=""):
        reply_callback(f"Echo: {text}")

    runtime.submit.side_effect = fake_submit
    channel = ConsoleDummyChannel(runtime)

    inputs = iter(["hallo", "exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    channel.run()

    out = capsys.readouterr().out
    assert "Echo: hallo" in out
    runtime.submit.assert_called_once()


def test_console_dummy_channel_ignores_empty_input(monkeypatch):
    runtime = MagicMock()
    channel = ConsoleDummyChannel(runtime)

    inputs = iter(["", "   ", "exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    channel.run()

    runtime.submit.assert_not_called()


# --- setup_logging: Konsolen-Handler nur bei vorhandener Konsole (ADR-028) --
# logging.basicConfig() selbst wird gemockt statt den echten Root-Logger zu
# mutieren - vermeidet globalen Testzustand/Seiteneffekte auf andere Tests.


def test_setup_logging_adds_stream_handler_when_stderr_available(tmp_path, monkeypatch):
    monkeypatch.setattr(jarvis_runtime.sys, "stderr", MagicMock())
    captured = {}
    monkeypatch.setattr(
        jarvis_runtime.logging, "basicConfig", lambda **kwargs: captured.update(kwargs)
    )
    config = _make_config(tmp_path)

    jarvis_runtime.setup_logging(config)

    handlers = captured["handlers"]
    try:
        assert len(handlers) == 2
        assert isinstance(handlers[0], logging.FileHandler)
        assert isinstance(handlers[1], logging.StreamHandler)
        assert not isinstance(handlers[1], logging.FileHandler)
    finally:
        for h in handlers:
            h.close()


def test_setup_logging_skips_stream_handler_when_stderr_is_none(tmp_path, monkeypatch):
    """ADR-028: pythonw.exe (Jarvis-Eigenstart ohne Konsolenfenster) setzt
    sys.stderr auf None - ein StreamHandler wuerde beim ersten Log-Aufruf
    abstuerzen. Der FileHandler bleibt in jedem Fall aktiv."""
    monkeypatch.setattr(jarvis_runtime.sys, "stderr", None)
    captured = {}
    monkeypatch.setattr(
        jarvis_runtime.logging, "basicConfig", lambda **kwargs: captured.update(kwargs)
    )
    config = _make_config(tmp_path)

    jarvis_runtime.setup_logging(config)

    handlers = captured["handlers"]
    try:
        assert len(handlers) == 1
        assert isinstance(handlers[0], logging.FileHandler)
    finally:
        for h in handlers:
            h.close()


def test_dampen_http_loggers_protects_token_by_setting_warning():
    """Sicherheit: httpx/httpcore loggen sonst den Telegram-Request-URL
    inkl. Bot-Token auf INFO - _dampen_http_loggers() hebt sie auf WARNING,
    damit der Token nie in Logdatei/Konsole landet."""
    loggers = [logging.getLogger("httpx"), logging.getLogger("httpcore")]
    orig = [lg.level for lg in loggers]
    try:
        for lg in loggers:
            lg.setLevel(logging.INFO)
        jarvis_runtime._dampen_http_loggers()
        assert all(lg.level == logging.WARNING for lg in loggers)
    finally:
        for lg, lvl in zip(loggers, orig):
            lg.setLevel(lvl)


# --- Asynchrone Repo-Analyse (ADR-035) -------------------------------------


class DelegatingFakeAI:
    """Wie FakeAI, erkennt aber 'analysiere ...' als delegate_analysis."""

    def get_plan(self, user_input, history):
        text = user_input.lower()
        if text.startswith("analysiere"):
            return Plan(
                intent="delegate_analysis",
                target="jarvis",
                parameters={"question": "frage"},
                raw_input=user_input,
                confidence=1.0,
            )
        if text.startswith("plane"):
            return Plan(intent="plan_next_step", raw_input=user_input, confidence=1.0)
        return Plan(intent="chat", raw_input=user_input, confidence=1.0)

    def answer(self, user_input, history, long_term_summary=""):
        return f"Antwort auf: {user_input}"


class RuntimeFakeBackend:
    """AgentBackend-Ersatz fuer die Runtime-Tests. Kann blockieren (block),
    auf den Cancel warten (wait_cancel) oder werfen (raises)."""

    name = "TestBackend"

    def __init__(self, *, result=None, block=None, raises=False, wait_cancel=False):
        self.result = result or AgentResult(text="Analyse fertig.", ok=True, duration_seconds=0.1)
        self.block = block
        self.raises = raises
        self.wait_cancel = wait_cancel
        self.calls = 0
        self.started = threading.Event()

    def analyze(self, repo, question, limits, cancel_event=None, on_event=None, redirect=None):
        self.calls += 1
        self.started.set()
        if self.raises:
            raise RuntimeError("backend boom")
        if self.wait_cancel and cancel_event is not None:
            cancel_event.wait(timeout=5.0)
            return AgentResult(text="", ok=False, duration_seconds=0.1, detail="abgebrochen")
        if self.block is not None:
            self.block.wait(timeout=5.0)
        return self.result


def _delegation_runtime(tmp_path: Path, backend) -> JarvisRuntime:
    """Runtime mit freigegebenem Repo 'jarvis' und injiziertem Backend.
    configure() laeuft NACH der Runtime-Konstruktion (die den echten Backend
    verdrahtet) und ueberschreibt ihn mit dem Fake."""
    repo = tmp_path / "jarvis"
    repo.mkdir(exist_ok=True)
    config = _make_config(tmp_path)
    config.agent_repos = [{"alias": "jarvis", "path": str(repo)}]
    runtime = JarvisRuntime(config, ai=DelegatingFakeAI())
    delegate_commands.configure(config, backend=backend)
    return runtime


def test_cancel_delegation_sets_kill_switch(tmp_path):
    """Stopp-Knopf (ADR-056 Scheibe 2): cancel_delegation setzt den bestehenden
    Kill-Switch, aber nur wenn wirklich eine Delegation laeuft."""
    import threading as _th

    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    try:
        assert runtime.cancel_delegation() is False   # nichts aktiv
        ev = _th.Event()
        runtime._delegation_active = True
        runtime._delegation_cancel = ev
        assert runtime.cancel_delegation() is True
        assert ev.is_set()                            # Kill-Switch gesetzt
    finally:
        runtime.stop()


def test_redirect_delegation_only_when_active(tmp_path):
    """Umlenken (ADR-056 Scheibe 3): redirect_delegation stellt eine
    Kurskorrektur NUR zu, wenn gerade eine Delegation laeuft - sonst wuerde die
    Nachricht in einen kuenftigen Lauf einsickern (fail-safe abgelehnt)."""
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    try:
        assert runtime.redirect_delegation("mach's anders") is False  # nichts aktiv
        assert runtime._redirect_channel.drain() == []                # nichts abgelegt
        runtime._delegation_active = True
        assert runtime.redirect_delegation("  ") is False             # leer -> nein
        assert runtime.redirect_delegation("nimm lieber Y") is True   # zugestellt
        assert runtime._redirect_channel.drain() == ["nimm lieber Y"]
    finally:
        runtime.stop()


def test_async_delegation_sends_quittung_then_push(tmp_path):
    backend = RuntimeFakeBackend(
        result=AgentResult(text="Ergebnis XY.", ok=True, duration_seconds=0.1)
    )
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        replies = []
        lock = threading.Lock()
        two = threading.Event()

        def cb(text):
            with lock:
                replies.append(text)
                if len(replies) == 2:
                    two.set()

        runtime.submit("analysiere jarvis: frage", cb, allow_async=True)
        assert two.wait(timeout=5.0)
        assert replies[0].startswith("Ich kümmere mich darum, Sir")  # sofortige Quittung
        assert "Ergebnis XY." in replies[1]          # spaeterer Ergebnis-Push
    finally:
        runtime.stop()


def test_message_worker_free_during_delegation(tmp_path):
    """Der Nachrichten-Worker darf waehrend einer laufenden Delegation NICHT
    blockieren - ein normaler Chat muss sofort beantwortet werden."""
    block = threading.Event()
    backend = RuntimeFakeBackend(block=block)
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        chat_done = threading.Event()
        replies = []
        lock = threading.Lock()

        def cb(text):
            with lock:
                replies.append(text)
            if "Antwort auf: hallo" in text:
                chat_done.set()

        runtime.submit("analysiere jarvis: frage", cb, allow_async=True)
        assert backend.started.wait(timeout=5.0)  # Delegation laeuft (blockiert)
        runtime.submit("hallo", cb)                # normaler Chat
        assert chat_done.wait(timeout=5.0)         # trotz laufender Delegation
    finally:
        block.set()
        runtime.stop()


def test_second_delegation_while_busy_is_rejected(tmp_path):
    block = threading.Event()
    backend = RuntimeFakeBackend(block=block)
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        replies = []
        lock = threading.Lock()
        busy = threading.Event()

        def cb(text):
            with lock:
                replies.append(text)
            if "läuft bereits" in text:
                busy.set()

        runtime.submit("analysiere jarvis: frage1", cb, allow_async=True)
        assert backend.started.wait(timeout=5.0)
        runtime.submit("analysiere jarvis: frage2", cb, allow_async=True)
        assert busy.wait(timeout=5.0)
        assert backend.calls == 1  # zweite Delegation erreicht das Backend nicht
    finally:
        block.set()
        runtime.stop()


def test_stop_cancels_running_delegation(tmp_path):
    backend = RuntimeFakeBackend(wait_cancel=True)
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()

    runtime.submit("analysiere jarvis: frage", lambda t: None, allow_async=True)
    assert backend.started.wait(timeout=5.0)

    runtime.stop()  # setzt Kill-Switch -> Backend kehrt zurueck -> Adapter-Lauf endet

    # H3 (§9-Migration): die Delegation laeuft im TaskService-Worker, nicht
    # mehr in einem eigenen Thread - nach stop() ist der Lauf beendet und
    # der Worker mit begrenztem Join eingesammelt.
    assert runtime._delegation_active is False
    worker = runtime.task_service._worker
    assert worker is not None and worker.is_alive() is False


def test_delegation_without_allow_async_runs_synchronously(tmp_path):
    """Regressionsanker (ADR-035 Entscheidung 5): ohne allow_async laeuft die
    Analyse synchron im Nachrichten-Worker - genau eine Antwort, keine
    separate Quittung."""
    backend = RuntimeFakeBackend(
        result=AgentResult(text="Sync-Ergebnis.", ok=True, duration_seconds=0.1)
    )
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        replies = []
        done = threading.Event()

        def cb(text):
            replies.append(text)
            done.set()

        runtime.submit("analysiere jarvis: frage", cb)  # allow_async=False (Default)
        assert done.wait(timeout=5.0)
        assert len(replies) == 1
        assert "Sync-Ergebnis." in replies[0]
    finally:
        runtime.stop()


def test_busy_flag_reset_after_background_exception(tmp_path):
    """Wirft der Hintergrundlauf, muss der Busy-Slot im finally freigegeben
    werden - eine nachfolgende Delegation darf nicht dauerhaft 'busy' sein."""
    backend = RuntimeFakeBackend(raises=True)
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        replies = []
        lock = threading.Lock()

        def cb(text):
            with lock:
                replies.append(text)

        runtime.submit("analysiere jarvis: frage1", cb, allow_async=True)
        assert backend.started.wait(timeout=5.0)
        # Ersten (werfenden) Adapter-Lauf sauber abwarten (H3: kein eigener
        # Thread mehr - das Busy-Flag ist die Wahrheit).
        deadline = time.time() + 5.0
        while runtime._delegation_active and time.time() < deadline:
            time.sleep(0.02)
        assert runtime._delegation_active is False

        backend.started.clear()
        runtime.submit("analysiere jarvis: frage2", cb, allow_async=True)
        # Zweite Delegation wird angenommen und erreicht das Backend erneut.
        assert backend.started.wait(timeout=5.0)
        deadline = time.time() + 5.0
        while backend.calls < 2 and time.time() < deadline:
            time.sleep(0.02)
        assert backend.calls == 2
        assert not any("läuft bereits" in r for r in replies)
    finally:
        runtime.stop()


def test_async_delegation_writes_consistent_history(tmp_path):
    backend = RuntimeFakeBackend(
        result=AgentResult(text="Ergebnis.", ok=True, duration_seconds=0.1)
    )
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        replies = []
        lock = threading.Lock()
        two = threading.Event()

        def cb(text):
            with lock:
                replies.append(text)
                if len(replies) == 2:
                    two.set()

        runtime.submit("analysiere jarvis: frage", cb, allow_async=True)
        assert two.wait(timeout=5.0)

        history = runtime.memory.get_history()
        assert [m.role for m in history] == ["user", "assistant"]
        assert history[0].content == "analysiere jarvis: frage"
        assert "Ergebnis." in history[1].content
        # Die transiente Quittung wird NICHT persistiert.
        assert all("Ich kümmere mich darum" not in m.content for m in history)
    finally:
        runtime.stop()


def test_async_plan_next_step_reuses_the_async_path(tmp_path):
    """Ein ZWEITER long_running-Command (plan_next_step) nutzt denselben
    Async-Pfad wie delegate_analysis - Quittung + Push, ohne Runtime-Aenderung."""
    import commands.plan as plan_commands

    backend = RuntimeFakeBackend(
        result=AgentResult(text="# Titel\n## Empfehlung\nScheibe X.", ok=True, duration_seconds=0.1)
    )
    config = _make_config(tmp_path)
    runtime = JarvisRuntime(config, ai=DelegatingFakeAI())
    plan_commands.configure(config, backend=backend)  # echten Backend durch Fake ersetzen
    runtime.start()
    try:
        replies = []
        lock = threading.Lock()
        two = threading.Event()

        def cb(text):
            with lock:
                replies.append(text)
                if len(replies) == 2:
                    two.set()

        runtime.submit("plane den nächsten schritt", cb, allow_async=True)
        assert two.wait(timeout=5.0)
        assert replies[0].startswith("Ich kümmere mich darum, Sir")   # generische Quittung
        assert "Scheibe X." in replies[1]             # Push mit dem Vorschlag
    finally:
        runtime.stop()


def test_async_and_sync_history_not_lost_under_concurrency(tmp_path):
    """RLock im MemoryStore: Delegations-Thread und Nachrichten-Worker
    schreiben gleichzeitig History - kein Eintrag darf verloren gehen."""
    block = threading.Event()
    backend = RuntimeFakeBackend(
        block=block, result=AgentResult(text="Analyse.", ok=True, duration_seconds=0.1)
    )
    runtime = _delegation_runtime(tmp_path, backend)
    runtime.start()
    try:
        replies = []
        lock = threading.Lock()
        push = threading.Event()
        chat = threading.Event()

        def cb(text):
            with lock:
                replies.append(text)
            if "Analyse." in text:
                push.set()
            if "Antwort auf: hallo" in text:
                chat.set()

        runtime.submit("analysiere jarvis: frage", cb, allow_async=True)
        assert backend.started.wait(timeout=5.0)  # Delegation laeuft (blockiert)
        runtime.submit("hallo", cb)                # paralleler Chat schreibt History
        assert chat.wait(timeout=5.0)
        block.set()                                # Delegation abschliessen
        assert push.wait(timeout=5.0)

        contents = [m.content for m in runtime.memory.get_history()]
        assert len(contents) == 4  # 2x Chat + 2x Delegation, nichts verloren
        assert "analysiere jarvis: frage" in contents
        assert "hallo" in contents
    finally:
        block.set()
        runtime.stop()


# --- Wake-Bestaetigungs-Validierung (Live-Befund 2026-07-10, 2. Runde) ------

def _wav_bytes(seconds: float, rate: int = 24_000) -> bytes:
    """Erzeugt ein stilles, aber strukturell valides WAV gegebener Dauer."""
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buffer.getvalue()


def test_wav_seconds_measures_duration_and_rejects_garbage():
    """Die alte Byte-Pruefung liess einen 0,3-s-Synthese-Stumpf durch (15 kB
    'RIFF...' >= 1000 Bytes) - der war dann die ganze Session stumm. Jetzt
    zaehlt die SPIELDAUER; Muell ergibt 0.0 statt einer Exception."""
    assert abs(jarvis_runtime._wav_seconds(_wav_bytes(1.2)) - 1.2) < 0.01
    assert jarvis_runtime._wav_seconds(_wav_bytes(0.3)) < jarvis_runtime._MIN_ACK_SECONDS
    assert jarvis_runtime._wav_seconds(b"RIFF" + b"\x00" * 20_000) == 0.0
    assert jarvis_runtime._wav_seconds(b"") == 0.0
    # Der Stumpf aus dem Live-Log (~15 kB bei 24 kHz = ~0,31 s) faellt durch:
    assert jarvis_runtime._wav_seconds(_wav_bytes(0.31)) < jarvis_runtime._MIN_ACK_SECONDS


# --- Live-Ablauf-Timeline (UI-Zielbild 2026-07-10) ---------------------------

def test_timeline_events_carry_stages_but_no_content(tmp_path):
    """Die Timeline meldet Plan/Schritt/Antwort mit Intents, Status und
    Dauern - aber NIE Nachrichteninhalte (dieselbe Disziplin wie die Logs)."""
    runtime = JarvisRuntime(_make_config(tmp_path), ai=DelegatingFakeAI())
    events: list[dict] = []
    runtime.timeline_listener = events.append

    runtime._process_inner("geheime plauderei", reply_callback=lambda _: None)

    stages = [e["stage"] for e in events]
    # Live-Fortschritt (PO-Befund 10.07.): Schritte melden Beginn UND Ende.
    assert stages == ["plan", "schritt_start", "schritt", "antwort"]
    assert events[0]["intents"] == ["chat"]
    assert events[0]["confidence"] == 1.0
    assert events[1]["intent"] == "chat" and events[1]["index"] == 0
    assert events[2]["intent"] == "chat" and events[2]["ok"] is True
    assert events[2]["target"] == ""  # Ziel-Feld vorhanden (leer bei chat)
    assert events[3]["chars"] > 0 and "seconds" in events[3]
    # Alle Events derselben Anfrage tragen dieselbe job-Nummer:
    assert len({e["job"] for e in events}) == 1
    # Kein Inhalt in keinem Event:
    for event in events:
        assert "geheime" not in str(event).lower()


def test_timeline_reports_delegation_dispatch(tmp_path):
    backend = RuntimeFakeBackend()
    runtime = _delegation_runtime(tmp_path, backend)
    events: list[dict] = []
    runtime.timeline_listener = events.append
    replies: list[str] = []
    try:
        runtime._process_inner(
            "analysiere jarvis: frage", reply_callback=replies.append, allow_async=True
        )
        assert backend.started.wait(timeout=5.0)
    finally:
        runtime.stop()

    assert any(e["stage"] == "delegation" and e["intent"] == "delegate_analysis"
               and e["target"] == "jarvis" for e in events)
    # Abschluss-Haken nach dem Hintergrund-Lauf (runtime.stop joint den
    # Thread), mit derselben job-Nummer wie der Start:
    delegation = next(e for e in events if e["stage"] == "delegation")
    done = [e for e in events if e["stage"] == "schritt" and e.get("ok") is True]
    assert done and done[0]["job"] == delegation["job"]
    assert done[0]["index"] == 0


def test_broken_timeline_listener_never_breaks_processing(tmp_path):
    runtime = JarvisRuntime(_make_config(tmp_path), ai=DelegatingFakeAI())
    runtime.timeline_listener = lambda event: (_ for _ in ()).throw(RuntimeError("UI weg"))
    replies: list[str] = []

    runtime._process_inner("hallo", reply_callback=replies.append)

    assert replies and "Antwort auf" in replies[0]  # Verarbeitung lief durch


# --- Async-Dispatch erzwingt Bestaetigung (Sicherheits-Befund 2026-07-10) ---

class _FakeLongRunningStufe2:
    """long_running + requires_confirmation - wie delegate_work (ADR-050)."""

    name = "fake_long"
    requires_confirmation = True
    long_running = True

    def __init__(self):
        self.ran = threading.Event()

    def execute(self, plan):
        raise AssertionError("Async-Pfad muss run_async nutzen")

    def run_async(self, plan, cancel_event=None):
        from core.models import Result, Status

        self.ran.set()
        return Result(status=Status.SUCCESS, message="erledigt")


class _FakeLongAI:
    def get_plan(self, user_input, history):
        return Plan(intent="fake_long", target="jkc", raw_input=user_input, confidence=1.0)

    def answer(self, user_input, history, long_term_summary=""):
        return "x"


def test_async_dispatch_asks_stufe2_confirmation_before_run(tmp_path, monkeypatch):
    """Der Async-Dispatch rief run_async DIREKT auf und umging
    requires_confirmation (live: delegate_work startete ohne Rueckfrage,
    nur der Dirty-Tree-Waechter fing es ab). Jetzt: Bestaetigung VOR dem
    Dispatch, ueber dieselbe Logik wie im Executor."""
    from unittest.mock import MagicMock

    from commands import REGISTRY

    cmd = _FakeLongRunningStufe2()
    monkeypatch.setitem(REGISTRY, "fake_long", cmd)
    runtime = JarvisRuntime(_make_config(tmp_path), ai=_FakeLongAI())
    runtime._speech = MagicMock()
    runtime._speech.listen.return_value = "ja"
    replies: list[str] = []
    try:
        runtime._process_inner("erledige was", reply_callback=replies.append, allow_async=True)
        assert cmd.ran.wait(timeout=5.0)  # nach "ja" laeuft die Delegation
    finally:
        runtime.stop()

    say_text = runtime._speech.say.call_args.args[0]
    # Rueckfrage nennt die Aktion (unbekannter Fake-Intent ehrlich roh) + das
    # Ziel und sagt, was Ja/Nein bewirken (Live-Reibung 13.07. spät).
    assert "fake_long «jkc»" in say_text
    assert "dann passiert nichts" in say_text
    assert any("kümmere" in r for r in replies)  # Quittung kam NACH dem Ja


def test_async_dispatch_aborts_without_confirmation(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from commands import REGISTRY

    cmd = _FakeLongRunningStufe2()
    monkeypatch.setitem(REGISTRY, "fake_long", cmd)
    runtime = JarvisRuntime(_make_config(tmp_path), ai=_FakeLongAI())
    runtime._speech = MagicMock()
    runtime._speech.listen.return_value = "nein"
    replies: list[str] = []
    try:
        runtime._process_inner("erledige was", reply_callback=replies.append, allow_async=True)
    finally:
        runtime.stop()

    assert not cmd.ran.is_set()  # kein Lauf ohne Bestaetigung
    # Kundendeutsch statt Alttext (Chatlog-Review 14.07.): ehrlich + folgenlos.
    assert any("ich lasse es" in r for r in replies)
    assert not any("Abgebrochen" in r for r in replies)


# --- Antwort-Composer im Schatten (ADR-065 Saeule A, Phase A1) ----------


class _ComposeAI(FakeAI):
    """FakeAI mit generate() - fuer den Composer-Schatten."""

    def __init__(self):
        self.generate_calls = []
        self.models = []

    def generate(self, system, user_text, *, json_mode=False, max_tokens=None, model=None):
        self.generate_calls.append((system, user_text))
        self.models.append(model)
        return "KOMPONIERTE ANTWORT"


def test_compose_shadow_off_by_default_does_not_call_generate(tmp_path):
    ai = _ComposeAI()
    runtime = JarvisRuntime(_make_config(tmp_path), ai=ai)

    runtime._process_inner("hallo", lambda _m: None)

    assert ai.generate_calls == []   # Schatten aus -> kein Composer-Call


def test_compose_shadow_on_runs_but_still_shows_template(tmp_path):
    config = _make_config(tmp_path)
    config.response_compose_shadow = True
    ai = _ComposeAI()
    runtime = JarvisRuntime(config, ai=ai)
    replies = []

    runtime._process_inner("hallo", replies.append)

    assert ai.generate_calls                          # Composer lief (Schatten)
    assert "KOMPONIERTE ANTWORT" not in replies[0]    # aber NICHT gezeigt
    assert replies[0].startswith("Antwort auf:")      # gezeigt bleibt die Schablone


def test_compose_shadow_failure_never_breaks_live_path(tmp_path):
    config = _make_config(tmp_path)
    config.response_compose_shadow = True

    class _BoomAI(FakeAI):
        def generate(self, system, user_text, *, json_mode=False, max_tokens=None, model=None):
            raise RuntimeError("compose down")

    runtime = JarvisRuntime(config, ai=_BoomAI())
    replies = []

    runtime._process_inner("hallo", replies.append)   # darf NICHT werfen

    assert replies[0].startswith("Antwort auf:")


# --- Antwort-Composer ZEIGEN (ADR-065 Saeule A, Phase A2) ---------------


class _TwoStepPlanner:
    """Erzwingt einen Multi-Step-Plan (zwei chat-Schritte) fuer die A2-Tests."""

    def plan(self, text, history):
        return [Plan(intent="chat", raw_input=text), Plan(intent="chat", raw_input=text)]


def test_multistep_shows_composed_reply(tmp_path):
    config = _make_config(tmp_path)
    config.response_compose_multistep = True
    ai = _ComposeAI()
    runtime = JarvisRuntime(config, ai=ai)
    runtime.planner = _TwoStepPlanner()
    replies = []

    runtime._process_inner("mach zwei dinge", replies.append)

    assert ai.generate_calls                       # Composer lief
    assert replies[0] == "KOMPONIERTE ANTWORT"     # komponierte Antwort GEZEIGT (statt "✓ | ✓")
    assert ai.models == ["gpt-4o-mini"]            # Composer auf dem guenstigen Modell (ADR-065)


def test_singlestep_keeps_template_and_skips_composer(tmp_path):
    config = _make_config(tmp_path)
    config.response_compose_multistep = True       # nur Multi-Step betroffen
    ai = _ComposeAI()
    runtime = JarvisRuntime(config, ai=ai)
    replies = []

    runtime._process_inner("hallo", replies.append)   # ein chat-Schritt

    assert replies[0].startswith("Antwort auf:")   # Schablone bleibt
    assert ai.generate_calls == []                 # Composer gar nicht aufgerufen


def test_multistep_failsafe_keeps_template_on_composer_error(tmp_path):
    config = _make_config(tmp_path)
    config.response_compose_multistep = True

    class _BoomAI(FakeAI):
        def generate(self, system, user_text, *, json_mode=False, max_tokens=None, model=None):
            raise RuntimeError("compose down")

    runtime = JarvisRuntime(config, ai=_BoomAI())
    runtime.planner = _TwoStepPlanner()
    replies = []

    runtime._process_inner("mach zwei dinge", replies.append)   # darf NICHT werfen

    assert "Antwort auf:" in replies[0]            # Composer-Fehler -> Schablone


def test_should_compose_show_multistep_only_on_success(tmp_path):
    config = _make_config(tmp_path)
    config.response_compose_multistep = True
    rt = JarvisRuntime(config, ai=_ComposeAI())
    steps = [Plan(intent="add_to_list"), Plan(intent="add_entry")]
    ok = [Result(status=Status.SUCCESS, message="a"), Result(status=Status.SUCCESS, message="b")]

    assert rt._should_compose_show(steps, ok) is True
    assert rt._should_compose_show(steps[:1], ok[:1]) is False      # Einzelschritt -> Schablone
    failed = [Result(status=Status.SUCCESS, message="a"), Result(status=Status.FAILED, message="x")]
    assert rt._should_compose_show(steps, failed) is False          # Fehler -> klare Schablone


def test_should_compose_show_intent_whitelist(tmp_path):
    config = _make_config(tmp_path)
    config.response_compose_intents = ["propose_ideas"]
    rt = JarvisRuntime(config, ai=_ComposeAI())
    ok = [Result(status=Status.SUCCESS, message="ideen")]

    assert rt._should_compose_show([Plan(intent="propose_ideas")], ok) is True
    assert rt._should_compose_show([Plan(intent="get_news")], ok) is False


# --- Sitzungs-Zusammenfassung (ADR-065 Saeule B1) -----------------------


class _SummarizeAI(FakeAI):
    """FakeAI mit generate() - fuer die Sitzungs-Zusammenfassung."""

    def __init__(self):
        self.gen = []

    def generate(self, system, user_text, *, json_mode=False, max_tokens=None, model=None):
        self.gen.append((system, user_text, model))
        return "ZUSAMMENFASSUNG"


def test_session_summary_folds_old_history_when_enabled(tmp_path):
    config = _make_config(tmp_path)
    config.session_summary_enabled = True
    config.max_history_entries = 200          # genug Puffer fuer Ueberlauf (real: 200)
    ai = _SummarizeAI()
    runtime = JarvisRuntime(config, ai=ai)
    for i in range(30):
        runtime.memory.append_history(
            Message(role="user" if i % 2 == 0 else "assistant", content=f"m{i}"))

    runtime._process_inner("neue frage", lambda _m: None)

    assert runtime._session_summary.summary() == "ZUSAMMENFASSUNG"
    assert ai.gen and ai.gen[0][2] == "gpt-4o-mini"   # guenstiges Modell


def test_session_summary_off_by_default(tmp_path):
    ai = _SummarizeAI()
    runtime = JarvisRuntime(_make_config(tmp_path), ai=ai)
    for i in range(30):
        runtime.memory.append_history(Message(role="user", content=f"m{i}"))

    runtime._process_inner("x", lambda _m: None)

    assert runtime._session_summary.summary() == ""
    assert ai.gen == []


# --- Semantischer Abruf (ADR-065 Saeule B2) -----------------------------

from memory.semantic import SemanticIndex   # noqa: E402

_SEM_VOCAB = ["kaffee", "schwarz", "montag", "report", "python", "backup", "mutter"]


def _sem_fake_embed(texts):
    return [[1.0 if w in t.lower() else 0.0 for w in _SEM_VOCAB] for t in texts]


def test_semantic_sync_indexes_facts_when_enabled(tmp_path):
    config = _make_config(tmp_path)
    config.semantic_recall_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime._semantic = SemanticIndex(tmp_path / "sem.json", _sem_fake_embed)
    runtime.long_term.remember("Ich trinke meinen Kaffee schwarz")

    n = runtime.run_semantic_sync()

    assert n >= 1
    hits = runtime._semantic.search("Wie trinke ich meinen Kaffee?", k=1)
    assert hits and "Kaffee schwarz" in hits[0]["text"]


def test_semantic_sync_off_by_default_does_nothing(tmp_path):
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    runtime.long_term.remember("Ich trinke meinen Kaffee schwarz")

    assert runtime.run_semantic_sync() == 0


# --- Proaktiver Bau-Vorschlag (ADR-067, Koenigsdisziplin) ---------------

class _BuildAI(FakeAI):
    """FakeAI mit generate() - liefert einen gueltigen Bau-Vorschlag."""

    def generate(self, system, user_text, *, json_mode=False, max_tokens=None, model=None):
        return ("Mir ist aufgefallen: du prüfst oft das Wetter. Ich koennte dir "
                "«wetter-cli» bauen, das dir das Wetter im Terminal zeigt. Sag "
                "«Bau mir wetter-cli», dann lege ich los.")


def test_run_build_suggestion_stores_when_enabled(tmp_path):
    import json

    config = _make_config(tmp_path)
    config.build_offers_enabled = True
    config.episodic_memory_enabled = True
    runtime = JarvisRuntime(config, ai=_BuildAI())

    text = runtime.run_build_suggestion()

    assert "Bau mir wetter-cli" in text
    data = json.loads((config.memory_dir / "build_suggestion.json").read_text(encoding="utf-8"))
    assert data["done"] is False
    assert "wetter-cli" in data["text"]


def test_run_build_suggestion_off_by_default_returns_empty(tmp_path):
    runtime = JarvisRuntime(_make_config(tmp_path), ai=_BuildAI())  # build_offers_enabled Default False

    assert runtime.run_build_suggestion() == ""
    assert not (runtime._build_suggestion_path).exists()


def test_build_suggestion_surfaced_exactly_once(tmp_path):
    from core.fileio import write_json_atomic

    config = _make_config(tmp_path)
    config.build_offers_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())
    write_json_atomic(runtime._build_suggestion_path,
                      {"text": "Ich koennte dir «x» bauen. Sag «Bau mir x».",
                       "done": False, "generated": "2030-01-01"})

    first = []
    runtime._process_inner("hallo", first.append)
    assert any("Bau mir x" in m for m in first)

    second = []
    runtime._process_inner("noch was", second.append)
    assert not any("Bau mir x" in m for m in second)   # nur EINMAL


def test_build_suggestion_not_surfaced_when_disabled(tmp_path):
    from core.fileio import write_json_atomic

    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())  # Default AUS
    write_json_atomic(runtime._build_suggestion_path,
                      {"text": "Sag «Bau mir x».", "done": False})

    out = []
    runtime._process_inner("hallo", out.append)
    assert not any("Bau mir x" in m for m in out)


# --- "Antworten + gleich tun" (ADR-068) ---------------------------------

class _RememberAI(FakeAI):
    """Routet jede Eingabe auf remember_fact und kann komponieren (generate)."""

    def __init__(self):
        self.last_system = ""

    def get_plan(self, user_input, history):
        return Plan(intent="remember_fact", target="mag mehr Kontext",
                    raw_input=user_input, confidence=1.0)

    def generate(self, system, user_text, *, json_mode=False, max_tokens=None, model=None):
        self.last_system = system
        return "COMPOSED: Ja, das ist sinnvoll — gemerkt, Sir."


def test_answer_and_act_composes_on_question(tmp_path):
    config = _make_config(tmp_path)
    config.answer_and_act_enabled = True
    ai = _RememberAI()
    runtime = JarvisRuntime(config, ai=ai)

    replies = []
    runtime._process_inner("ist das nicht sinnvoll?", replies.append)

    assert any("COMPOSED" in m for m in replies)                  # Frage beantwortet + Tat
    assert "rueckgaengig" in ai.last_system.lower()               # Undo-Weisung kam an


def test_answer_and_act_off_keeps_bare_template(tmp_path):
    config = _make_config(tmp_path)  # answer_and_act_enabled Default AUS
    ai = _RememberAI()
    runtime = JarvisRuntime(config, ai=ai)

    replies = []
    runtime._process_inner("ist das nicht sinnvoll?", replies.append)

    assert not any("COMPOSED" in m for m in replies)
    assert any("Gemerkt" in m for m in replies)                   # nackte Schablone


def test_answer_and_act_without_question_keeps_template(tmp_path):
    config = _make_config(tmp_path)
    config.answer_and_act_enabled = True
    ai = _RememberAI()
    runtime = JarvisRuntime(config, ai=ai)

    replies = []
    runtime._process_inner("merk dir das", replies.append)        # kein '?'

    assert not any("COMPOSED" in m for m in replies)
    assert any("Gemerkt" in m for m in replies)


def test_prepare_meeting_bundles_person_and_related_tasks(tmp_path, monkeypatch):
    """Plan C4: die Meeting-Prep buendelt Termin + bekannte Person + verwandte
    offene Aufgaben zu einer Karte (deterministisch, read-only)."""
    import commands.calendar as calendar_commands

    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    runtime._people.remember("Anna", "deine Steuerberaterin")
    runtime._entry_store.add(text="Steuerunterlagen sortieren", when="")
    monkeypatch.setattr(calendar_commands, "read_agenda",
                        lambda when: [{"subject": "Steuerberater", "start": "2026-07-14T09:00:00"}])

    out = runtime.prepare_meeting("mit Anna")

    assert "Steuerberater" in out
    assert "Anna" in out                                   # Person gezogen
    assert "Steuerunterlagen sortieren" in out             # verwandte Aufgabe


def test_prepare_meeting_no_events(tmp_path, monkeypatch):
    import commands.calendar as calendar_commands
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    monkeypatch.setattr(calendar_commands, "read_agenda", lambda when: [])
    assert "keinen Termin" in runtime.prepare_meeting("")


def test_impulse_push_when_enabled_and_notifier(tmp_path):
    """Plan F: bei eingeschaltetem Push + gesetztem Notifier geht ein neuer
    Impuls (geschwaerzt) an den Besitzer."""
    config = _make_config(tmp_path)
    config.impulse_push_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())
    sent = []
    runtime.set_notifier(sent.append)

    runtime._push_impulse({"title": "Unwetter", "detail": "Hagel ab 16 Uhr"})

    assert sent == ["Unwetter\nHagel ab 16 Uhr"]


def test_impulse_push_off_by_default(tmp_path):
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())  # Default AUS
    sent = []
    runtime.set_notifier(sent.append)

    runtime._push_impulse({"title": "Unwetter", "detail": "Hagel"})

    assert sent == []


def test_impulse_push_noop_without_notifier(tmp_path):
    config = _make_config(tmp_path)
    config.impulse_push_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())  # kein Notifier gesetzt
    runtime._push_impulse({"title": "Unwetter", "detail": "Hagel"})  # darf nicht werfen


def test_reversible_answer_directive_guards(tmp_path):
    from core.models import Result, Status

    config = _make_config(tmp_path)
    config.answer_and_act_enabled = True
    runtime = JarvisRuntime(config, ai=_RememberAI())
    ok = [Result(status=Status.SUCCESS, message="Gemerkt")]
    rem = [Plan(intent="remember_fact", target="x")]

    assert runtime._reversible_answer_directive("ist das sinnvoll?", rem, ok)      # greift
    assert not runtime._reversible_answer_directive("merk dir das", rem, ok)       # keine Frage
    # nicht-umkehrbarer Intent -> nie automatisch handeln+antworten
    assert not runtime._reversible_answer_directive(
        "loeschen?", [Plan(intent="shutdown_pc", target=None)], ok)
    # fehlgeschlagene Aktion -> keine Erfolgs-Erzaehlung
    assert not runtime._reversible_answer_directive(
        "sinnvoll?", rem, [Result(status=Status.FAILED, message="nix")])


def test_semantic_recall_injects_relevant_memory_into_context(tmp_path, monkeypatch):
    config = _make_config(tmp_path)
    config.semantic_recall_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime._semantic = SemanticIndex(tmp_path / "sem.json", _sem_fake_embed)
    runtime._semantic.add_texts([("Ich trinke meinen Kaffee schwarz", "fakt")])

    captured = {}
    real_run = runtime.executor.run

    def spy(steps, history, long_term_summary, on_step=None):
        captured["lts"] = long_term_summary
        return real_run(steps, history, long_term_summary, on_step=on_step)

    monkeypatch.setattr(runtime.executor, "run", spy)
    runtime._process_inner("Wie trinke ich eigentlich meinen Kaffee?", lambda _m: None)

    assert "Relevante Erinnerungen" in captured["lts"]
    assert "Kaffee schwarz" in captured["lts"]


def test_semantic_recall_skips_trivial_input(tmp_path, monkeypatch):
    config = _make_config(tmp_path)
    config.semantic_recall_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())
    called = {"n": 0}
    runtime._semantic = SemanticIndex(tmp_path / "sem.json",
                                      lambda texts: called.__setitem__("n", called["n"] + 1) or _sem_fake_embed(texts))
    runtime._semantic.add_texts([("Kaffee schwarz", "fakt")])
    before = called["n"]

    runtime._process_inner("ja", lambda _m: None)   # 2 Woerter -> kein Abruf

    assert called["n"] == before   # kein zusaetzlicher Embed-Aufruf fuer triviale Eingabe


# --- Personen-Gedaechtnis (ADR-066 Stein 1) -----------------------------


def test_people_context_is_injected_when_name_mentioned(tmp_path, monkeypatch):
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    runtime._people.remember("Anna", "meine Steuerberaterin")

    captured = {}
    real_run = runtime.executor.run

    def spy(steps, history, long_term_summary, on_step=None):
        captured["lts"] = long_term_summary
        return real_run(steps, history, long_term_summary, on_step=on_step)

    monkeypatch.setattr(runtime.executor, "run", spy)
    runtime._process_inner("Habe ich morgen ein Meeting mit Anna?", lambda _m: None)

    assert "Personen im Kontext" in captured["lts"]
    assert "Steuerberaterin" in captured["lts"]


def test_people_context_absent_when_no_known_name(tmp_path, monkeypatch):
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    runtime._people.remember("Anna", "meine Steuerberaterin")

    captured = {}
    real_run = runtime.executor.run

    def spy(steps, history, long_term_summary, on_step=None):
        captured["lts"] = long_term_summary
        return real_run(steps, history, long_term_summary, on_step=on_step)

    monkeypatch.setattr(runtime.executor, "run", spy)
    runtime._process_inner("Wie ist das Wetter?", lambda _m: None)

    assert "Personen im Kontext" not in captured["lts"]


# --- Uebergreifende proaktive Vorbereitung (ADR-066 Stein 2) -------------


def test_run_proactive_check_enriches_with_people_and_tasks(tmp_path, monkeypatch):
    from datetime import date, datetime

    import commands.calendar as calendar_commands

    runtime, _ = _proactive_runtime(tmp_path)
    runtime._people.remember("Anna", "meine Steuerberaterin")
    runtime._entry_store.add("Steuerunterlagen sortieren", when="2030-01-02T08:00")
    monkeypatch.setattr(calendar_commands, "read_agenda", lambda day: [
        {"subject": "Termin mit Anna vom Steuerberater",
         "start": "2030-01-02T09:00:00", "end": "2030-01-02T10:00:00", "all_day": False},
    ])

    payload = runtime.run_proactive_check(date(2030, 1, 2), now=datetime(2030, 1, 1, 20, 0))

    assert payload is not None
    assert "Anna" in payload["nudge"]                       # Person verknuepft
    assert "Steuerunterlagen sortieren" in payload["nudge"]  # verwandte Aufgabe verknuepft


# --- Selbst-Verbesserung (ADR-066 Stein 3) ------------------------------


def test_run_self_review_writes_journal_when_enabled(tmp_path):
    from datetime import date

    config = _make_config(tmp_path)
    config.episodic_memory_enabled = True
    config.self_review_enabled = True
    runtime = JarvisRuntime(config, ai=_SummarizeAI())   # generate() -> "ZUSAMMENFASSUNG"
    runtime._episodic.record(user_input="trag mir was ein", intents=["add_entry"],
                             response="✗ Dazu habe ich keinen Eintrag gefunden", source="test")

    text = runtime.run_self_review(date.today())

    assert text
    assert runtime._self_review.latest()


def test_run_self_review_off_by_default(tmp_path):
    config = _make_config(tmp_path)
    config.episodic_memory_enabled = True     # aber self_review_enabled bleibt False
    runtime = JarvisRuntime(config, ai=_SummarizeAI())
    runtime._episodic.record(user_input="x", intents=["chat"], response="✗", source="test")

    assert runtime.run_self_review() == ""


# --- Telegram-Ausbau (a): Briefing-Push + Meeting-Prep-Push ---------------

def _fake_dispatch(results: dict):
    """dispatch-Attrappe: intent -> Result."""
    from core.models import Result as R, Status as S

    def fake(plan):
        r = results.get(plan.intent)
        if r is None:
            return R(status=S.FAILED, message="nicht konfiguriert")
        return r
    return fake


def test_briefing_push_composes_briefing_and_mail(tmp_path, monkeypatch):
    """Scheibe (a): der Morgen-Push buendelt get_briefing + check_mail (read-only)
    und schickt sie ueber den Notifier."""
    from core.models import Result as R, Status as S

    config = _make_config(tmp_path)
    config.briefing_push_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())
    sent = []
    runtime.set_notifier(sent.append)
    monkeypatch.setattr(jarvis_runtime, "dispatch", _fake_dispatch({
        "get_briefing": R(status=S.SUCCESS, message="Termine: Zahnarzt 9 Uhr."),
        "check_mail": R(status=S.SUCCESS, message="2 neue Mails, eine dringend."),
    }))

    out = runtime.run_briefing_push()

    assert sent and "Zahnarzt" in sent[0] and "dringend" in sent[0]
    assert out.startswith("Guten Morgen")


def test_briefing_push_skips_failed_mail_part(tmp_path, monkeypatch):
    """Kein Mail-Konto (NEEDS_CLARIFICATION) -> der Mail-Teil bleibt still weg."""
    from core.models import Result as R, Status as S

    config = _make_config(tmp_path)
    config.briefing_push_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())
    sent = []
    runtime.set_notifier(sent.append)
    monkeypatch.setattr(jarvis_runtime, "dispatch", _fake_dispatch({
        "get_briefing": R(status=S.SUCCESS, message="Termine: keine."),
        "check_mail": R(status=S.NEEDS_CLARIFICATION, message="Kein Mail-Konto eingerichtet."),
    }))

    runtime.run_briefing_push()

    assert sent and "Mail-Konto" not in sent[0]


def test_briefing_push_off_by_default(tmp_path, monkeypatch):
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    sent = []
    runtime.set_notifier(sent.append)

    assert runtime.run_briefing_push() == ""
    assert sent == []


def test_maybe_briefing_push_time_gate_and_once_per_day(tmp_path, monkeypatch):
    """Vor der Uhrzeit kein Push; danach GENAU EINER pro Tag - auch ueber einen
    Neustart hinweg (Zustand persistiert)."""
    from datetime import datetime as dt

    from core.models import Result as R, Status as S

    config = _make_config(tmp_path)
    config.briefing_push_enabled = True
    config.briefing_push_time = "07:30"
    runtime = JarvisRuntime(config, ai=FakeAI())
    sent = []
    runtime.set_notifier(sent.append)
    monkeypatch.setattr(jarvis_runtime, "dispatch", _fake_dispatch({
        "get_briefing": R(status=S.SUCCESS, message="Guten Tag."),
    }))

    runtime._maybe_run_briefing_push(now=dt(2026, 7, 13, 6, 0))
    assert sent == []                                     # zu frueh

    runtime._maybe_run_briefing_push(now=dt(2026, 7, 13, 8, 0))
    assert len(sent) == 1                                 # gepusht

    runtime._maybe_run_briefing_push(now=dt(2026, 7, 13, 9, 0))
    assert len(sent) == 1                                 # nicht doppelt

    # "Neustart" am selben Tag: neue Runtime, gleicher memory_dir -> kein Doppel.
    runtime2 = JarvisRuntime(config, ai=FakeAI())
    sent2 = []
    runtime2.set_notifier(sent2.append)
    monkeypatch.setattr(jarvis_runtime, "dispatch", _fake_dispatch({
        "get_briefing": R(status=S.SUCCESS, message="Guten Tag."),
    }))
    runtime2._maybe_run_briefing_push(now=dt(2026, 7, 13, 10, 0))
    assert sent2 == []


def test_meeting_prep_push_within_lead_window_once(tmp_path, monkeypatch):
    """Ein Termin in 20 Minuten -> genau EIN Prep-Push (Dedupe persistiert);
    ein zweiter Lauf pusht nicht erneut."""
    from datetime import datetime as dt

    import commands.calendar as calendar_commands

    config = _make_config(tmp_path)
    config.meeting_prep_push_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())
    runtime._people.remember("Anna", "deine Steuerberaterin")
    sent = []
    runtime.set_notifier(sent.append)
    now = dt(2026, 7, 13, 8, 40)
    monkeypatch.setattr(calendar_commands, "read_agenda", lambda when: [
        {"subject": "Steuerberater Anna", "start": "2026-07-13T09:00:00"},
    ])

    assert runtime.run_meeting_prep_push(now=now) == 1
    assert sent and "Vorbereitung" in sent[0] and "Anna" in sent[0]

    assert runtime.run_meeting_prep_push(now=now) == 0     # Dedupe
    assert len(sent) == 1


def test_meeting_prep_push_ignores_far_past_and_allday(tmp_path, monkeypatch):
    from datetime import datetime as dt

    import commands.calendar as calendar_commands

    config = _make_config(tmp_path)
    config.meeting_prep_push_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())
    sent = []
    runtime.set_notifier(sent.append)
    now = dt(2026, 7, 13, 8, 0)
    monkeypatch.setattr(calendar_commands, "read_agenda", lambda when: [
        {"subject": "Spaeter", "start": "2026-07-13T12:00:00"},              # zu weit weg
        {"subject": "Vorbei", "start": "2026-07-13T07:00:00"},               # vorbei
        {"subject": "Ganztags", "start": "2026-07-13T00:00:00", "all_day": True},
    ])

    assert runtime.run_meeting_prep_push(now=now) == 0
    assert sent == []


def test_meeting_prep_push_off_by_default(tmp_path, monkeypatch):
    import commands.calendar as calendar_commands

    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    sent = []
    runtime.set_notifier(sent.append)
    monkeypatch.setattr(calendar_commands, "read_agenda", lambda when: [
        {"subject": "Gleich", "start": "2026-07-13T09:00:00"},
    ])

    assert runtime.run_meeting_prep_push() == 0
    assert sent == []


def test_runtime_wires_stop_agent_to_cancel_delegation(tmp_path):
    """c1: die Runtime injiziert cancel_delegation als stop_agent-Hook - ohne
    laufende Delegation antwortet der Befehl ehrlich 'kein Agent'."""
    from commands import dispatch as real_dispatch

    JarvisRuntime(_make_config(tmp_path), ai=FakeAI())  # configure() laeuft im Konstruktor
    result = real_dispatch(Plan(intent="stop_agent", raw_input="stopp den agenten"))

    assert result.ok
    assert "kein Agent" in result.message


# --- Erlaubnis-Haken (S4b Scheibe 2, ADR-071) -----------------------------

def _hook_runtime(tmp_path):
    config = _make_config(tmp_path)
    config.agent_permission_hook_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())
    sent = []
    runtime.set_notifier(sent.append)
    return runtime, sent


def test_hook_settings_written_when_enabled(tmp_path):
    import json

    runtime, _ = _hook_runtime(tmp_path)
    path = tmp_path / "memory_data" / "hook_settings.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["hooks"]["PreToolUse"][0]["matcher"] == "Bash"
    assert "agent_permission_hook.py" in data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]


def test_hook_settings_absent_by_default(tmp_path):
    JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    assert not (tmp_path / "memory_data" / "hook_settings.json").exists()


def test_permission_yes_writes_allow_to_mailbox(tmp_path):
    """Die armierte Erlaubnis-Frage: 'ja' aus dem Frage-Kanal schreibt allow=True
    in die Mailbox und quittiert - die Nachricht geht NICHT durch den Planner."""
    import json

    runtime, _ = _hook_runtime(tmp_path)
    runtime._permission_offer = ("telegram", "abc123", time.monotonic() + 60)

    replies = []
    runtime._process_inner("ja", replies.append, source="telegram")

    answer = json.loads((runtime._hook_mailbox.dir / "a_abc123.json").read_text(encoding="utf-8"))
    assert answer["allow"] is True
    assert replies and "Erlaubt" in replies[0]
    assert runtime._permission_offer is None


def test_permission_no_writes_deny(tmp_path):
    import json

    runtime, _ = _hook_runtime(tmp_path)
    runtime._permission_offer = ("telegram", "abc124", time.monotonic() + 60)

    replies = []
    runtime._process_inner("nein", replies.append, source="telegram")

    answer = json.loads((runtime._hook_mailbox.dir / "a_abc124.json").read_text(encoding="utf-8"))
    assert answer["allow"] is False
    assert replies and "Abgelehnt" in replies[0]


def test_permission_expired_yes_is_deny(tmp_path):
    """Ein 'ja' NACH Ablauf des Fensters wird sicherheitshalber zum Nein."""
    import json

    runtime, _ = _hook_runtime(tmp_path)
    runtime._permission_offer = ("telegram", "abc125", time.monotonic() - 1)

    replies = []
    runtime._process_inner("ja", replies.append, source="telegram")

    answer = json.loads((runtime._hook_mailbox.dir / "a_abc125.json").read_text(encoding="utf-8"))
    assert answer["allow"] is False
    assert replies and "abgelaufen" in replies[0]


def test_permission_yes_from_other_channel_answers(tmp_path):
    """PO-Live-Befund 13.07. (er antwortete zuerst am Desktop): ein ja/nein
    zaehlt aus JEDEM Kanal des Besitzers - wer die Frage sieht, darf antworten."""
    import json

    runtime, _ = _hook_runtime(tmp_path)
    runtime._permission_offer = ("telegram", "abc126", time.monotonic() + 60)

    replies = []
    runtime._process_inner("nein", replies.append, source="browser")

    answer = json.loads((runtime._hook_mailbox.dir / "a_abc126.json").read_text(encoding="utf-8"))
    assert answer["allow"] is False
    assert runtime._permission_offer is None
    assert replies and "stopp den Agenten" in replies[0]      # Stopp-Hinweis dabei


def test_permission_other_text_from_foreign_channel_keeps_armed(tmp_path):
    """Anderes Thema aus einem FREMDEN Kanal laesst die Frage armiert (nur der
    Frage-Kanal laesst sie durch anderes Thema verfallen)."""
    runtime, _ = _hook_runtime(tmp_path)
    runtime._permission_offer = ("telegram", "abc128", time.monotonic() + 60)

    replies = []
    runtime._process_inner("wie ist das wetter?", replies.append, source="browser")

    assert runtime._permission_offer is not None              # bleibt offen
    assert replies                                            # normale Antwort kam


def test_permission_other_text_lapses_question(tmp_path):
    """Anderes Thema aus dem Frage-Kanal: Frage verfaellt (Hook-Timeout = NEIN),
    die Nachricht wird normal beantwortet."""
    runtime, _ = _hook_runtime(tmp_path)
    runtime._permission_offer = ("telegram", "abc127", time.monotonic() + 60)

    replies = []
    runtime._process_inner("wie ist das wetter?", replies.append, source="telegram")

    assert runtime._permission_offer is None
    assert not (runtime._hook_mailbox.dir / "a_abc127.json").exists()
    assert replies


def test_hook_watcher_pushes_question_and_arms_offer(tmp_path):
    """Der Watcher sieht eine offene Hook-Anfrage, pusht die Frage (geschwaerzt)
    und armiert GENAU EIN Angebot."""
    runtime, sent = _hook_runtime(tmp_path)
    runtime._hook_mailbox.dir.mkdir(parents=True, exist_ok=True)
    (runtime._hook_mailbox.dir / "q_req1.json").write_text(
        '{"id": "req1", "tool": "Bash", "command": "git push origin main"}',
        encoding="utf-8")
    with runtime._state_lock:
        runtime._delegation_active = True
    cancel = threading.Event()
    try:
        t = threading.Thread(target=runtime._watch_hook_requests, args=(cancel,), daemon=True)
        t.start()
        for _ in range(40):
            if sent:
                break
            time.sleep(0.1)
    finally:
        with runtime._state_lock:
            runtime._delegation_active = False
        t.join(timeout=5)

    assert sent and "git push origin main" in sent[0] and "Erlauben?" in sent[0]
    assert runtime._permission_offer is not None
    assert runtime._permission_offer[0] == "telegram"
    assert runtime._permission_offer[1] == "req1"


def test_permission_question_is_verstaendlich(tmp_path):
    """PO-Live-Befund 13.07. ('Kauderwelsch'): die Frage traegt Klartext-Satz
    (LLM, injiziert), Risiko-Einordnung und den rohen Befehl als 'Technisch:'."""
    config = _make_config(tmp_path)
    config.agent_permission_hook_enabled = True
    runtime = JarvisRuntime(config, ai=_SummarizeAI())   # generate() -> "ZUSAMMENFASSUNG"

    q = runtime._permission_question('ls -la && git log --oneline -5')

    assert "Was er tun will: ZUSAMMENFASSUNG" in q       # Klartext-Satz (LLM)
    assert "Einordnung:" in q and "Nur-Lese" in q        # deterministische Einordnung
    assert "Technisch: «ls -la && git log --oneline -5»" in q
    assert "Erlauben?" in q


def test_permission_question_without_llm_still_informative(tmp_path):
    """Ohne generate() (FakeAI) bleibt die deterministische Einordnung."""
    config = _make_config(tmp_path)
    config.agent_permission_hook_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())

    q = runtime._permission_question("git push origin main")

    assert "Einordnung:" in q and "⚠️" in q              # riskant erkannt
    assert "Was er tun will" not in q                    # kein LLM-Satz erfunden


# --- Aktions-Zustand im Antwort-Kontext (UX-S4) ---------------------------

def test_action_state_mentions_fresh_start(tmp_path):
    """Frisch gestartet: der Kontext sagt es KLAR - eine zugesagte Aktion (z. B.
    Neustart) IST passiert; nie mehr ein erfundenes 'kein Neustart'."""
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    block = runtime._action_state_block()
    assert "neu) gestartet" in block
    assert "NIE" in block                                  # die Ehrlichkeits-Regel


def test_action_state_records_executed_intents(tmp_path):
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    runtime._started_monotonic -= 600                      # kein 'frisch gestartet'

    class _WebAI(FakeAI):
        def get_plan(self, user_input, history):
            return Plan(intent="search_web", target="Wetter", raw_input=user_input, confidence=1.0)

    runtime.ai = _WebAI()
    runtime.planner = jarvis_runtime.Planner(runtime.ai) if hasattr(jarvis_runtime, "Planner") else runtime.planner
    runtime._process_inner("such was im web", lambda _m: None)

    block = runtime._action_state_block()
    assert "search_web" in block


def test_action_state_flags_running_delegation(tmp_path):
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    with runtime._state_lock:
        runtime._delegation_active = True
    try:
        block = runtime._action_state_block()
    finally:
        with runtime._state_lock:
            runtime._delegation_active = False
    assert "LAEUFT" in block and "stopp den Agenten" in block


def test_action_state_flows_into_answer_context(tmp_path):
    """Der Zustand reitet auf long_term_summary -> erreicht Chat UND Composer."""
    captured = {}

    class _CaptureAI(FakeAI):
        def answer(self, user_input, history, long_term_summary=""):
            captured["summary"] = long_term_summary
            return "ok"

    runtime = JarvisRuntime(_make_config(tmp_path), ai=_CaptureAI())
    runtime._process_inner("hallo", lambda _m: None)

    assert "AKTIONS-ZUSTAND" in captured.get("summary", "")


# --- "Neu bei mir"-Hinweis (Spektakulaer #1) -------------------------------

def _whats_new_runtime(tmp_path, changelog_text):
    import commands.help as help_commands

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(changelog_text, encoding="utf-8")
    help_commands.configure(changelog)
    config = _make_config(tmp_path)
    config.whats_new_hint_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())
    help_commands.configure(changelog)     # Runtime-__init__ ueberschreibt den Pfad
    return runtime


def test_whats_new_hint_surfaces_once(tmp_path):
    runtime = _whats_new_runtime(
        tmp_path, "# Changelog\n\n## 2026-07-13 - Jarvis lernt Fliegen\n\n- x\n")

    first = []
    runtime._process_inner("hallo", first.append)
    assert any("Neues gelernt: Jarvis lernt Fliegen" in m for m in first)

    second = []
    runtime._process_inner("noch was", second.append)
    assert not any("Neues gelernt" in m for m in second)      # nur EINMAL


def test_whats_new_hint_off_by_default(tmp_path):
    import commands.help as help_commands

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## 2026-07-13 - Titel\n\n- x\n", encoding="utf-8")
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    help_commands.configure(changelog)

    out = []
    runtime._process_inner("hallo", out.append)
    assert not any("Neues gelernt" in m for m in out)


# --- Neue-Version-Hinweis (Spektakulaer #5-light) --------------------------

def test_version_hint_armed_on_head_change_and_surfaces_once(tmp_path, monkeypatch):
    config = _make_config(tmp_path)
    config.version_hint_enabled = True
    monkeypatch.setattr(jarvis_runtime, "_git_head", lambda repo: "AAAA")
    runtime = JarvisRuntime(config, ai=FakeAI())

    # Platte hat jetzt einen neueren Stand:
    monkeypatch.setattr(jarvis_runtime, "_git_head", lambda repo: "BBBB")
    runtime._maybe_check_new_version()
    assert runtime._version_hint_pending is True

    first = []
    runtime._process_inner("hallo", first.append)
    assert any("starte neu" in m for m in first)

    second = []
    runtime._process_inner("weiter", second.append)
    assert not any("starte neu" in m for m in second)      # nur EINMAL

    # Derselbe Stand armiert nicht erneut (Drossel umgangen):
    runtime._last_version_check_monotonic = 0.0
    runtime._maybe_check_new_version()
    assert runtime._version_hint_pending is False


def test_version_hint_off_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(jarvis_runtime, "_git_head", lambda repo: "AAAA")
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    monkeypatch.setattr(jarvis_runtime, "_git_head", lambda repo: "BBBB")
    runtime._maybe_check_new_version()
    assert runtime._version_hint_pending is False


# --- Gesprochene Erinnerungen + Stimme-ohne-Bestaetigungsweg ---------------

def test_due_reminder_is_spoken_when_enabled(tmp_path):
    """PO-Reibung 13.07. («Mit Sprache»): eine faellige Erinnerung wird
    zusaetzlich ueber den injizierten Sprech-Weg gesprochen."""
    config = _make_config(tmp_path)
    config.reminder_speech_enabled = True
    runtime = JarvisRuntime(config, ai=FakeAI())
    pushed, spoken = [], []
    runtime.set_notifier(pushed.append)
    runtime.set_voice_notifier(spoken.append)
    e = runtime._entry_store.add(text="Pizza aus dem Ofen holen", when="2099-01-01T00:00")
    with runtime._entry_store._lock:
        data = runtime._entry_store._read()
        for d in data:
            if d["id"] == e.id:
                d["when"] = "2020-01-01T00:00"
        runtime._entry_store._write(data)

    runtime._push_due_entries()

    assert pushed and "Pizza" in pushed[0]
    assert spoken and "Pizza aus dem Ofen holen" in spoken[0]


def test_due_reminder_not_spoken_by_default(tmp_path):
    runtime = JarvisRuntime(_make_config(tmp_path), ai=FakeAI())
    pushed, spoken = [], []
    runtime.set_notifier(pushed.append)
    runtime.set_voice_notifier(spoken.append)
    e = runtime._entry_store.add(text="Pizza", when="2099-01-01T00:00")
    with runtime._entry_store._lock:
        data = runtime._entry_store._read()
        for d in data:
            if d["id"] == e.id:
                d["when"] = "2020-01-01T00:00"
        runtime._entry_store._write(data)

    runtime._push_due_entries()

    assert pushed and spoken == []                        # Text ja, Stimme nein


def test_voice_stage2_explains_way_instead_of_cryptic_abort(tmp_path):
    """PO-Reibung 13.07.: «loesch den Termin» per Stimme endete in 'Abgebrochen
    - keine Bestaetigung erhalten', OHNE dass je gefragt wurde. Jetzt erklaert
    die Antwort den Weg (Chat/Handy) in Kundendeutsch."""
    class _CancelAI(FakeAI):
        def get_plan(self, user_input, history):
            return Plan(intent="shutdown_pc", raw_input=user_input, confidence=1.0)

    runtime = JarvisRuntime(_make_config(tmp_path), ai=_CancelAI())

    replies = []
    # Kein confirmer gesetzt = Sprach-/PTT-Weg (fail-closed).
    runtime._process_inner("fahr den pc runter", replies.append, source="voice")

    assert replies
    assert "Bestätigung" in replies[0]
    assert "Chat oder am Handy" in replies[0]              # der gezeigte Weg
    assert "Abgebrochen - keine Bestätigung erhalten" not in replies[0]
