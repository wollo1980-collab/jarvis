"""Tests für telegram_channel.py - TelegramChannel (ADR-027). Kein
echter Bot-Token/Netzwerk nötig: python-telegram-bot-Objekte (Update,
Context, Application) werden gemockt, die Asyncio-Brücke wird mit einem
echten, in einem eigenen Thread laufenden Event-Loop nachgebildet
(simuliert python-telegram-bots eigenen Loop)."""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config import Config
from core.models import Plan
from jarvis_runtime import JarvisRuntime
import telegram_main
import telegram_channel
from telegram_channel import TelegramChannel, _on_message, filter_plan


def _make_update(chat_id, text):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.text = text
    return update


def _make_context(channel):
    context = MagicMock()
    context.application.bot_data = {"channel": channel}
    return context


def _make_channel(allowed_chat_id="111"):
    channel = MagicMock()
    channel.allowed_chat_id = allowed_chat_id
    channel.runtime = MagicMock()
    return channel


def test_authorized_message_is_forwarded_with_filter_plan():
    channel = _make_channel()
    update = _make_update(chat_id=111, text="hallo")
    context = _make_context(channel)

    asyncio.run(_on_message(update, context))

    channel.runtime.submit.assert_called_once()
    args, kwargs = channel.runtime.submit.call_args
    assert args[0] == "hallo"
    assert kwargs["plan_filter"] is filter_plan


def test_unauthorized_message_is_ignored_without_submit():
    channel = _make_channel(allowed_chat_id="111")
    update = _make_update(chat_id=999, text="hallo")
    context = _make_context(channel)

    asyncio.run(_on_message(update, context))

    channel.runtime.submit.assert_not_called()


def test_non_text_update_is_ignored():
    channel = _make_channel()
    update = MagicMock()
    update.effective_chat = None
    context = _make_context(channel)

    asyncio.run(_on_message(update, context))

    channel.runtime.submit.assert_not_called()


def test_empty_message_text_is_ignored():
    channel = _make_channel()
    update = _make_update(chat_id=111, text=None)
    context = _make_context(channel)

    asyncio.run(_on_message(update, context))

    channel.runtime.submit.assert_not_called()


def test_reply_callback_delivers_message_from_worker_thread():
    """Kern-Asyncio-Brücken-Test (ADR-027 Punkt 9): reply_callback wird
    aus einem ANDEREN, echten Thread aufgerufen (simuliert den
    Runtime-Worker) - die Antwort muss trotzdem sicher auf dem
    Event-Loop-Thread ankommen (simuliert python-telegram-bots Loop)."""
    calls = []
    done = threading.Event()

    async def fake_send_message(**kwargs):
        calls.append(kwargs)
        done.set()

    channel = _make_channel()
    captured = {}

    def fake_submit(text, reply_callback, plan_filter=None):
        captured["reply_callback"] = reply_callback

    channel.runtime.submit.side_effect = fake_submit

    update = _make_update(chat_id=111, text="hallo")
    context = _make_context(channel)
    context.bot.send_message = fake_send_message

    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
    try:
        fut = asyncio.run_coroutine_threadsafe(_on_message(update, context), loop)
        fut.result(timeout=2.0)

        reply_callback = captured["reply_callback"]
        worker_thread = threading.Thread(target=reply_callback, args=("antwort",))
        worker_thread.start()
        worker_thread.join()

        assert done.wait(timeout=2.0)
        assert calls == [{"chat_id": 111, "text": "antwort"}]
    finally:
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=2.0)
        loop.close()


