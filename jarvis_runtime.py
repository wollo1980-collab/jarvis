"""
Jarvis-Runtime (ADR-024/025/026/027) - koordinierender, künftig
dauerhaft laufender Einstiegspunkt für mehrere gleichzeitige Kanäle.
main.py und telegram_main.py bleiben unverändert und eigenständig
(Koexistenz statt Ablösung, ADR-024) - diese Runtime ersetzt sie nicht.

Enthält:
- Core-Stack einmalig instanziiert (gleiche Verdrahtung wie main.py)
- queue.Queue + ein einzelner Worker-Thread, serialisierte Verarbeitung
  (kein asyncio in der Runtime selbst, siehe ADR-024/025)
- Fail-closed Speech-Adapter für den geteilten Executor (Sicherheitsstufe
  2/3 bleibt gesperrt, gleiches Prinzip wie TelegramSpeech in
  telegram_main.py, ADR-018) - dupliziert statt importiert, um keine
  Abhängigkeit von python-telegram-bot in dieser Datei zu erzeugen.
- Single-Instance-Schutz (ADR-026) - verhindert gleichzeitigen Betrieb
  mehrerer Jarvis-Prozesse gegen dasselbe memory_dir.
- ConsoleDummyChannel - erster, minimaler Kanal (ADR-025), kein
  Produktivkanal.
- Optionaler zweiter Kanal, TelegramChannel (telegram_channel.py,
  ADR-027) - wird nur gestartet, wenn die bekannten Umgebungsvariablen
  gesetzt UND python-telegram-bot installiert ist (verzögerter Import,
  keine Pflichtabhängigkeit für diese Datei).

Bewusst NICHT enthalten: UI, Tray, Wake-Word, Autostart, abstraktes
Channel-Interface (kein Verhaltenswert bei zwei strukturell
verschiedenen Kanälen, ADR-027), echte Nebenläufigkeits-Absicherung in
Memory (nicht nötig, da die Queue serialisiert).
"""
from __future__ import annotations

import logging
import os
import queue
import threading
from datetime import date
from typing import Callable, Optional

import commands.memory as memory_commands
import commands.monitor as monitor_commands
import commands.reports as reports_commands
from core.ai import AIEngine
from core.config import Config
from core.models import Message, Plan
from core.planner import Planner
from core.single_instance import InstanceAlreadyRunningError, SingleInstanceLock
from executor.executor import Executor
from memory.long_term import LongTermMemory
from memory.store import JsonMemoryStore

logger = logging.getLogger("jarvis.runtime")

# Sentinel-Wert, der den Worker-Thread sauber beendet (ADR-025) - eigenes
# Objekt statt None/String, damit er nie versehentlich mit einer echten
# Nachricht kollidiert.
_STOP = object()

EXIT_WORDS = {"exit", "quit", "beenden", "ende", "stop", "stopp", "tschuess", "tschüss", "bye"}


class _RuntimeSpeech:
    """Fail-closed say()/listen()-Adapter für den geteilten Executor -
    gleiches Prinzip wie TelegramSpeech (ADR-018), bewusst dupliziert
    statt importiert (keine python-telegram-bot-Abhängigkeit in der
    Runtime). Sicherheitsstufe-2/3-Commands erreichen in v1 keinen
    Kanal, der eine echte Bestätigung anbietet - lieber fail-closed als
    eine Bestätigung erfinden."""

    def say(self, text: str) -> None:
        logger.error("_RuntimeSpeech.say() aufgerufen - unerwartet in Runtime v1: %r", text)

    def listen(self) -> str:
        logger.error(
            "_RuntimeSpeech.listen() aufgerufen - unerwartet in Runtime v1. "
            "Fail closed: keine Bestätigung."
        )
        return ""


