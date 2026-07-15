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

from core.confirmation import ConfirmationGate
from jarvis_runtime import JarvisRuntime
from telegram_main import ALLOWED_INTENTS, filter_plan, is_authorized, rejection_reason

logger = logging.getLogger("jarvis.runtime.telegram")

# Der Runtime-Kanal erlaubt zusaetzlich zur Standalone-Whitelist die
# asynchrone Repo-Analyse (ADR-035): delegate_analysis laeuft hier im
# Hintergrund-Worker der Runtime (Quittung -> Push), blockiert also NICHT den
# Event-Loop. Der Standalone-Bot (telegram_main.py) bleibt bewusst ohne diesen
# Intent - er hat keinen Async-Worker und wuerde bei einer Minuten-Analyse den
# PTB-Loop blockieren.
RUNTIME_ALLOWED_INTENTS = ALLOWED_INTENTS | {
    "delegate_analysis",
    "plan_next_step",
    "stop_runtime",
    # Neustart (Welle 3.4): gleiche Kontrollaktion wie stop_runtime - die
    # "gleich wieder da"-Zusage sichert derselbe Send-Flush vor dem Teardown.
    "restart_runtime",
    # Eintraege (A1): reiner eigener Datenlayer, harmlos wie remember_fact.
    "add_entry",
    "list_entries",
    "delete_entry",
    # Papierkorb-Rueckwege (Bestaetigungs-Diaet 14.07.): das Undo zu
    # delete_entry/forget_fact gehoert auf DENSELBEN Kanal wie das Loeschen -
    # sonst nennt die Antwort unterwegs einen Rueckweg, der dort nicht geht.
    "restore_entry",
    "restore_fact",
    # Auftrags-Loop (Phase B.1, ADR-074): read-only Portfolio-Review starten,
    # Status abfragen, abbrechen - gerade UNTERWEGS der Kernnutzen (Quittung
    # sofort, Ergebnis kommt als Push aus der Task-Outbox).
    "portfolio_review",
    "task_status",
    "task_resume",
    "task_cancel",
    # Benannte Listen (2026-07-10): derselbe harmlose Datenlayer - die
    # Einkaufsliste soll gerade UNTERWEGS erreichbar sein; clear_list ist
    # dank Papierkorb+restore_list gefahrlos (Undo statt Rueckfrage).
    "add_to_list",
    "show_list",
    "remove_from_list",
    "clear_list",
    "restore_list",
    # Morgen-Briefing (2026-07-11): read-only Komposition - gerade
    # unterwegs/morgens der natuerlichste Abruf.
    "get_briefing",
    # Ideen-Befehl (Angestellten-Vision Stufe 1): schlaegt nur vor.
    "propose_ideas",
    # Wochen-Rueckblick: deterministische Rechenschaft, read-only.
    "weekly_review",
    # Stufe-2/3-Befehle (ADR-045, PO-Freigabe 10.07.2026): seit dem
    # ConfirmationGate hat der Runtime-Kanal einen ECHTEN Bestaetigungsweg -
    # der Ausschlussgrund (fail-closed ohne Antwortkanal) entfaellt. Der
    # Executor-Dialog (Stufe 2 Ja/Nein, Stufe 3 exakte Phrase) gilt
    # unveraendert; keine Antwort/Timeout => Abbruch.
    "shutdown_pc",
    "clean_temp_files",
    "install_program",
    "enable_autostart_entry",
    "disable_autostart_entry",
    "enable_jarvis_autostart",
    "disable_jarvis_autostart",
    # Telegram-Ausbau (b), 13.07.2026 - "COO in der Hosentasche": kuratierte
    # Erweiterung um die Alltags-Intents, die unterwegs am meisten fehlen.
    # Kalender: lesen ist Stufe 0; add/move/cancel tragen requires_confirmation
    # und laufen ueber das bestehende ConfirmationGate (ja/nein im Chat).
    "calendar_agenda",
    "calendar_add_event",
    "calendar_move_event",
    "calendar_cancel_event",
    # Meeting-Prep (Plan C4): read-only Buendelung, das mobile Gegenstueck
    # zum Prep-Push.
    "prepare_meeting",
    # Personen-Gedaechtnis (ADR-066): reiner Datenlayer wie remember_fact.
    "who_is",
    "remember_person",
    # Eintraege aendern: gleicher harmloser Datenlayer wie add/delete_entry.
    "update_entry",
    # Selbstbewertung (ADR-066 Stein 3): read-only.
    "self_review",
    # Agenten-Stopp (c1): der Kill-Switch als Befehl - die harte Kontrolle
    # gehoert GERADE aufs Handy (Stufe-0-Kontrollaktion, stoppt nur).
    "stop_agent",
    # Bau-Arm mobil (c2, PO-Go 13.07. "Ja mach mit A weiter"): "Bau mir X"
    # auch von unterwegs. Voraussetzungen erfuellt: Bestaetigung VOR dem Lauf
    # (ConfirmationGate ADR-045 + preview zeigt den konkreten Bau), Not-Stopp
    # jederzeit (stop_agent, c1), Ergebnis-Push nach Abschluss (ADR-035-Async).
    # Kaefig unveraendert (sandboxed, nie Jarvis' eigenes Repo, ADR-056/059).
    "build_project",
    "delegate_work",
    "project_continue",
}