def test_reply_callback_does_not_raise_when_send_message_fails():
    done = threading.Event()

    async def failing_send_message(**kwargs):
        done.set()
        raise RuntimeError("Chat blockiert")

    channel = _make_channel()
    captured = {}

    def fake_submit(text, reply_callback, plan_filter=None):
        captured["reply_callback"] = reply_callback

    channel.runtime.submit.side_effect = fake_submit

    update = _make_update(chat_id=111, text="hallo")
    context = _make_context(channel)
    context.bot.send_message = failing_send_message

    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
    try:
        fut = asyncio.run_coroutine_threadsafe(_on_message(update, context), loop)
        fut.result(timeout=2.0)

        reply_callback = captured["reply_callback"]
        reply_callback("antwort")  # darf nicht werfen
        # Sicherstellen, dass die fehlschlagende Koroutine tatsaechlich
        # noch laeuft, bevor der Loop im finally-Block gestoppt wird -
        # vermeidet ein "coroutine was never awaited"-Warning durch eine
        # reine Timing-Race im Test selbst.
        assert done.wait(timeout=2.0)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=2.0)
        loop.close()


def test_telegram_channel_reuses_security_logic_from_telegram_main():
    """Regressionsschutz gegen kuenftiges versehentliches Duplizieren
    (ADR-027 Punkt 7/8) - echte Identitaet, nicht nur gleicher Inhalt."""
    assert telegram_channel.filter_plan is telegram_main.filter_plan
    assert telegram_channel.rejection_reason is telegram_main.rejection_reason
    assert telegram_channel.is_authorized is telegram_main.is_authorized
    assert telegram_channel.ALLOWED_INTENTS is telegram_main.ALLOWED_INTENTS


class _FakeAI:
    def get_plan(self, user_input, history):
        return Plan(intent="shutdown_pc", raw_input=user_input, confidence=1.0)

    def answer(self, user_input, history, long_term_summary=""):
        return f"Antwort auf: {user_input}"


def _make_runtime_config(tmp_path: Path) -> Config:
    memory_dir = tmp_path / "memory_data"
    log_dir = tmp_path / "logs"
    memory_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    return Config(memory_dir=memory_dir, log_dir=log_dir, max_history_entries=20)


def test_stufe2_intent_rejected_via_filter_before_executor(tmp_path):
    """Sicherheitskritisch (ADR-027): ein per Telegram nicht erlaubter
    Intent (hier zusaetzlich Sicherheitsstufe 3) darf den Executor nicht
    erreichen - die Whitelist-Pruefung muss vor der Ausfuehrung greifen,
    nicht nur der fail-closed Speech-Adapter."""
    config = _make_runtime_config(tmp_path)
    runtime = JarvisRuntime(config, ai=_FakeAI())
    runtime.executor.run = MagicMock(side_effect=AssertionError("Executor haette nicht laufen duerfen"))
    runtime.start()
    try:
        done = threading.Event()
        replies = []

        def reply_callback(text):
            replies.append(text)
            done.set()

        runtime.submit("mach etwas kritisches", reply_callback, plan_filter=filter_plan)
        assert done.wait(timeout=2.0)

        assert "abgelehnt" in replies[0]
        assert "shutdown_pc" in replies[0]
        runtime.executor.run.assert_not_called()
    finally:
        runtime.stop()


@patch("telegram_channel.Application")
def test_run_polling_called_with_stop_signals_none(mock_application_cls):
    """PTB installiert sonst Signal-Handler, was ausserhalb des
    Hauptthreads abstuerzt (dieser Kanal laeuft in einem eigenen
    Hintergrund-Thread neben ConsoleDummyChannel)."""
    mock_app = MagicMock()
    mock_application_cls.builder.return_value.token.return_value.build.return_value = mock_app

    channel = TelegramChannel(runtime=MagicMock(), bot_token="TOKEN", allowed_chat_id="111")
    channel.run()

    mock_app.run_polling.assert_called_once_with(stop_signals=None)


@patch("telegram_channel.Application")
def test_stop_requests_polling_shutdown(mock_application_cls):
    mock_app = MagicMock()
    mock_application_cls.builder.return_value.token.return_value.build.return_value = mock_app

    channel = TelegramChannel(runtime=MagicMock(), bot_token="TOKEN", allowed_chat_id="111")
    channel.run()
    channel.stop()

    mock_app.stop_running.assert_called_once()


def test_stop_without_run_is_a_no_op():
    channel = TelegramChannel(runtime=MagicMock(), bot_token="TOKEN", allowed_chat_id="111")
    channel.stop()  # darf nicht werfen
