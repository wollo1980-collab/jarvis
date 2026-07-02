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
from typing import Optional

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from jarvis_runtime import JarvisRuntime
from telegram_main import ALLOWED_INTENTS, filter_plan, is_authorized, rejection_reason

logger = logging.getLogger("jarvis.runtime.telegram")

__all__ = ["TelegramChannel", "ALLOWED_INTENTS", "filter_plan", "rejection_reason", "is_authorized"]


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
        asyncio.run_coroutine_threadsafe(
            context.bot.send_message(chat_id=chat_id, text=text), loop
        )

    channel.runtime.submit(user_input, reply_callback, plan_filter=filter_plan)