__all__ = [
    "TelegramChannel",
    "ALLOWED_INTENTS",
    "RUNTIME_ALLOWED_INTENTS",
    "filter_plan",
    "rejection_reason",
    "is_authorized",
]

_MAX_TELEGRAM_TEXT = 4000

# Zeitfenster (Sekunden) fuer die Antwort auf eine Stufe-2/3-Rueckfrage
# (ADR-045). Laeuft es ab, gilt fail-closed "keine Bestaetigung" - der
# Executor bricht mit seiner bestehenden Meldung ab.
_CONFIRMATION_TIMEOUT = 120.0

# Zeitlimit (Sekunden), das stop() auf das Zustellen noch ausstehender Antworten
# wartet, bevor der Event-Loop gestoppt wird. Sichert die "ich fahre herunter"-
# Zusage des stop_runtime-Befehls gegen den Teardown ab (fire-and-forget-Reply
# wuerde sonst mit dem Loop-Stop verloren gehen).
_SEND_FLUSH_TIMEOUT = 10.0


def _runtime_filter_plan(steps):
    """Whitelist-Filter des Runtime-Kanals: wie filter_plan, aber mit dem
    erweiterten Set (ADR-035) und - seit dem ConfirmationGate (ADR-045) -
    OHNE den Stufe-2/3-Pauschalblock: dieser Kanal hat einen echten
    Bestaetigungsweg, der Executor-Dialog uebernimmt die Kontrolle."""
    return filter_plan(steps, RUNTIME_ALLOWED_INTENTS, allow_confirmation=True)


