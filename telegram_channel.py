"""
Runtime v2 (ADR-027) - TelegramChannel: erster echter Runtime-Kanal
neben ConsoleDummyChannel (jarvis_runtime.py). Einzige Stelle im
Runtime-Umfeld mit python-telegram-bot/asyncio-Code - vollständig
getrennt von jarvis_runtime.py gehalten.

Sicherheitslogik (ALLOWED_INTENTS, filter_plan, rejection_reason,
is_authorized) wird unverändert aus telegram_main.py importiert statt
dupliziert (ADR-027 Punkt 7/8) - derselbe Sicherheitsstand wie
telegram_main.py (ADR-018), nur über die Runtime statt einer eigenen
Core-Stack-Instanz. TelegramSpeech/eigener Executor sind hier nicht
nötig: JarvisRuntime.executor läuft bereits mit dem fail-closed
_RuntimeSpeech-Adapter (ADR-025) - Sicherheitsstufe-2/3-Commands bleiben
dadurch automatisch gesperrt, auch über diesen Kanal.

Asyncio-Brücke (ADR-027 Punkt 9): python-telegram-bot ist strukturell
asynchron (eigener Event-Loop über Application.run_polling()). Die
Runtime selbst bleibt synchron/Thread-basiert (ADR-024) - nur dieser
Kanal überbrückt beide Modelle: eingehend ruft der (asynchrone)
Nachrichten-Handler synchron runtime.submit() auf (unproblematisch,
queue.Queue ist thread-sicher); ausgehend nutzt der aus dem
Runtime-Worker-Thread aufgerufene reply_callback
asyncio.run_coroutine_threadsafe(), um die Antwort sicher auf den
PTB-eigenen Event-Loop zurück einzuschleusen.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future
from typing import Optional

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from jarvis_runtime import JarvisRuntime
from telegram_main import ALLOWED_INTENTS, filter_plan, is_authorized, rejection_reason

logger = logging.getLogger("jarvis.runtime.telegram")

# Der Runtime-Kanal erlaubt zusaetzlich zur Standalone-Whitelist die
# asynchrone Repo-Analyse (ADR-035): delegate_analysis laeuft hier im
# Hintergrund-Worker der Runtime (Quittung -> Push), blockiert also NICHT den
# Event-Loop. Der Standalone-Bot (telegram_main.py) bleibt bewusst ohne diesen
# Intent - er hat keinen Async-Worker und wuerde bei einer Minuten-Analyse den
# PTB-Loop blockieren.
RUNTIME_ALLOWED_INTENTS = ALLOWED_INTENTS | {"delegate_analysis", "plan_next_step"}

__all__ = [
    "TelegramChannel",
    "ALLOWED_INTENTS",
    "RUNTIME_ALLOWED_INTENTS",
    "filter_plan",
    "rejection_reason",
    "is_authorized",
]

_MAX_TELEGRAM_TEXT = 4000


def _runtime_filter_plan(steps):
    """Whitelist-Filter des Runtime-Kanals: wie filter_plan, aber mit dem um
    delegate_analysis erweiterten Set (ADR-035)."""
    return filter_plan(steps, RUNTIME_ALLOWED_INTENTS)


class TelegramChannel:
    """Zweiter Runtime-Kanal (ADR-027): liest über python-telegram-bot
    Long-Polling, wendet dieselbe Whitelist wie telegram_main.py an und
    reicht erlaubte Nachrichten über runtime.submit() weiter. Bekommt
    eine bereits existierende JarvisRuntime injiziert - baut keinen
    eigenen Core-Stack auf (Core-Stack bleibt einmalig, ADR-024)."""

    def __init__(self, runtime: JarvisRuntime, bot_token: str, allowed_chat_id: str):
        self.runtime = runtime
        self.bot_token = bot_token
        self.allowed_chat_id = allowed_chat_id
        self._application: Optional[Application] = None
        # Der PTB-Event-Loop laeuft in DIESEM Kanal-Thread (run_polling), nicht
        # im Runtime-/Main-Thread, der stop() aufruft. _loop wird per
        # _post_init() im Loop erfasst, _loop_ready signalisiert, dass er
        # verfuegbar ist.
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_ready = threading.Event()

    async def _post_init(self, application: Application) -> None:
        """Laeuft im PTB-Event-Loop-Thread nach der Initialisierung und vor
        dem Polling. Erfasst den laufenden Loop, damit stop() den Shutdown
        aus einem fremden Thread thread-/eventloop-konform einplanen kann."""
        self._loop = asyncio.get_running_loop()
        self._loop_ready.set()

    def run(self) -> None:
        """Blockierend - für den Aufruf in einem eigenen Thread gedacht
        (jarvis_runtime.py::main() startet diesen Kanal nicht im
        Hauptthread, der weiterhin ConsoleDummyChannel bedient)."""
        self._application = (
            Application.builder().token(self.bot_token).post_init(self._post_init).build()
        )
        self._application.bot_data["channel"] = self
        self._application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_message))

        logger.info("TelegramChannel gestartet (Long-Polling, Runtime v2).")
        # stop_signals=None: Application.run_polling() versucht sonst,
        # Signal-Handler zu installieren - das schlaegt ausserhalb des
        # Hauptthreads fehl (dieser Kanal laeuft in einem eigenen
        # Hintergrund-Thread neben ConsoleDummyChannel).
        self._application.run_polling(stop_signals=None)

    def stop(self) -> None:
        """Wird aus dem Runtime-/Main-Thread aufgerufen. Application.stop_running()
        MUSS im PTB-Event-Loop-Thread laufen - ein Direktaufruf aus einem
        fremden Thread wirft `RuntimeError: no running event loop`. Deshalb den
        Aufruf thread-sicher in den erfassten Loop einplanen (gleiche Bruecke
        wie beim reply_callback, ADR-027)."""
        app = self._application
        if app is None:
            return
        # Kurz auf den Loop warten, falls stop() sehr frueh (vor _post_init)
        # kommt - im Normalfall laengst gesetzt.
        self._loop_ready.wait(timeout=5.0)
        loop = self._loop
        if loop is None:
            logger.warning(
                "TelegramChannel.stop(): Event-Loop nicht verfuegbar - Shutdown uebersprungen."
            )
            return
        loop.call_soon_threadsafe(app.stop_running)


def _message_chunks(text: str, limit: int = _MAX_TELEGRAM_TEXT) -> list[str]:
    """Split long Telegram replies into safe chunks below the API limit."""
    clean_text = text.strip()
    if not clean_text:
        return []
    if len(clean_text) <= limit:
        return [clean_text]

    chunks: list[str] = []
    start = 0
    while start < len(clean_text):
        end = min(start + limit, len(clean_text))
        if end < len(clean_text):
            split_at = clean_text.rfind("\n", start, end)
            if split_at >= start:
                end = split_at + 1
        if end == start:
            end = min(start + limit, len(clean_text))
        chunks.append(clean_text[start:end])
        start = end
    return chunks


async def _send_reply_chunks(bot, chat_id: int, text: str) -> None:
    """Send one logical answer as one or more Telegram messages."""
    for chunk in _message_chunks(text):
        await bot.send_message(chat_id=chat_id, text=chunk)


def _log_send_future(future: Future) -> None:
    """Surface Telegram send failures instead of dropping them silently."""
    try:
        future.result()
    except Exception:
        logger.exception("Telegram-Antwort konnte nicht gesendet werden.")


async def _on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    channel: TelegramChannel = context.application.bot_data["channel"]
    if update.effective_chat is None or update.message is None or not update.message.text:
        return

    chat_id = update.effective_chat.id
    if not is_authorized(chat_id, channel.allowed_chat_id):
        logger.warning("Nicht autorisierter Chat %s - Nachricht ignoriert.", chat_id)
        return

    user_input = update.message.text
    loop = asyncio.get_running_loop()

    def reply_callback(text: str) -> None:
        future = asyncio.run_coroutine_threadsafe(
            _send_reply_chunks(context.bot, chat_id=chat_id, text=text), loop
        )
        future.add_done_callback(_log_send_future)

    # allow_async=True: die Runtime darf delegate_analysis in ihren
    # Hintergrund-Worker auslagern (Quittung sofort, Ergebnis-Push spaeter
    # ueber denselben reply_callback). Telegram bleibt reiner Transportkanal
    # (ADR-035) - die gesamte Async-Orchestrierung liegt in der Runtime.
    channel.runtime.submit(
        user_input, reply_callback, plan_filter=_runtime_filter_plan, allow_async=True
    )
