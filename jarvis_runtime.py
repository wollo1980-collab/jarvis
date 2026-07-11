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
import time
from datetime import date, datetime
from typing import Callable, Optional

import commands.delegate as delegate_commands
import commands.briefing as briefing_commands
import commands.entries as entries_commands
import commands.ideas as ideas_commands
import commands.impulses as impulses_commands
import commands.review as review_commands
import commands.verify as verify_commands
import commands.lists as lists_commands
import commands.mail as mail_commands
import commands.memory as memory_commands
import commands.monitor as monitor_commands
import commands.plan as plan_commands
import commands.project as project_commands
import commands.news as news_commands
import commands.owner as owner_commands
import commands.restart as restart_commands
import commands.shutdown as shutdown_commands
import commands.weather as weather_commands
import commands.web as web_commands
from pathlib import Path

from commands import REGISTRY, dispatch
from core.agent_backend import ClaudeCodeBackend, RedirectChannel
from core.ai import AIEngine
from core.config import BASE_DIR, Config
from core.fileio import read_json, write_json_atomic
from core.models import Message, Plan
from core.redaction import redact
from core.planner import Planner
from core.single_instance import InstanceAlreadyRunningError, SingleInstanceLock
from core.speech import SpeechEngine
from executor.executor import ExecutionReport, Executor, request_confirmation
from memory.entries import Entry, format_when
from memory.habits import HabitStats
from memory.long_term import LongTermMemory
from memory.store import JsonMemoryStore

logger = logging.getLogger("jarvis.runtime")

# Antworten, die ein schwebendes Merk-Angebot (ADR-051) annehmen/ablehnen -
# bewusst eng (nur eindeutige Kurzantworten); alles andere laesst das
# Angebot still verfallen und wird als normale Nachricht verarbeitet.
_OFFER_YES = {"ja", "j", "yes", "gerne", "ja bitte", "merk dir das"}
_OFFER_NO = {"nein", "n", "no", "lieber nicht", "nicht merken"}

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

# Neustart (restart_runtime, Welle 3.4): Der Nachfolger-Prozess erbt dieses
# Env-Flag und wartet damit bis zu N Sekunden auf die Freigabe des
# Single-Instance-Locks (Staffelstab), statt am noch laufenden Vorgaenger
# sofort zu sterben. Ohne das Flag (normaler Start) bleibt der
# Doppelstart-Schutz unveraendert hart.
WAIT_FOR_LOCK_ENV = "JARVIS_WAIT_FOR_LOCK"
_RESTART_WAIT_SECONDS = 30.0

# Scheduler (A2, ADR-039): Poll-Intervall der Faelligkeits-Pruefung. 30 s ist
# fuer minutengenaue Erinnerungen mehr als ausreichend und praktisch lastfrei.
_SCHEDULER_POLL_SECONDS = 30.0
# Impuls-Kreislauf (ADR-054): eigener, deutlich langsamer Takt auf demselben
# Scheduler-Thread - Unwetter/Gewohnheiten aendern sich in Minuten, nicht
# Sekunden; der gecachte Wetterabruf (30-Min-TTL) wird so nie gehaemmert.
_IMPULSE_INTERVAL_SECONDS = 900.0
# Zeitlimit fuers Einsammeln des Scheduler-Threads beim Stop.
_SCHEDULER_JOIN_TIMEOUT = 5.0
# Ab dieser Verspaetung (Sekunden) wird eine Nachholung ehrlich als
# "verspaetet" markiert (z. B. Jarvis war zur Faelligkeit nicht an).
_LATE_THRESHOLD_SECONDS = 120.0


def _format_due_message(entry: Entry) -> str:
    """Baut die proaktive Erinnerungs-Nachricht (A2). Ganztaegige Eintraege
    (reines Datum, faellig ab Mitternacht) gelten nie als 'verspaetet' -
    die Tages-Erinnerung kommt planmaessig morgens beim ersten Tick."""
    star = "⭐ " if entry.important else ""
    late = False
    if len(entry.when) > 10:
        try:
            due = datetime.fromisoformat(entry.when)
            now = datetime.now(due.tzinfo) if due.tzinfo else datetime.now()
            late = (now - due).total_seconds() > _LATE_THRESHOLD_SECONDS
        except ValueError:
            pass
    repeat_hint = {"taeglich": " ↻ täglich", "woechentlich": " ↻ wöchentlich"}.get(
        entry.repeat, ""
    )
    if late:
        return (
            f"🔔 {star}Erinnerung (verspätet - war fällig {format_when(entry.when)}): "
            f"«{entry.text}» — ich war kurz außer Dienst, Sir.{repeat_hint}"
        )
    return f"🔔 {star}Eine Erinnerung, Sir: «{entry.text}» — fällig {format_when(entry.when)}.{repeat_hint}"

EXIT_WORDS = {"exit", "quit", "beenden", "ende", "stop", "stopp", "tschuess", "tschüss", "bye"}