class JarvisRuntime:
    """Instanziiert den Core-Stack einmalig und verarbeitet eingehende
    Nachrichten aus beliebig vielen Kanälen seriell über eine
    queue.Queue + einen einzelnen Worker-Thread (ADR-024/025)."""

    def __init__(self, config: Config, ai: Optional[AIEngine] = None):
        self.ai = ai if ai is not None else AIEngine(config)
        self.planner = Planner(self.ai)
        self.executor = Executor(_RuntimeSpeech(), self.ai)
        self.memory = JsonMemoryStore(config.memory_dir, config.max_history_entries)
        self.long_term = LongTermMemory(config.memory_dir)

        # Gleiche configure()-Verdrahtung wie main.py - Commands werden
        # beim Modul-Import instanziiert, bevor Config/AIEngine existieren.
        memory_commands.configure(config.memory_dir)
        reports_commands.configure(self.ai)
        monitor_commands.configure(self.ai)

        self._queue: "queue.Queue" = queue.Queue()
        self._worker: Optional[threading.Thread] = None

    def start(self) -> None:
        """Startet den Worker-Thread. Nicht blockierend - Kanäle laufen
        unabhängig davon weiter."""
        self._worker = threading.Thread(
            target=self._run_worker, name="jarvis-runtime-worker", daemon=False
        )
        self._worker.start()
        logger.info("Jarvis-Runtime gestartet (Worker-Thread aktiv).")

    def stop(self) -> None:
        """Legt den Stop-Sentinel in die Queue und wartet, bis der
        Worker sauber beendet ist."""
        self._queue.put(_STOP)
        if self._worker is not None:
            self._worker.join()
        logger.info("Jarvis-Runtime gestoppt.")

    def submit(
        self,
        text: str,
        reply_callback: Callable[[str], None],
        plan_filter: Optional[Callable[[list[Plan]], tuple[list[Plan], Optional[str]]]] = None,
    ) -> None:
        """Von einem Kanal aufgerufen: legt eine Nachricht in die Queue.
        Blockiert den Aufrufer nicht - die Verarbeitung passiert
        asynchron im Worker-Thread.

        plan_filter (optional, ADR-027): wird nach dem Planen auf die
        berechneten Schritte angewendet, bevor der Executor sie sieht -
        liefert (erlaubte_schritte, Ablehnungsgrund). Damit kann ein
        Kanal (z. B. Telegram) eine eigene Whitelist durchsetzen, ohne
        dass JarvisRuntime selbst irgendetwas ueber diese Whitelist
        wissen muss. Ohne plan_filter (Default) verhaelt sich submit()
        exakt wie in Runtime v1."""
        self._queue.put((text, reply_callback, plan_filter))

    def _run_worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                self._queue.task_done()
                break
            text, reply_callback, plan_filter = item
            try:
                self._process(text, reply_callback, plan_filter)
            except Exception:
                # Der Worker darf bei Fehlern nicht still sterben - loggen
                # und mit der naechsten Nachricht weitermachen.
                logger.exception("Unerwarteter Fehler bei der Verarbeitung von: %r", text)
            finally:
                self._queue.task_done()

    def _process(
        self,
        text: str,
        reply_callback: Callable[[str], None],
        plan_filter: Optional[Callable[[list[Plan]], tuple[list[Plan], Optional[str]]]] = None,
    ) -> None:
        history = self.memory.get_history(limit=20)
        steps = self.planner.plan(text, history)

        if plan_filter is not None:
            steps, rejection = plan_filter(steps)
            if rejection:
                # Abgelehnt: Executor wird nicht aufgerufen, keine
                # History-Schreibung - exakt wie telegram_main.py's
                # JarvisBridge.handle_message() bei einer Ablehnung.
                try:
                    reply_callback(rejection)
                except Exception:
                    logger.exception(
                        "reply_callback fehlgeschlagen fuer abgelehnte Anfrage: %r", text
                    )
                return

        long_term_summary = self.long_term.summary_text()
        report = self.executor.run(steps, history, long_term_summary)
        response_text = "\n".join(report.summary_lines()) or "Alles klar."

        self.memory.append_history(Message(role="user", content=text))
        self.memory.append_history(Message(role="assistant", content=response_text))

        try:
            reply_callback(response_text)
        except Exception:
            # Ein kaputter reply_callback (z. B. Kanal bereits weg) darf
            # den Worker ebenfalls nicht mitreissen.
            logger.exception("reply_callback fehlgeschlagen fuer: %r", text)


