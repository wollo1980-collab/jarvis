"""
Jarvis-Runtime (ADR-024/025/026/027/028) - koordinierender, künftig
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
  Produktivkanal. Wird nur gestartet, wenn ein Konsolenfenster vorhanden
  ist (sys.stdin is not None) - beim Jarvis-Eigenstart (ADR-028, über
  pythonw.exe) fehlt das absichtlich, siehe main().
- Optionaler zweiter Kanal, TelegramChannel (telegram_channel.py,
  ADR-027) - wird nur gestartet, wenn die bekannten Umgebungsvariablen
  gesetzt UND python-telegram-bot installiert ist (verzögerter Import,
  keine Pflichtabhängigkeit für diese Datei).
- Jarvis-Eigenstart (ADR-028): registriert/entfernt sich selbst als
  Windows-Autostart-Eintrag über die Commands `enable_/
  disable_jarvis_autostart` (commands/monitor.py) - reine
  Command-Erweiterung, keine Runtime-Architekturänderung. Einzige
  Auswirkung hier: main()/setup_logging() prüfen einmal, ob ein
  Konsolenfenster vorhanden ist, und starten ConsoleDummyChannel bzw.
  den Konsolen-Log-Handler nur dann.

Bewusst NICHT enthalten: UI, Tray, Wake-Word, abstraktes
Channel-Interface (kein Verhaltenswert bei zwei strukturell
verschiedenen Kanälen, ADR-027), echte Nebenläufigkeits-Absicherung in
Memory (nicht nötig, da die Queue serialisiert).
"""
from __future__ import annotations

import logging
import os
import queue
import sys
import threading
from datetime import date
from typing import Callable, Optional

import commands.delegate as delegate_commands
import commands.entries as entries_commands
import commands.mail as mail_commands
import commands.memory as memory_commands
import commands.monitor as monitor_commands
import commands.plan as plan_commands
import commands.reports as reports_commands
import commands.shutdown as shutdown_commands
import commands.web as web_commands
from commands import REGISTRY
from core.agent_backend import ClaudeCodeBackend
from core.ai import AIEngine
from core.config import Config
from core.models import Message, Plan
from core.planner import Planner
from core.single_instance import InstanceAlreadyRunningError, SingleInstanceLock
from executor.executor import ExecutionReport, Executor
from memory.long_term import LongTermMemory
from memory.store import JsonMemoryStore

logger = logging.getLogger("jarvis.runtime")

# Sentinel-Wert, der den Worker-Thread sauber beendet (ADR-025) - eigenes
# Objekt statt None/String, damit er nie versehentlich mit einer echten
# Nachricht kollidiert.
_STOP = object()

# Hartes Zeitlimit (Sekunden), das stop() auf das Einsammeln eines laufenden
# Delegations-Threads wartet, nachdem der Kill-Switch gesetzt wurde (ADR-035).
# Da der Kill-Switch den claude-Prozess terminiert, endet der Thread praktisch
# sofort; das Limit ist nur die Sicherung gegen einen Haenger.
_DELEGATION_JOIN_TIMEOUT = 15.0

