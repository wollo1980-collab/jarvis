"""Tests für jarvis_runtime.py - JarvisRuntime (Queue+Worker-Thread),
_RuntimeSpeech (fail-closed) und ConsoleDummyChannel (ADR-025). AIEngine
gemockt (FakeAI, gleiches Muster wie tests/test_integration.py), kein
echter API-Key/Netzwerk nötig."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import commands.delegate as delegate_commands
import commands.web as web_commands
import jarvis_runtime
from core.agent_backend import AgentResult
from core.config import Config
from core.models import Plan
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
        jarvis_runtime.mail_commands, "configure", lambda config: calls.append(config)
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
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("suche im web nach wetter berlin", reply_callback)
        _wait(done)

        assert "Quellen:" in replies[0]
        assert "https://example.com/wetter-berlin" in replies[0]
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
    assert "verspätet" in msg and "01.01.2020 09:00" in msg

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

        # shutdown_pc erfordert eine exakte Bestaetigungsphrase (Stufe 3)
        # - _RuntimeSpeech.listen() liefert "" statt der Phrase, der
        # Executor lehnt ab statt eine Bestaetigung zu erfinden.
        assert "Abgebrochen" in replies[0]
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

    runtime.stop()  # setzt Kill-Switch -> Backend kehrt zurueck -> Thread endet

    assert runtime._delegation_thread is not None
    assert runtime._delegation_thread.is_alive() is False


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
        # Erster Hintergrund-Thread (wirft) sauber abwarten.
        runtime._delegation_thread.join(timeout=5.0)

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
    assert "fake_long (jkc)" in say_text  # Rueckfrage nennt die Aktion
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
    assert any("Abgebrochen" in r for r in replies)