class ConsoleDummyChannel:
    """Erster, minimaler Runtime-Kanal (ADR-025): liest interaktiv von
    der Konsole, reicht jede Zeile ueber runtime.submit() weiter,
    wartet auf die Antwort und druckt sie. Kein Produktivkanal - beweist
    nur, dass das Runtime-Geruest tatsaechlich funktioniert."""

    def __init__(self, runtime: JarvisRuntime):
        self.runtime = runtime

    def run(self) -> None:
        print("Jarvis-Runtime (Konsolen-Dummy-Kanal) ist bereit.")
        while True:
            user_input = input("Du: ").strip()
            if user_input.lower() in EXIT_WORDS:
                break
            if not user_input:
                continue
            self._handle(user_input)

    def _handle(self, user_input: str) -> None:
        done = threading.Event()
        result: dict = {}

        def reply_callback(response_text: str) -> None:
            result["text"] = response_text
            done.set()

        self.runtime.submit(user_input, reply_callback)
        done.wait()
        print(f"Jarvis: {result.get('text', '')}")


def setup_logging(config: Config) -> None:
    log_file = config.log_dir / f"{date.today().isoformat()}-runtime.log"
    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
    )


# Dieselben Umgebungsvariablen wie telegram_main.py (ADR-018) - Werte
# hier als eigene Literale gehalten statt aus telegram_main importiert,
# damit jarvis_runtime.py ohne python-telegram-bot importierbar bleibt
# (der Import von TelegramChannel/telegram_main erfolgt nur verzögert,
# innerhalb von _start_telegram_channel(), ADR-027).
TELEGRAM_BOT_TOKEN_ENV = "JARVIS_TELEGRAM_BOT_TOKEN"
TELEGRAM_ALLOWED_CHAT_ID_ENV = "JARVIS_TELEGRAM_ALLOWED_CHAT_ID"


def _start_telegram_channel(runtime: JarvisRuntime):
    """Startet TelegramChannel (ADR-027) in einem eigenen Thread, falls
    die bekannten Umgebungsvariablen gesetzt UND python-telegram-bot
    installiert ist - liefert (channel, thread) oder None. Ohne
    Telegram-Konfiguration verhält sich main() exakt wie in Runtime v1
    (nur ConsoleDummyChannel)."""
    bot_token = os.environ.get(TELEGRAM_BOT_TOKEN_ENV)
    allowed_chat_id = os.environ.get(TELEGRAM_ALLOWED_CHAT_ID_ENV)
    if not bot_token or not allowed_chat_id:
        logger.info(
            "Kein Telegram-Kanal gestartet - %s/%s nicht gesetzt.",
            TELEGRAM_BOT_TOKEN_ENV,
            TELEGRAM_ALLOWED_CHAT_ID_ENV,
        )
        return None

    try:
        from telegram_channel import TelegramChannel
    except ImportError:
        logger.warning(
            "Telegram-Umgebungsvariablen gesetzt, aber python-telegram-bot "
            "ist nicht installiert - Telegram-Kanal wird uebersprungen."
        )
        return None

    channel = TelegramChannel(runtime, bot_token, allowed_chat_id)
    thread = threading.Thread(target=channel.run, name="jarvis-runtime-telegram", daemon=True)
    thread.start()
    logger.info("TelegramChannel gestartet (eigener Thread, Runtime v2).")
    return channel, thread


def main() -> None:
    config = Config.load()
    setup_logging(config)

    # Single-Instance-Schutz (ADR-026): allererste Aktion, vor jedem
    # Core-Stack-Aufbau - main.py, telegram_main.py und jarvis_runtime.py
    # teilen sich ohne besondere Konfiguration dasselbe memory_dir, das
    # keinerlei Locking hat.
    lock = SingleInstanceLock(config.memory_dir, entry_point="jarvis_runtime.py")
    try:
        lock.acquire()
    except InstanceAlreadyRunningError as e:
        logger.error("Start abgebrochen: %s", e)
        print(f"Jarvis-Runtime konnte nicht gestartet werden: {e}")
        return

    try:
        runtime = JarvisRuntime(config)
        runtime.start()

        telegram = _start_telegram_channel(runtime)

        channel = ConsoleDummyChannel(runtime)
        try:
            channel.run()
        finally:
            if telegram is not None:
                telegram_channel_obj, telegram_thread = telegram
                telegram_channel_obj.stop()
                telegram_thread.join(timeout=5.0)
            runtime.stop()
    finally:
        lock.release()


if __name__ == "__main__":
    main()