# Sicherheitsnetz-Timeout (Sekunden) fuer den synchronen Konsolenkanal
# (Audit-Fix P1a). Grosszuegig ueber dem Standard-agent_timeout (300 s), damit
# eine legitime synchrone Konsolen-Delegation nie faelschlich abgeschnitten wird;
# er verhindert nur einen kuenftigen Endlos-Hang bei ausbleibendem reply_callback.
_CONSOLE_REPLY_TIMEOUT = 600.0

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
        # Eintraege (A1): Erinnerungen/Aufgaben/Merkposten, eigener Store
        # neben dem Langzeitgedaechtnis (memory/entries.py).
        entries_commands.configure(config.memory_dir)
        reports_commands.configure(self.ai)
        monitor_commands.configure(self.ai)
        web_commands.configure(self.ai, timeout_seconds=config.timeout)
        mail_commands.configure(config)
        # Agenten-Delegation (ADR-034): read-only Repo-Analyse. Backend aus der
        # Verdrahtungsschicht injiziert (Fachlogik nennt kein Backend, ADR-036).
        delegate_commands.configure(config, ClaudeCodeBackend())
        # Nächsten Schritt planen (ADR-036 / Handbook 4.2): Backend in der
        # Verdrahtungsschicht gewählt und injiziert (Fachlogik nennt kein
        # konkretes Backend, Modellunabhängigkeit).
        plan_commands.configure(config, ClaudeCodeBackend())
        # Beenden-Befehl (stop_runtime): injizierter Hook legt das Stop-Sentinel
        # in die Queue - der Befehl kennt die Runtime nicht (entkoppelt), und
        # weil nur die Queue befuellt wird, gibt es keinen Selbst-Join des
        # Worker-Threads (Deadlock-Falle vermieden).
        shutdown_commands.configure(self._request_shutdown)

        self._queue: "queue.Queue" = queue.Queue()
        self._worker: Optional[threading.Thread] = None

        # Asynchrone Repo-Analyse (ADR-035): ein von der Runtime besessener
        # Hintergrund-Worker fuer langlaufende (long_running) Commands, damit
        # der serielle Nachrichten-Worker nicht minutenlang blockiert.
        # Nebenlaeufigkeit bewusst = 1 (ADR-035): ein einzelnes Flag unter einem
        # Lock, KEIN Scheduler/keine Warteschlange - deckt "genau eine
        # gleichzeitige Delegation" exakt ab (erweiterbar, falls je noetig).
        self._state_lock = threading.Lock()
        self._delegation_active = False
        self._delegation_thread: Optional[threading.Thread] = None
        self._delegation_cancel: Optional[threading.Event] = None

    def start(self) -> None:
        """Startet den Worker-Thread. Nicht blockierend - Kanäle laufen
        unabhängig davon weiter."""
        self._worker = threading.Thread(
            target=self._run_worker, name="jarvis-runtime-worker", daemon=False
        )
        self._worker.start()
        logger.info("Jarvis-Runtime gestartet (Worker-Thread aktiv).")

    def _request_shutdown(self) -> None:
        """Hook fuer den stop_runtime-Befehl (aus der Verdrahtungsschicht
        injiziert): legt das Stop-Sentinel in die Queue. Der Worker zieht es
        erst in der NAECHSTEN Runde - also nachdem die aktuelle Nachricht
        (inkl. der 'ich fahre herunter'-Zusage) fertig verarbeitet ist. main()
        wacht dann aus worker.join() auf und faehrt im finally sauber herunter.
        Bewusst KEIN join() hier: der Aufruf laeuft auf dem Worker-Thread selbst
        (der Befehl wird dort ausgefuehrt) - ein join wuerde sich selbst
        blockieren."""
        self._queue.put(_STOP)

    def stop(self) -> None:
        """Legt den Stop-Sentinel in die Queue und wartet, bis der
        Worker sauber beendet ist. Beendet ausserdem eine ggf. laufende
        Hintergrund-Delegation (ADR-035): Kill-Switch setzen (terminiert den
        claude-Prozess) und den Thread mit hartem Zeitlimit einsammeln - so
        haengt der Shutdown nicht bis zum Agenten-Timeout."""
        self._queue.put(_STOP)
        if self._worker is not None:
            self._worker.join()

        cancel = self._delegation_cancel
        if cancel is not None:
            cancel.set()
        thread = self._delegation_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=_DELEGATION_JOIN_TIMEOUT)
            if thread.is_alive():
                logger.warning(
                    "Delegations-Thread nach %.0fs noch aktiv - Shutdown wird fortgesetzt.",
                    _DELEGATION_JOIN_TIMEOUT,
                )
        logger.info("Jarvis-Runtime gestoppt.")

    def submit(
        self,
        text: str,
        reply_callback: Callable[[str], None],
        plan_filter: Optional[Callable[[list[Plan]], tuple[list[Plan], Optional[str]]]] = None,
        allow_async: bool = False,
    ) -> None:
        """Von einem Kanal aufgerufen: legt eine Nachricht in die Queue.
        Blockiert den Aufrufer nicht - die Verarbeitung passiert
        asynchron im Worker-Thread.

        plan_filter (optional, ADR-027): wird nach dem Planen auf die
        berechneten Schritte angewendet, bevor der Executor sie sieht -
        liefert (erlaubte_schritte, Ablehnungsgrund). Damit kann ein
        Kanal (z. B. Telegram) eine eigene Whitelist durchsetzen, ohne
        dass JarvisRuntime selbst irgendetwas ueber diese Whitelist
        wissen muss.

        allow_async (optional, ADR-035): erlaubt der Runtime, einen
        langlaufenden (long_running) Command - die Repo-Analyse - NICHT im
        seriellen Nachrichten-Worker auszufuehren, sondern im Hintergrund
        (sofortige Quittung, spaeter Ergebnis-Push ueber denselben
        reply_callback). Nur Kanaele mit einem push-faehigen reply_callback
        (Telegram-Runtime-Kanal) setzen True; die Konsole bleibt synchron.
        Ohne die neuen Argumente (Default) verhaelt sich submit() exakt wie
        in Runtime v1/v2."""
        self._queue.put((text, reply_callback, plan_filter, allow_async))

    def _run_worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                self._queue.task_done()
                break
            text, reply_callback, plan_filter, allow_async = item
            try:
                self._process(text, reply_callback, plan_filter, allow_async)
            except Exception:
                # Der Worker darf bei Fehlern nicht still sterben - loggen
                # und mit der naechsten Nachricht weitermachen. Wichtig
                # (Audit-Fix P1a): der Kanal MUSS trotzdem eine Antwort
                # bekommen, sonst wartet ein synchroner Kanal (Konsole) ewig
                # auf reply_callback und haengt.
                logger.exception("Unerwarteter Fehler bei der Verarbeitung von: %r", text)
                self._safe_reply(
                    reply_callback,
                    "Es ist ein unerwarteter Fehler aufgetreten - ich konnte die Anfrage nicht verarbeiten.",
                    text,
                )
            finally:
                self._queue.task_done()

    def _process(
        self,
        text: str,
        reply_callback: Callable[[str], None],
        plan_filter: Optional[Callable[[list[Plan]], tuple[list[Plan], Optional[str]]]] = None,
        allow_async: bool = False,
    ) -> None:
        history = self.memory.get_history(limit=20)
        steps = self.planner.plan(text, history)

        if plan_filter is not None:
            steps, rejection = plan_filter(steps)
            if rejection:
                # Abgelehnt: Executor wird nicht aufgerufen, keine
                # History-Schreibung - exakt wie telegram_main.py's
                # JarvisBridge.handle_message() bei einer Ablehnung.
                self._safe_reply(reply_callback, rejection, text)
                return

        # Asynchroner Zweig (ADR-035): ein einzelner langlaufender Command
        # (Repo-Analyse) wird - wenn der Kanal es erlaubt - in den
        # Hintergrund-Worker ausgelagert, damit der Nachrichten-Worker sofort
        # frei ist. Sicherheitspruefung (plan_filter) ist zu diesem Zeitpunkt
        # bereits erfolgt.
        if allow_async:
            command = self._async_command(steps)
            if command is not None:
                self._dispatch_delegation(text, steps[0], command, reply_callback)
                return

        long_term_summary = self.long_term.summary_text()
        report = self.executor.run(steps, history, long_term_summary)
        response_text = "\n".join(report.summary_lines()) or "Alles klar."

        self.memory.append_history(Message(role="user", content=text))
        self.memory.append_history(Message(role="assistant", content=response_text))
        self._safe_reply(reply_callback, response_text, text)

    def _safe_reply(
        self, reply_callback: Callable[[str], None], message: str, source_text: str
    ) -> None:
        """Ruft den reply_callback und faengt Fehler ab - ein kaputter
        Callback (z. B. Kanal bereits weg) darf weder den Worker noch den
        Delegations-Thread mitreissen."""
        try:
            reply_callback(message)
        except Exception:
            logger.exception("reply_callback fehlgeschlagen fuer: %r", source_text)

    @staticmethod
    def _async_command(steps: list[Plan]):
        """Liefert den Command-Objekt, wenn der Plan genau ein Schritt ist,
        dessen registrierter Command als long_running markiert ist - sonst
        None. Kein hartkodierter Intent-Name: die Entscheidung haengt allein
        am Command-Attribut (Muster wie requires_confirmation)."""
        if len(steps) != 1:
            return None
        command = REGISTRY.get(steps[0].intent)
        if command is not None and getattr(command, "long_running", False):
            return command
        return None

    def _dispatch_delegation(
        self, text: str, step: Plan, command, reply_callback: Callable[[str], None]
    ) -> None:
        """Belegt den (einzigen) Delegations-Slot, quittiert sofort und
        startet den Hintergrund-Thread. Ist bereits eine Delegation aktiv,
        wird die Anfrage hoeflich abgelehnt (Nebenlaeufigkeit = 1, ADR-035) -
        ohne History-Schreibung, wie bei einer Ablehnung."""
        with self._state_lock:
            if self._delegation_active:
                busy = True
            else:
                self._delegation_active = True
                busy = False
        if busy:
            self._safe_reply(
                reply_callback,
                "Es läuft bereits eine Analyse - ich melde mich, sobald sie fertig ist.",
                text,
            )
            return

        # Generische Quittung: die Runtime kennt den konkreten long_running-
        # Command nicht (ADR-036) - kein hartkodiertes "analysiere '<repo>'".
        self._safe_reply(
            reply_callback,
            "Verstanden - ich kümmere mich darum und melde mich, sobald das Ergebnis da ist.",
            text,
        )
        cancel_event = threading.Event()
        self._delegation_cancel = cancel_event
        thread = threading.Thread(
            target=self._run_delegation,
            args=(text, step, command, reply_callback, cancel_event),
            name="jarvis-delegation",
            daemon=False,
        )
        self._delegation_thread = thread
        thread.start()

    def _run_delegation(
        self,
        text: str,
        step: Plan,
        command,
        reply_callback: Callable[[str], None],
        cancel_event: threading.Event,
    ) -> None:
        """Laeuft im Hintergrund-Thread: fuehrt die Analyse cancelbar aus,
        schreibt das Ergebnis (user + assistant) ins Gedaechtnis und pusht die
        Antwort. Das Busy-Flag wird IMMER im finally freigegeben - auch bei
        einer Exception im Hintergrund -, damit der Slot nie dauerhaft belegt
        bleibt."""
        try:
            result = command.run_async(step, cancel_event)
            response_text = "\n".join(ExecutionReport(results=[result]).summary_lines()) or "Alles klar."
            self.memory.append_history(Message(role="user", content=text))
            self.memory.append_history(Message(role="assistant", content=response_text))
            self._safe_reply(reply_callback, response_text, text)
        except Exception:
            # Audit-Fix P1b: Nach der Quittung MUSS ein Abschluss folgen -
            # bei einer unerwarteten Exception ein finaler Fehler-Push, nicht
            # nur ein Log-Eintrag (sonst bleibt es beim "melde mich" ohne Ende).
            logger.exception("Hintergrund-Delegation fehlgeschlagen fuer: %r", text)
            self._safe_reply(
                reply_callback,
                "Die Aufgabe ist unerwartet fehlgeschlagen - ich konnte kein Ergebnis liefern.",
                text,
            )
        finally:
            with self._state_lock:
                self._delegation_active = False


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
        # Sicherheitsnetz (Audit-Fix P1a): grosszuegiger Timeout statt
        # unbegrenztem Warten - dank Fehler-Reply im Worker feuert reply_callback
        # jetzt auf jedem Pfad, der Timeout verhindert nur einen kuenftigen
        # Endlos-Hang (z. B. bei einem toten Worker). Grosszuegig, weil eine
        # synchrone Konsolen-Delegation legitim Minuten dauern darf.
        if not done.wait(timeout=_CONSOLE_REPLY_TIMEOUT):
            print("Jarvis: (keine Antwort erhalten - der Verarbeitungs-Thread reagiert nicht.)")
            return
        print(f"Jarvis: {result.get('text', '')}")