class TelegramChannel:
    """Zweiter Runtime-Kanal (ADR-027): liest über python-telegram-bot
    Long-Polling, wendet dieselbe Whitelist wie telegram_main.py an und
    reicht erlaubte Nachrichten über runtime.submit() weiter. Bekommt
    eine bereits existierende JarvisRuntime injiziert - baut keinen
    eigenen Core-Stack auf (Core-Stack bleibt einmalig, ADR-024)."""

    def __init__(
        self,
        runtime: JarvisRuntime,
        bot_token: str,
        allowed_chat_id: str,
        transcriber=None,
    ):
        self.runtime = runtime
        self.bot_token = bot_token
        self.allowed_chat_id = allowed_chat_id
        # Sprach-Eingabe (ADR-038): optionaler Transcriber. Ist keiner injiziert
        # (z. B. kein OpenAI-Key), wird der Voice-Handler nicht registriert -
        # Textbetrieb bleibt unveraendert.
        self.transcriber = transcriber
        self._application: Optional[Application] = None
        # Der PTB-Event-Loop laeuft in DIESEM Kanal-Thread (run_polling), nicht
        # im Runtime-/Main-Thread, der stop() aufruft. _loop wird per
        # _post_init() im Loop erfasst, _loop_ready signalisiert, dass er
        # verfuegbar ist.
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_ready = threading.Event()
        # Ausstehende (fire-and-forget) Antwort-Sends. stop() wartet auf deren
        # Zustellung, bevor der Loop stoppt - sonst geht die letzte Nachricht
        # (z. B. die Herunterfahr-Zusage) verloren. Set + Lock, weil add/discard
        # im PTB-Loop-Thread, das Auslesen aber im Main-Thread passiert.
        self._pending_sends: set = set()
        self._pending_lock = threading.Lock()
        # Bestaetigungs-Briefkasten (ADR-045): der Executor-Dialog fuer
        # Stufe-2/3 bekommt darueber einen echten Antwortkanal - die naechste
        # Textnachricht des autorisierten Chats beantwortet eine offene
        # Rueckfrage (und geht dann NICHT durch den Planner).
        self.gate = ConfirmationGate()

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
        # Sprach-Eingabe (ADR-038): nur registrieren, wenn ein Transcriber da ist.
        if self.transcriber is not None:
            self._application.add_handler(MessageHandler(filters.VOICE, _on_voice))

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
        # Auflage (Zusage-vor-Teardown): ausstehende Antworten - v. a. die
        # "ich fahre herunter"-Zusage - noch zustellen, BEVOR der Loop stoppt.
        # Der Loop laeuft hier noch, die Sends laufen also durch.
        self._flush_pending_sends()
        loop.call_soon_threadsafe(app.stop_running)

    def push(self, text: str) -> None:
        """Proaktive Nachricht an den autorisierten Chat (A2, ADR-039) -
        das Gegenstueck zum reply_callback, nur OHNE vorausgehende Nachricht:
        der Scheduler der Runtime meldet faellige Eintraege. Gleiche
        threadsichere Loop-Bruecke, gleiches Pending-Tracking (die Nachricht
        wird beim Stop noch zugestellt, Zusage-vor-Teardown)."""
        app = self._application
        if app is None:
            logger.warning("push() ohne laufende Application - Nachricht verworfen: %r", text)
            return
        self._loop_ready.wait(timeout=5.0)
        loop = self._loop
        if loop is None:
            logger.warning("push(): Event-Loop nicht verfuegbar - Nachricht verworfen: %r", text)
            return

        future = asyncio.run_coroutine_threadsafe(
            _send_reply_chunks(app.bot, chat_id=self.allowed_chat_id, text=text), loop
        )
        with self._pending_lock:
            self._pending_sends.add(future)

        def _done(f: Future) -> None:
            with self._pending_lock:
                self._pending_sends.discard(f)
            _log_send_future(f)

        future.add_done_callback(_done)

    def _flush_pending_sends(self, timeout: float = _SEND_FLUSH_TIMEOUT) -> None:
        """Wartet, bis alle noch ausstehenden Antwort-Sends zugestellt sind (der
        Event-Loop laeuft zu diesem Zeitpunkt noch, future.result() blockiert
        also nur bis zur Zustellung). Fehler werden geloggt, nicht
        weitergereicht - der Shutdown darf daran nicht scheitern."""
        with self._pending_lock:
            pending = list(self._pending_sends)
        for future in pending:
            try:
                future.result(timeout=timeout)
            except Exception:
                logger.exception("Ausstehende Telegram-Antwort beim Stop nicht zugestellt.")


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


class _TelegramConfirmer:
    """Bestaetigungsweg des Telegram-Kanals (ADR-045), pro Nachricht an
    runtime.submit() uebergeben: say() schickt die Executor-Rueckfrage ueber
    den Antwortweg des ausloesenden Chats, listen() wartet auf die naechste
    Textnachricht (ConfirmationGate, Timeout => "" => Executor-Abbruch)."""

    def __init__(self, reply_callback, gate: ConfirmationGate):
        self._reply = reply_callback
        self._gate = gate

    def say(self, text: str) -> None:
        self._reply(text)

    def listen(self) -> str:
        return self._gate.wait_answer(timeout=_CONFIRMATION_TIMEOUT)


def _make_reply_callback(channel, bot, chat_id, loop):
    """Baut den reply_callback: schleust die Antwort thread-sicher auf den
    PTB-Loop (aus dem Runtime-Worker-Thread aufgerufen) und trackt den Send,
    damit stop() ihn vor dem Teardown zustellt. Von Text- UND Voice-Pfad genutzt."""

    def reply_callback(text: str) -> None:
        future = asyncio.run_coroutine_threadsafe(
            _send_reply_chunks(bot, chat_id=chat_id, text=text), loop
        )
        with channel._pending_lock:
            channel._pending_sends.add(future)

        def _done(f: Future) -> None:
            with channel._pending_lock:
                channel._pending_sends.discard(f)
            _log_send_future(f)

        future.add_done_callback(_done)

    return reply_callback