class _RuntimeSpeech:
    """say()/listen()-Adapter für den geteilten Executor. Default:
    fail-closed (gleiches Prinzip wie TelegramSpeech, ADR-018) - ohne
    echten Bestätigungsweg wird keine Bestätigung erfunden.

    Seit ADR-045 kann ein Kanal pro Nachricht einen `confirmer` mitgeben
    (say -> Antwortweg des Chats, listen -> ConfirmationGate); der Worker
    setzt ihn vor der Verarbeitung und räumt ihn im finally ab. Kanäle
    OHNE confirmer (PTT/Wake/Konsole der Runtime) bleiben exakt
    fail-closed wie zuvor."""

    def __init__(self):
        self.confirmer = None  # pro Nachricht gesetzt (ADR-045), sonst None

    def say(self, text: str) -> None:
        confirmer = self.confirmer
        if confirmer is not None:
            confirmer.say(text)
            return
        logger.error("_RuntimeSpeech.say() ohne Bestätigungsweg aufgerufen: %r", text)

    def listen(self) -> str:
        confirmer = self.confirmer
        if confirmer is not None:
            return confirmer.listen()
        logger.error(
            "_RuntimeSpeech.listen() ohne Bestätigungsweg aufgerufen. "
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
        self._speech = _RuntimeSpeech()
        self.executor = Executor(self._speech, self.ai)
        self.memory = JsonMemoryStore(config.memory_dir, config.max_history_entries)
        self._memory_dir = Path(config.memory_dir)  # fuer stille UI-Aktionen (Vorschlag verwerfen)
        self.long_term = LongTermMemory(config.memory_dir)
        # Gewohnheits-Statistik (ADR-053): reine Zaehlwerte Intent x
        # (Wochentag, Stunde) - Datengrundlage fuer Gewohnheits-Lernen
        # Stufe 2. Die Frage-Mechanik folgt separat mit PO-Feintuning.
        self.habits = HabitStats(config.memory_dir)

        # Gleiche configure()-Verdrahtung wie main.py - Commands werden
        # beim Modul-Import instanziiert, bevor Config/AIEngine existieren.
        # Umlenken (ADR-056 Scheibe 3): EIN dauerhafter Draht (Single-Flight,
        # genau eine Delegation gleichzeitig). Der Backend-Adapter zieht daraus
        # waehrend eines interaktiven Laufs; redirect_delegation() legt hinein.
        # Vor der delegate-configure() gesetzt, da es dort mitgegeben wird.
        self._redirect_channel = RedirectChannel()
        memory_commands.configure(config.memory_dir)
        # Anzeigename auf Zuruf (ADR-057): "nenn mich X" -> owner_name. MUSS
        # dasselbe Config-Objekt bekommen wie die AIEngine (self.ai), damit der
        # Chat live folgt; long_term, um alte Namens-Fakten zu raeumen.
        owner_commands.configure(config, self.long_term)
        # Eintraege (A1): Erinnerungen/Aufgaben/Merkposten, eigener Store
        # neben dem Langzeitgedaechtnis (memory/entries.py). DIESELBE Instanz
        # dient dem Scheduler (A2) - zwei Instanzen haetten getrennte Locks.
        self._entry_store = entries_commands.configure(config.memory_dir)
        # Benannte Listen (Einkaufsliste & Co.): eigener Datenlayer wie
        # Eintraege, Undo-Papierkorb statt Loeschen-Rueckfrage.
        list_store = lists_commands.configure(config.memory_dir)
        # Morgen-Briefing (Ziellinie v1.5 P3): bekommt DIESELBEN Store-
        # Instanzen (getrennte Instanzen haetten getrennte Locks).
        briefing_commands.configure(
            self._entry_store, list_store,
            config.weather_default_location, config.news_feeds, config.timeout,
        )
        # Ideen-Befehl (Angestellten-Vision Stufe 1): geerdet in Registry,
        # Nutzungs-Statistik und aktuellem Stand - geteilte Instanzen.
        ideas_commands.configure(self.ai, self.habits, self._entry_store, list_store)
        # Wochen-Rueckblick: CHANGELOG + Delegations-Logs (deterministisch).
        review_commands.configure(BASE_DIR / "docs" / "CHANGELOG.md", config.log_dir)
        # Impuls-Kreislauf (Endsystem-Kampagne, ADR-054): Jarvis' Herzschlag.
        # EINE geteilte Store-Instanz - die Engine legt Impulse, der ✕-Klick
        # (dismiss_impulse) klickt sie weg; getrennte Instanzen saehen die
        # Nein-Liste des jeweils anderen nicht.
        from memory.impulses import ImpulseStore
        from core.impulses import ImpulseEngine, make_weather_checker

        self._impulse_store = ImpulseStore(config.memory_dir)
        impulses_commands.configure(self._impulse_store)
        self._impulse_engine: Optional[ImpulseEngine] = None
        if bool(getattr(config, "impulses_enabled", True)):
            checkers = [make_weather_checker(config.weather_default_location)]
            self._impulse_engine = ImpulseEngine(self._impulse_store, checkers)
        self._last_impulse_monotonic = 0.0
        monitor_commands.configure(self.ai)
        web_commands.configure(self.ai, timeout_seconds=config.timeout)
        # News-Briefing (ADR-042): RSS-Feeds aus der Config.
        news_commands.configure(config.news_feeds, timeout_seconds=config.timeout)
        # Wetter (ADR-043): Standard-Ort aus der Config.
        weather_commands.configure(config.weather_default_location, timeout_seconds=config.timeout)
        # Projektstart (ADR-049): Pfade aus der Config, leer = aus.
        project_commands.configure(config.projects_root, config.framework_repo)
        mail_commands.configure(config)
        # Agenten-Delegation (ADR-034): read-only Repo-Analyse. Backend aus der
        # Verdrahtungsschicht injiziert (Fachlogik nennt kein Backend, ADR-036).
        # ai fuer project_continue (Stufe 2): baut den Delegations-Auftrag
        # aus dem Projektstand des Zielrepos.
        delegate_commands.configure(config, ClaudeCodeBackend(), ai=self.ai,
                                    event_sink=self._agent_event_sink,
                                    redirect=self._redirect_channel)
        # Nächsten Schritt planen (ADR-036 / Handbook 4.2): Backend in der
        # Verdrahtungsschicht gewählt und injiziert (Fachlogik nennt kein
        # konkretes Backend, Modellunabhängigkeit).
        plan_commands.configure(config, ClaudeCodeBackend())
        # Selbstkontrolle Stufe 3 (ADR-055): Verifikations-Harnisch - Allowlist
        # aus denselben Repo-Listen wie die Delegation (fail-closed).
        verify_commands.configure(config)
        # Beenden-Befehl (stop_runtime): injizierter Hook legt das Stop-Sentinel
        # in die Queue - der Befehl kennt die Runtime nicht (entkoppelt), und
        # weil nur die Queue befuellt wird, gibt es keinen Selbst-Join des
        # Worker-Threads (Deadlock-Falle vermieden).
        shutdown_commands.configure(self._request_shutdown)
        # Neustart-Befehl (restart_runtime, Welle 3.4): gleiches Muster -
        # Nachfolger-Prozess starten, dann Stop-Sentinel. Der Spawner ist als
        # Instanz-Attribut injizierbar (Tests starten keinen echten Prozess).
        self._spawn_successor: Callable[[], bool] = _spawn_successor_process
        # Nachtplan Scheibe 6: beim Neustart zieht das Dashboard mit um.
        self._restart_dashboard: Callable[[], None] = _restart_dashboard_process
        restart_commands.configure(self._request_restart)

        self._queue: "queue.Queue" = queue.Queue()
        self._worker: Optional[threading.Thread] = None

        # Merk-Angebot (ADR-051): ein NEBENBEI erkannter dauerhafter Fakt
        # schwebt genau bis zur naechsten Nachricht - "ja" speichert, "nein"
        # landet auf der Nein-Liste, alles andere laesst ihn still verfallen.
        # Worker ist seriell (ein Angebot zur Zeit, kein Lock noetig).
        # Tupel (kanal, fakt) - Nacht-Audit-Fix A: kanalgebunden.
        self._memory_offers_enabled = bool(getattr(config, "memory_offers_enabled", False))
        self._memory_offer: Optional[tuple] = None
        self._declined_offers_path = Path(config.memory_dir) / "memory_declined.json"

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

        # Scheduler (A2, ADR-039): meldet faellige Eintraege proaktiv ueber
        # einen injizierten Notifier (main() verdrahtet channel.push). Ohne
        # Notifier laeuft KEIN Scheduler - nichts feuert ins Leere.
        self._notifier: Optional[Callable[[str], None]] = None
        self._scheduler_thread: Optional[threading.Thread] = None
        self._scheduler_stop = threading.Event()

        # Live-Ablauf-Timeline (UI-Zielbild 2026-07-10): optionaler Listener
        # (Verdrahtungsschicht -> browser.publish). Events tragen NUR
        # Intents/Status/Dauern - nie Nachrichteninhalte. Beiwerk wie die
        # Zuruf-Mitschrift: ein kaputter Listener stoert nie die Verarbeitung.
        # job = fortlaufende Nummer je Anfrage: die UI ordnet damit spaete
        # Events (z. B. Delegations-Abschluss nach Minuten) der richtigen
        # Schritt-Zeile zu, auch wenn dazwischen neue Anfragen liefen.
        self.timeline_listener: Optional[Callable[[dict], None]] = None
        self._timeline_job = 0

        # Durchsicht (ADR-056 Scheibe 1): die Schritt-Ereignisse des Agenten
        # ({kind,label,detail}) wandern live ins UI. Publisher wird in der
        # Verdrahtungsschicht gesetzt (main -> browser.publish("agent", ...));
        # der Sink ist an den Delegate-Command gegeben (spaete Bindung, damit
        # er auch gesetzt werden kann, nachdem der Browser existiert).
        self.agent_event_publisher: Optional[Callable[[dict], None]] = None

    def cancel_delegation(self) -> bool:
        """Stopp-Knopf (ADR-056 Scheibe 2): bricht eine laufende Delegation
        ab, indem der bestehende Kill-Switch gesetzt wird - der Agent-
        Subprozess wird beim naechsten Poll-Tick hart beendet
        (core/agent_backend). Liefert True, wenn es etwas zu stoppen gab.
        Fail-safe: nie werfend."""
        with self._state_lock:
            active = self._delegation_active
        cancel = self._delegation_cancel
        if active and cancel is not None:
            cancel.set()
            logger.info("Delegation per Stopp-Knopf abgebrochen.")
            return True
        return False

    def redirect_delegation(self, text: str) -> bool:
        """Umlenken mitten im Lauf (ADR-056 Scheibe 3): legt eine Kurskorrektur
        ('mach's anders: ...') in den Draht, den das laufende Backend dem
        Agenten ueber stdin unterschiebt. Nur wirksam, WENN gerade eine
        Delegation laeuft (sonst wuerde die Nachricht in einen kuenftigen Lauf
        einsickern) - dann fail-safe abgelehnt. Liefert True, wenn zugestellt."""
        text = (text or "").strip()
        if not text:
            return False
        with self._state_lock:
            active = self._delegation_active
        if not active:
            return False
        self._redirect_channel.send(text)
        logger.info("Kurskorrektur an laufende Delegation zugestellt (%d Zeichen).", len(text))
        return True

    def dismiss_proposal(self, filename: str) -> bool:
        """Verwirft einen Eigenvorschlag (UI-✕, PO-Reibung 2026-07-11): setzt
        den Status im Artefakt auf 'verworfen', damit die Karte verschwindet.
        Fail-safe: nie werfend."""
        try:
            from core.dashboard_data import dismiss_proposal as _dismiss

            return bool(_dismiss(self._memory_dir, filename))
        except Exception:  # noqa: BLE001 - stille UI-Aktion, nie den Prozess gefaehrden
            logger.exception("Vorschlag verwerfen fehlgeschlagen.")
            return False

    def _agent_event_sink(self, event: dict) -> None:
        """Nimmt ein Agenten-Schritt-Ereignis und reicht es an den Publisher
        weiter (falls gesetzt). Fail-safe: die Durchsicht ist Beiwerk - ein
        Fehler hier darf den Agentenlauf nie stoeren."""
        publisher = self.agent_event_publisher
        if publisher is None:
            return
        try:
            publisher(event)
        except Exception:  # noqa: BLE001 - Beiwerk, nie den Lauf gefaehrden
            logger.debug("Agenten-Ereignis-Publisher warf.", exc_info=True)

    def start(self) -> None:
        """Startet den Worker-Thread. Nicht blockierend - Kanäle laufen
        unabhängig davon weiter."""
        self._worker = threading.Thread(
            target=self._run_worker, name="jarvis-runtime-worker", daemon=False
        )
        self._worker.start()
        logger.info("Jarvis-Runtime gestartet (Worker-Thread aktiv).")

    def set_notifier(self, notifier: Callable[[str], None]) -> None:
        """Injiziert den Push-Kanal fuer proaktive Meldungen (A2) - main()
        verdrahtet hier TelegramChannel.push. Die Runtime kennt Telegram
        nicht (gleiche Entkopplung wie beim Agenten-Backend, ADR-027/036)."""
        self._notifier = notifier

    def start_scheduler(self) -> None:
        """Startet den Scheduler-Thread (A2, ADR-039 + Impuls-Kreislauf
        ADR-054). Er laeuft, sobald es ETWAS zu tun gibt: einen Notifier
        (Erinnerungs-Push) ODER die Impuls-Engine. Governance-Einordnung:
        der Erinnerungs-Push erfuellt einen EXPLIZITEN frueheren Auftrag
        ('erinnere mich...'); ein Impuls legt nur eine stille Karte, fuehrt
        nie etwas aus (Handbook 4.2 gewahrt, Vorschlag statt Aktion)."""
        if self._notifier is None and self._impulse_engine is None:
            logger.info("Weder Notifier noch Impuls-Engine - Scheduler bleibt aus.")
            return
        self._scheduler_thread = threading.Thread(
            target=self._run_scheduler, name="jarvis-scheduler", daemon=False
        )
        self._scheduler_thread.start()
        logger.info(
            "Scheduler gestartet (Poll alle %.0fs%s).",
            _SCHEDULER_POLL_SECONDS,
            ", Impuls-Kreislauf aktiv" if self._impulse_engine is not None else "",
        )

    def _run_scheduler(self) -> None:
        """Poll-Schleife: prueft faellige, ungemeldete Eintraege und pusht sie.
        stop_event.wait() dient zugleich als Sleep und als promptes Stop-Signal.
        Markiert VOR dem Push (at-most-once, ADR-039): lieber geht im seltenen
        Sendefehler-Fall eine Erinnerung verloren (steht im Log), als dass eine
        Fehlschleife den Nutzer mit Wiederholungen flutet."""
        while not self._scheduler_stop.wait(timeout=_SCHEDULER_POLL_SECONDS):
            try:
                if self._notifier is not None:
                    for entry in self._entry_store.due_unnotified():
                        if entry.repeat:
                            # ADR-052: VOR dem Push aufs naechste Vorkommen
                            # vorruecken (at-most-once pro Vorkommen; das
                            # entry-Objekt behaelt den ALTEN Zeitpunkt fuer die
                            # ehrliche "war faellig"-Nachricht).
                            self._entry_store.reschedule_repeating(entry.id)
                        else:
                            self._entry_store.mark_notified(entry.id)
                        message = _format_due_message(entry)
                        logger.info("Erinnerung faellig - pushe: %s", entry.text)
                        try:
                            self._notifier(message)
                        except Exception:
                            logger.exception("Erinnerungs-Push fehlgeschlagen: %r", entry.text)
            except Exception:
                # Die Schleife darf nie sterben - naechster Tick versucht es neu.
                logger.exception("Scheduler-Tick fehlgeschlagen.")
            # Impuls-Kreislauf (ADR-054): eigener, langsamer Takt auf demselben
            # Thread - deterministische Pruefer legen stille Karten ab.
            self._maybe_run_impulses()

    def _maybe_run_impulses(self) -> None:
        """Fuehrt die Impuls-Engine hoechstens alle _IMPULSE_INTERVAL_SECONDS
        aus (throttle auf dem Scheduler-Thread). Fail-safe - ein Fehler hier
        darf die Erinnerungs-Pruefung nie beeintraechtigen."""
        if self._impulse_engine is None:
            return
        now = time.monotonic()
        if now - self._last_impulse_monotonic < _IMPULSE_INTERVAL_SECONDS:
            return
        self._last_impulse_monotonic = now
        try:
            self._impulse_engine.run()
        except Exception:  # noqa: BLE001 - der Kreislauf stoert nie den Scheduler
            logger.exception("Impuls-Kreislauf-Tick fehlgeschlagen.")

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

    def _request_restart(self) -> bool:
        """Hook fuer den restart_runtime-Befehl: startet den abgekoppelten
        Nachfolger-Prozess und legt DANACH das Stop-Sentinel in die Queue
        (gleiche Deadlock-Vermeidung wie _request_shutdown - kein join auf
        dem eigenen Worker-Thread). Schlaegt der Prozess-Start fehl, wird
        NICHT heruntergefahren - lieber im Dienst bleiben als tot; der
        Befehl meldet das ehrlich (False)."""
        if not self._spawn_successor():
            return False
        # Nachtplan Scheibe 6: das Dashboard zieht beim Neustart mit um -
        # fail-safe (injizierbar fuer Tests, wie _spawn_successor).
        try:
            self._restart_dashboard()
        except Exception:  # noqa: BLE001 - Dashboard ist Beiwerk
            logger.warning("Dashboard-Abloesung beim Neustart fehlgeschlagen.", exc_info=True)
        self._queue.put(_STOP)
        return True

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

        # Scheduler (A2) einsammeln: Stop-Event beendet den wait() sofort.
        self._scheduler_stop.set()
        scheduler = self._scheduler_thread
        if scheduler is not None and scheduler.is_alive():
            scheduler.join(timeout=_SCHEDULER_JOIN_TIMEOUT)
            if scheduler.is_alive():
                logger.warning(
                    "Scheduler-Thread nach %.0fs noch aktiv - Shutdown wird fortgesetzt.",
                    _SCHEDULER_JOIN_TIMEOUT,
                )
        logger.info("Jarvis-Runtime gestoppt.")

    def submit(
        self,
        text: str,
        reply_callback: Callable[[str], None],
        plan_filter: Optional[Callable[[list[Plan]], tuple[list[Plan], Optional[str]]]] = None,
        allow_async: bool = False,
        confirmer=None,
        source: str = "",
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
        confirmer (optional, ADR-045): Bestätigungsweg des Kanals für
        Stufe-2/3-Rückfragen (say -> Antwortweg des Chats, listen ->
        ConfirmationGate). Nur pro Nachricht aktiv; ohne confirmer bleibt
        die Runtime-Speech exakt fail-closed wie zuvor.

        source (optional, Nacht-Audit-Fix A 2026-07-11): Kanal-Kennung
        ("telegram"/"browser"/"voice"/"konsole") - bindet das Merk-Angebot
        (ADR-051) an den Kanal, in dem es gestellt wurde. Ein "ja" aus
        einem ANDEREN Kanal beantwortet nie ein fremdes Angebot.

        Ohne die neuen Argumente (Default) verhaelt sich submit() exakt wie
        in Runtime v1/v2."""
        self._queue.put((text, reply_callback, plan_filter, allow_async, confirmer, source))

    def _run_worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                self._queue.task_done()
                break
            text, reply_callback, plan_filter, allow_async, confirmer, source = item
            try:
                self._process(text, reply_callback, plan_filter, allow_async, confirmer, source)
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
        confirmer=None,
        source: str = "",
    ) -> None:
        # Bestätigungsweg (ADR-045) NUR für diese Nachricht aktivieren - der
        # Worker ist seriell, das finally räumt garantiert ab (kein Leck in
        # die nächste Nachricht eines anderen Kanals).
        self._speech.confirmer = confirmer
        try:
            self._process_inner(text, reply_callback, plan_filter, allow_async, source)
        finally:
            self._speech.confirmer = None

    def _emit_timeline(self, **event) -> None:
        """Live-Ablauf-Event ans UI. Nie fatal, nie Inhalte (nur Intents,
        Status, Dauern, Laengen)."""
        listener = self.timeline_listener
        if listener is None:
            return
        try:
            listener(event)
        except Exception:  # noqa: BLE001 - Timeline ist Beiwerk
            logger.debug("Timeline-Listener fehlgeschlagen.", exc_info=True)

    def _process_inner(
        self,
        text: str,
        reply_callback: Callable[[str], None],
        plan_filter: Optional[Callable[[list[Plan]], tuple[list[Plan], Optional[str]]]] = None,
        allow_async: bool = False,
        source: str = "",
    ) -> None:
        started = time.monotonic()
        # Merk-Angebot (ADR-051) konsumieren, BEVOR der Planner laeuft: ein
        # schwebendes Angebot gehoert zur letzten Antwort, nicht zur neuen
        # Anfrage. "ja"/"nein" beantworten es; alles andere laesst es still
        # verfallen und wird normal verarbeitet. KANAL-BINDUNG (Nacht-Audit-
        # Fix A): nur der Kanal, dem das Angebot gestellt wurde, kann es
        # beantworten - eine Nachricht aus einem anderen Kanal laesst es
        # verfallen und wird IMMER normal verarbeitet (nie verschluckt).
        pending = self._memory_offer
        if pending is not None:
            self._memory_offer = None
            offer_source, offer = pending
            answer = text.strip().lower().rstrip(".!,")
            if source != offer_source:
                answer = ""  # fremder Kanal: Angebot verfaellt, Nachricht laeuft normal
            if answer in _OFFER_YES:
                result = dispatch(Plan(intent="remember_fact", target=offer,
                                       parameters={"category": "gewohnheit"}))
                self.memory.append_history(Message(role="user", content=text))
                self.memory.append_history(Message(role="assistant", content=result.message))
                self._safe_reply(reply_callback, result.message, text)
                return
            if answer in _OFFER_NO:
                self._decline_memory_offer(offer)
                reply = "Verstanden, Sir — ich schlage das nicht wieder vor."
                self.memory.append_history(Message(role="user", content=text))
                self.memory.append_history(Message(role="assistant", content=reply))
                self._safe_reply(reply_callback, reply, text)
                return

        # Worker ist seriell - der Zaehler braucht kein Lock.
        self._timeline_job += 1
        job = self._timeline_job
        history = self.memory.get_history(limit=20)
        steps = self.planner.plan(text, history)
        # Gewohnheits-Zaehlung (ADR-053): NUR der Intent-Name faellt in ein
        # (Wochentag, Stunde)-Fach - nie Inhalte. record() ist fail-safe.
        for step in steps:
            self.habits.record(step.intent)
        self._emit_timeline(
            stage="plan",
            job=job,
            # Ziel mit anzeigen ("delegate_work (jkc)") - der PO-Befund
            # 2026-07-10 "man sieht nicht viel" UND das Doppel-Schritt-
            # Routing wurden erst durch die Timeline sichtbar.
            intents=[f"{s.intent} ({s.target})" if s.target else s.intent for s in steps],
            confidence=round(steps[0].confidence, 2) if steps else None,
            seconds=round(time.monotonic() - started, 1),
        )

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
                # Sicherheits-Befund 2026-07-10: der Async-Dispatch umging
                # requires_confirmation (run_async lief am Executor vorbei) -
                # delegate_work (Stufe 2) startete ohne Rueckfrage; nur der
                # Sauberer-Baum-Waechter fing es ab. Jetzt: dieselbe
                # Bestaetigung wie im Executor, VOR dem Dispatch, ueber den
                # Confirmer-Weg des Kanals (ADR-045).
                if getattr(command, "requires_confirmation", False) and not steps[
                    0
                ].parameters.get("confirmed"):
                    if not request_confirmation(self._speech, command, steps[0]):
                        self._safe_reply(
                            reply_callback, "Abgebrochen - keine Bestätigung erhalten.", text
                        )
                        return
                    steps[0].parameters["confirmed"] = True
                self._emit_timeline(
                    stage="delegation", job=job, index=0,
                    intent=steps[0].intent, target=(steps[0].target or ""),
                )
                self._dispatch_delegation(text, steps[0], command, reply_callback, job=job)
                return

        long_term_summary = self.long_term.summary_text()

        # Live-Fortschritt (PO-Befund 2026-07-10 "man sieht nicht, dass er
        # arbeitet"): der Executor meldet jeden Schritt bei Beginn UND bei
        # Abschluss - vorher kamen die Haken erst nach ALLEN Schritten.
        def _on_step(phase, index, step, result=None):
            if phase == "start":
                self._emit_timeline(
                    stage="schritt_start", job=job, index=index,
                    intent=step.intent, target=(step.target or ""),
                )
            else:
                self._emit_timeline(
                    stage="schritt", job=job, index=index,
                    intent=step.intent, target=(step.target or ""),
                    ok=bool(result.ok) if result is not None else False,
                )

        report = self.executor.run(steps, history, long_term_summary, on_step=_on_step)
        response_text = "\n".join(report.summary_lines()) or "Alles klar."

        # Merk-Angebot (ADR-051) anbieten: nur wenn eingeschaltet, der Fakt
        # weder bekannt noch abgelehnt ist - und IMMER als Frage, nie als Tat.
        if self._memory_offers_enabled:
            suggestion = next(
                (s.memory_suggestion for s in steps if getattr(s, "memory_suggestion", "")), ""
            )
            if suggestion and not self._memory_suggestion_known(suggestion):
                response_text += f"\n\nSoll ich mir dauerhaft merken: «{suggestion}»? (ja/nein)"
                self._memory_offer = (source, suggestion)  # kanalgebunden (Fix A)

        self.memory.append_history(Message(role="user", content=text))
        self.memory.append_history(Message(role="assistant", content=response_text))
        self._emit_timeline(
            stage="antwort", job=job, chars=len(response_text),
            seconds=round(time.monotonic() - started, 1),
        )
        self._safe_reply(reply_callback, response_text, text)

    def _memory_suggestion_known(self, suggestion: str) -> bool:
        """Nerv-Schutz (ADR-051): kein Angebot, wenn der Fakt schon im
        Langzeitgedaechtnis steht (Teilstring in beide Richtungen, v1-
        Heuristik) oder frueher abgelehnt wurde (Nein-Liste, exakt).
        redact() vorab (Nacht-Audit-Fix C): die Nein-Liste speichert
        redigiert - der Vergleich muss dieselbe Form nutzen."""
        needle = redact(suggestion).strip().lower()
        if not needle:
            return True
        for fact in self.long_term.all_facts():
            existing = fact.text.strip().lower()
            if existing and (needle in existing or existing in needle):
                return True
        return needle in (d.strip().lower() for d in self._declined_offers())

    def _declined_offers(self) -> list[str]:
        data = read_json(self._declined_offers_path, [])
        return [str(x) for x in data] if isinstance(data, list) else []

    def _decline_memory_offer(self, offer: str) -> None:
        # Auto-Redaction (ADR-040, Nacht-Audit-Fix C): auch die Nein-Liste
        # ist ein persistenter Store - Secrets nie im Klartext auf Platte.
        clean = redact(offer)
        declined = self._declined_offers()
        if clean not in declined:
            declined.append(clean)
            write_json_atomic(self._declined_offers_path, declined)
        logger.info("Merk-Angebot abgelehnt (Nein-Liste): %s", clean)

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
        self, text: str, step: Plan, command, reply_callback: Callable[[str], None],
        job: int = 0,
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
                "Es läuft bereits eine Analyse, Sir - eins nach dem anderen; ich melde mich.",
                text,
            )
            return

        # Generische Quittung: die Runtime kennt den konkreten long_running-
        # Command nicht (ADR-036) - kein hartkodiertes "analysiere '<repo>'".
        self._safe_reply(
            reply_callback,
            "Ich kümmere mich darum, Sir - Bericht folgt, sobald das Ergebnis vorliegt.",
            text,
        )
        cancel_event = threading.Event()
        self._delegation_cancel = cancel_event
        thread = threading.Thread(
            target=self._run_delegation,
            args=(text, step, command, reply_callback, cancel_event, job),
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
        job: int = 0,
    ) -> None:
        """Laeuft im Hintergrund-Thread: fuehrt die Analyse cancelbar aus,
        schreibt das Ergebnis (user + assistant) ins Gedaechtnis und pusht die
        Antwort. Das Busy-Flag wird IMMER im finally freigegeben - auch bei
        einer Exception im Hintergrund -, damit der Slot nie dauerhaft belegt
        bleibt."""
        try:
            result = command.run_async(step, cancel_event)
            # Abschluss-Haken in der Timeline - dank job-Nummer landet er an
            # der richtigen Zeile, auch wenn dazwischen neue Anfragen liefen.
            self._emit_timeline(
                stage="schritt", job=job, index=0, intent=step.intent,
                target=(step.target or ""), ok=bool(result.ok),
            )
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

        self.runtime.submit(user_input, reply_callback, source="konsole")
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


def _spawn_successor_process() -> bool:
    """Startet den Nachfolger-Prozess fuer restart_runtime (Welle 3.4):
    gleicher Interpreter (pythonw bleibt pythonw), gleicher Entry-Point,
    vollstaendig vom aktuellen Prozess abgekoppelt. Das Env-Flag laesst den
    Nachfolger auf die Lock-Freigabe warten (Staffelstab, ADR-026 bleibt)."""
    import subprocess

    entry_point = os.path.abspath(__file__)
    env = {**os.environ, WAIT_FOR_LOCK_ENV: str(int(_RESTART_WAIT_SECONDS))}
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            [sys.executable, entry_point],
            env=env,
            creationflags=flags,
            close_fds=True,
            cwd=os.path.dirname(entry_point),
        )
        logger.info("Nachfolger-Prozess gestartet (%s) - fahre herunter.", sys.executable)
        return True
    except Exception:  # noqa: BLE001 - lieber weiterlaufen als tot
        logger.exception("Nachfolger-Prozess konnte nicht gestartet werden.")
        return False


def _restart_dashboard_process() -> None:
    """Loest beim Runtime-Neustart auch das Dashboard ab (Nachtplan
    Scheibe 6, von Jarvis' Eigenvorschlag 20260711-005357 selbst als
    naechster Schritt gestanzt): alten dashboard.py-Prozess beenden, neuen
    abgekoppelt starten - automatisiert die dokumentierte manuelle Routine.
    Fail-safe in JEDEM Teilschritt: der Jarvis-Neustart hat Vorrang, ein
    Dashboard-Fehler wird nur geloggt (lieber altes Gesicht als kein
    Neustart)."""
    import subprocess

    try:
        import psutil

        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmdline = " ".join(proc.info.get("cmdline") or [])
                if "dashboard.py" in cmdline:
                    proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:  # noqa: BLE001 - Abloesung ist Beiwerk
        logger.warning("Dashboard-Abloesung: alte Prozesse nicht ermittelbar.", exc_info=True)
    try:
        entry_point = os.path.abspath(__file__)
        dashboard_script = os.path.join(os.path.dirname(entry_point), "dashboard.py")
        subprocess.Popen(
            [sys.executable, dashboard_script, "--no-browser"],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
            cwd=os.path.dirname(entry_point),
        )
        logger.info("Dashboard-Prozess beim Neustart mit abgeloest.")
    except Exception:  # noqa: BLE001
        logger.warning("Dashboard-Neustart fehlgeschlagen - Runtime-Neustart laeuft trotzdem.", exc_info=True)


def _lock_wait_seconds() -> float:
    """Liest das Neustart-Warte-Flag (gesetzt nur vom Vorgaenger-Prozess).
    Ungesetzt/unlesbar -> 0.0 = heutiges Sofort-Abbruch-Verhalten."""
    raw = os.environ.get(WAIT_FOR_LOCK_ENV, "")
    try:
        return max(float(raw), 0.0) if raw else 0.0
    except ValueError:
        return 0.0


def _fanout_notifier(targets: list) -> Callable[[str], None]:
    """Erinnerungs-Push an ALLE push-faehigen Kanaele (Live-Befund
    2026-07-10: der Push kam nur in Telegram an, das UI-Gesicht blieb
    stumm). Ein kaputter Kanal darf die anderen nie aufhalten."""

    def notify(text: str) -> None:
        for target in targets:
            try:
                target(text)
            except Exception:  # noqa: BLE001
                logger.exception("Erinnerungs-Push an einen Kanal fehlgeschlagen.")

    return notify


def _build_transcriber(config: Config):
    """Baut den Whisper-Transcriber (ADR-038) einmal - genutzt vom Telegram-
    Voice-Handler UND vom Push-to-talk-Kanal (ADR-041). Ohne OpenAI-Key oder
    bei Fehler: None (beide Sprach-Eingaenge bleiben dann aus, Text laeuft)."""
    if not config.openai_api_key:
        return None
    try:
        from core.transcribe import OpenAITranscriber

        return OpenAITranscriber(config.openai_api_key, config.transcription_model)
    except Exception:  # noqa: BLE001
        logger.warning("Transcriber nicht verfuegbar - Sprach-Eingabe deaktiviert.", exc_info=True)
        return None


# Kuerzeste Bestaetigungs-Variante ("Sir?") dauert gesprochen ~0,7 s - alles
# unter einer halben Sekunde ist ein Synthese-Stumpf, keine Ansprache.
_MIN_ACK_SECONDS = 0.5


def _wav_seconds(data: bytes) -> float:
    """Spieldauer eines WAV im Speicher - 0.0 bei kaputten/fremden Daten.
    Ersetzt die zu lasche Byte-Pruefung der Wake-Bestaetigungen (Live-Befund
    2026-07-10: 15-kB-Stumpf = 0,3 s "Stille" passierte RIFF+1000-Bytes)."""
    import io
    import wave

    try:
        with wave.open(io.BytesIO(data)) as w:
            rate = w.getframerate()
            if rate <= 0:
                return 0.0
            return w.getnframes() / float(rate)
    except Exception:  # noqa: BLE001 - kaputt ist kaputt, egal warum
        return 0.0


def _start_hotkey_channel(runtime: JarvisRuntime, config: Config, transcriber):
    """Startet den Push-to-talk-Kanal (ADR-041), wenn Config, Transcriber,
    Pakete und Mikrofon es hergeben - sonst None (alles andere unveraendert)."""
    if not getattr(config, "ptt_enabled", True):
        logger.info("Push-to-talk per Config deaktiviert.")
        return None
    if transcriber is None:
        logger.info("Push-to-talk aus: kein Transcriber (OpenAI-Key fehlt?).")
        return None

    from hotkey_channel import HotkeyChannel, make_speakable

    speech = SpeechEngine(config)

    def speak(text: str) -> None:
        # Gesprochene Antwort darf nie den Aufrufer (Worker/PTT-Thread)
        # mitreissen - Fehler landen im Log, die Arbeit geht weiter.
        # make_speakable: URLs/Quellen-Bloecke werden nicht vorgelesen,
        # Laengen-Deckel gegen Monologe (Text-Kanaele bleiben vollstaendig).
        try:
            speech.say(make_speakable(text))
        except Exception:  # noqa: BLE001
            logger.exception("Sprachausgabe fehlgeschlagen.")

    # Gesprochene Wake-Bestaetigungen einmal synthetisieren und cachen -
    # zur Laufzeit piep-schnell aus dem Speicher (PO-Wunsch: kein Piepton,
    # sondern Butler). Mehrere Varianten per "|" getrennt (Lebendigkeit,
    # PO-Befund 2026-07-10) - pro Zuruf wird zufaellig gewaehlt.
    # Scheitert jede Synthese: Piepton-Fallback.
    wake_acks: list[bytes] = []
    wake_enabled = getattr(config, "wake_word_enabled", False)
    ack_text = getattr(config, "wake_acknowledgement", "")
    if wake_enabled and ack_text and speech.backend is not None:
        import tempfile
        from pathlib import Path

        for variant in [v.strip() for v in ack_text.split("|") if v.strip()]:
            # Zwei Versuche je Variante (Live-Befund 2026-07-10, 2. Runde:
            # OpenAI lieferte einen 0,3-s-Synthese-Stumpf; der passierte die
            # alte Byte-Pruefung und war dann die GANZE Session stumm).
            for attempt in (1, 2):
                try:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                        ack_path = tmp.name
                    speech.backend.synthesize_to_file(variant, ack_path)
                    data = Path(ack_path).read_bytes()
                    Path(ack_path).unlink(missing_ok=True)
                except Exception:  # noqa: BLE001 - Piepton bleibt der Rueckfall
                    logger.warning(
                        'Wake-Bestaetigung "%s" nicht synthetisierbar (Versuch %d).',
                        variant, attempt, exc_info=True,
                    )
                    continue
                seconds = _wav_seconds(data)
                if seconds >= _MIN_ACK_SECONDS:
                    wake_acks.append(data)
                    break
                logger.warning(
                    'Wake-Bestaetigung "%s" unbrauchbar (%.2fs Audio, Versuch %d) - '
                    "abgerissene Synthese wird nicht gecacht.",
                    variant, seconds, attempt,
                )
        if wake_acks:
            logger.info("Wake-Bestaetigungen gecacht: %d Variante(n).", len(wake_acks))

    channel = HotkeyChannel(
        runtime,
        transcriber,
        speak,
        wake_word=wake_enabled,
        wake_acks=wake_acks or None,
    )
    return channel if channel.start() else None


def _start_telegram_channel(runtime: JarvisRuntime, config: Config, transcriber=None):
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

    # Sprach-Eingabe (ADR-038): Transcriber kommt seit ADR-041 aus main()
    # (_build_transcriber) - Telegram-Voice und Push-to-talk teilen ihn.
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
        # Neustart-Staffelstab (restart_runtime): nur der vom Vorgaenger
        # gestartete Nachfolger wartet auf die Lock-Freigabe; ein normaler
        # (Doppel-)Start bricht unveraendert sofort ab.
        lock.acquire(retry_seconds=_lock_wait_seconds())
    except InstanceAlreadyRunningError as e:
        logger.error("Start abgebrochen: %s", e)
        if sys.stdout is not None:
            print(f"Jarvis-Runtime konnte nicht gestartet werden: {e}")
        return
    # Flag nicht weitervererben: kuenftige eigene Nachfolger bekommen es vom
    # Neustart-Spawner explizit neu gesetzt.
    os.environ.pop(WAIT_FOR_LOCK_ENV, None)

    try:
        runtime = JarvisRuntime(config)
        runtime.start()

        transcriber = _build_transcriber(config)
        telegram = _start_telegram_channel(runtime, config, transcriber)

        # Push-to-talk (ADR-041): Hotkey -> Mikro -> Whisper -> gesprochene
        # Antwort. Optional; ohne Pakete/Mikro/Key laeuft alles wie bisher.
        hotkey = _start_hotkey_channel(runtime, config, transcriber)

        # Browser-Kanal (ADR-047): lokale Runtime-API fuer das Jarvis-UI.
        # Default aus; beim PO per ui_enabled aktiviert.
        browser = None
        if getattr(config, "ui_enabled", False):
            from browser_channel import BrowserChannel

            browser = BrowserChannel(runtime, port=config.ui_port)
            if not browser.start():
                browser = None

        # Zuruf-Mitschrift ins UI (PO-Wunsch 10.07.2026): gesprochene
        # Gespraeche (Hey Jarvis / Hotkey) erscheinen im Browser-Gesicht.
        if browser is not None and hotkey is not None:
            def _voice_to_ui(role: str, text: str) -> None:
                browser.publish("voice" if role == "user" else "reply", text=text)

            hotkey.transcript_listener = _voice_to_ui
            # Orb-Zustaende (hoert/arbeitet/spricht/bereit) in den Event-Strom.
            hotkey.state_listener = lambda value: browser.publish("state", value=value)
        # Live-Ablauf-Timeline (UI-Zielbild 2026-07-10): Pipeline-Stationen
        # (Plan/Schritte/Delegation/Antwort) als Events ins Gesicht - jede
        # Zeile echt, keine Inhalte (nur Intents/Status/Dauern).
        if browser is not None:
            runtime.timeline_listener = lambda event: browser.publish("timeline", **event)
            # Durchsicht (ADR-056): Agenten-Schritte live ins Gesicht.
            runtime.agent_event_publisher = lambda ev: browser.publish("agent", **ev)

        # Erinnerungs-Scheduler (A2, ADR-039): pusht an ALLE push-faehigen
        # Kanaele - Telegram UND das UI-Gesicht (Live-Befund 2026-07-10).
        # Verdrahtung hier statt in der Runtime - sie kennt die Kanaele nicht.
        push_targets = []
        if telegram is not None:
            push_targets.append(telegram[0].push)
        if browser is not None:
            push_targets.append(lambda text: browser.publish("reply", text=text))
        if push_targets:
            runtime.set_notifier(_fanout_notifier(push_targets))
        else:
            logger.info("Kein push-faehiger Kanal - Erinnerungen werden nicht gepusht.")
        # Scheduler starten, sobald es etwas zu tun gibt (Push ODER Impulse,
        # ADR-054): start_scheduler entscheidet selbst, ob ein Thread noetig ist.
        runtime.start_scheduler()

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
            if browser is not None:
                browser.stop()
            if hotkey is not None:
                hotkey.stop()
            if telegram is not None:
                telegram_channel_obj, telegram_thread = telegram
                telegram_channel_obj.stop()
                telegram_thread.join(timeout=5.0)
            runtime.stop()
    finally:
        lock.release()


if __name__ == "__main__":
    main()