def setup_logging(config: Config) -> None:
    log_file = config.log_dir / f"{date.today().isoformat()}-runtime.log"
    handlers: list[logging.Handler] = [logging.FileHandler(log_file, encoding="utf-8")]
    if sys.stderr is not None:
        # Kein Konsolenfenster (z. B. Autostart ueber pythonw.exe,
        # ADR-028) -> sys.stderr ist None, StreamHandler() wuerde beim
        # ersten Log-Aufruf abstuerzen. FileHandler bleibt in jedem Fall
        # aktiv, kein Log geht verloren.
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    _dampen_http_loggers()


def _dampen_http_loggers() -> None:
    """Sicherheit: python-telegram-bot laesst httpx/httpcore den Request-URL
    protokollieren - inkl. Bot-Token im Pfad
    (https://api.telegram.org/bot<TOKEN>/...). Diese Logger auf WARNING heben,
    damit der Token nie in Logdatei/Konsole landet - bewusst auch im
    Debug-Modus (ein Secret gehoert unter keinen Umstaenden ins Log). WARNING
    zeigt echte HTTP-Fehler weiterhin an."""
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# Dieselben Umgebungsvariablen wie telegram_main.py (ADR-018) - Werte
# hier als eigene Literale gehalten statt aus telegram_main importiert,
# damit jarvis_runtime.py ohne python-telegram-bot importierbar bleibt
# (der Import von TelegramChannel/telegram_main erfolgt nur verzögert,
# innerhalb von _start_telegram_channel(), ADR-027).
TELEGRAM_BOT_TOKEN_ENV = "JARVIS_TELEGRAM_BOT_TOKEN"
TELEGRAM_ALLOWED_CHAT_ID_ENV = "JARVIS_TELEGRAM_ALLOWED_CHAT_ID"