async def _on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    channel: TelegramChannel = context.application.bot_data["channel"]
    if update.effective_chat is None or update.message is None or not update.message.text:
        return

    chat_id = update.effective_chat.id
    if not is_authorized(chat_id, channel.allowed_chat_id):
        logger.warning("Nicht autorisierter Chat %s - Nachricht ignoriert.", chat_id)
        return

    # Offene Stufe-2/3-Rueckfrage (ADR-045)? Dann ist diese Nachricht die
    # ANTWORT - sie wird konsumiert und geht NIE durch den Planner (die
    # Antwort auf eine Sicherheitsfrage darf kein LLM interpretieren).
    if channel.gate.offer_answer(update.message.text):
        logger.info("Nachricht als Bestaetigungs-Antwort konsumiert (Laenge %d).", len(update.message.text))
        return

    reply_callback = _make_reply_callback(channel, context.bot, chat_id, asyncio.get_running_loop())
    # allow_async=True: die Runtime darf delegate_analysis in ihren
    # Hintergrund-Worker auslagern (Quittung sofort, Ergebnis-Push spaeter
    # ueber denselben reply_callback). Telegram bleibt reiner Transportkanal
    # (ADR-035) - die gesamte Async-Orchestrierung liegt in der Runtime.
    channel.runtime.submit(
        update.message.text,
        reply_callback,
        plan_filter=_runtime_filter_plan,
        allow_async=True,
        confirmer=_TelegramConfirmer(reply_callback, channel.gate),
        source="telegram",
    )


async def _on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sprachnachricht (ADR-038). Reihenfolge nach PO-Auflagen:
    1. NUR nach Autorisierung wird ueberhaupt Audio geladen.
    2. Audio bleibt im Speicher (kein Datei-Write).
    3. Transkription -> Echo (gegen Verhoerer) -> dieselbe Whitelist/Pipeline
       wie Text.
    4. Schlaegt die Transkription fehl oder ergibt nichts, wird NICHTS
       ausgefuehrt - nur eine klare Rueckmeldung."""
    channel: TelegramChannel = context.application.bot_data["channel"]
    if update.effective_chat is None or update.message is None or update.message.voice is None:
        return

    chat_id = update.effective_chat.id
    if not is_authorized(chat_id, channel.allowed_chat_id):
        logger.warning("Nicht autorisierter Chat %s - Sprachnachricht ignoriert.", chat_id)
        return

    reply_callback = _make_reply_callback(channel, context.bot, chat_id, asyncio.get_running_loop())

    try:
        tg_file = await context.bot.get_file(update.message.voice.file_id)
        # download_as_bytearray: nur im Speicher - kein download_to_drive (Auflage).
        audio = bytes(await tg_file.download_as_bytearray())
        transcript = await asyncio.to_thread(channel.transcriber.transcribe, audio, "voice.ogg")
    except Exception:
        logger.exception("Sprachnachricht konnte nicht verarbeitet werden.")
        reply_callback("Ich konnte die Sprachnachricht nicht verstehen - bitte nochmal oder als Text.")
        return

    if not transcript:
        reply_callback("Ich habe in der Sprachnachricht nichts verstanden - bitte nochmal.")
        return

    reply_callback(f"🎤 Verstanden: «{transcript}»")
    # Auch per Sprache AUSGELOESTE Stufe-2/3-Befehle bekommen den
    # Bestaetigungsweg - die ANTWORT auf die Rueckfrage muss aber getippt
    # werden (Sprachnachrichten werden bewusst nicht als Antwort gewertet,
    # ADR-045: Stufe 3 verlangt exakte Schreibweise, Verhoerer zu riskant).
    channel.runtime.submit(
        transcript,
        reply_callback,
        plan_filter=_runtime_filter_plan,
        allow_async=True,
        confirmer=_TelegramConfirmer(reply_callback, channel.gate),
        source="telegram",
    )