def _start_telegram_channel(runtime: JarvisRuntime, config: Config):
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

    # Sprach-Eingabe (ADR-038): Transcriber aus dem OpenAI-Key bauen. Ohne Key
    # bleibt er None -> nur Text (der Voice-Handler wird dann nicht registriert).
    transcriber = None
    if config.openai_api_key:
        try:
            from core.transcribe import OpenAITranscriber

            transcriber = OpenAITranscriber(config.openai_api_key, config.transcription_model)
        except Exception:
            logger.warning("Transcriber nicht verfuegbar - Sprach-Eingabe deaktiviert.", exc_info=True)

    channel = TelegramChannel(runtime, bot_token, allowed_chat_id, transcriber=transcriber)
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
        if sys.stdout is not None:
            print(f"Jarvis-Runtime konnte nicht gestartet werden: {e}")
        return

    try:
        runtime = JarvisRuntime(config)
        runtime.start()

        telegram = _start_telegram_channel(runtime, config)

        try:
            if sys.stdin is not None:
                ConsoleDummyChannel(runtime).run()
            else:
                # Kein Konsolenfenster (z. B. Autostart ueber pythonw.exe,
                # ADR-028) - ConsoleDummyChannel selbst bleibt unveraendert,
                # wird hier aber gar nicht erst gestartet: input() haette
                # ohne verfuegbares stdin sofort mit einer Exception
                # abgebrochen. Haelt den Prozess stattdessen ueber den
                # bereits laufenden Worker-Thread am Leben, bis der Prozess
                # von aussen beendet wird (kein Konsolen-Exit-Wort moeglich).
                logger.info(
                    "Kein Konsolenfenster vorhanden - ConsoleDummyChannel wird uebersprungen."
                )
                runtime._worker.join()
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
