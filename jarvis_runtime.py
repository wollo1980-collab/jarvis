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
from collections import deque
import sys
import threading
import time
from datetime import date, datetime, timedelta
from typing import Callable, Optional

import commands.delegate as delegate_commands
import commands.briefing as briefing_commands
import commands.entries as entries_commands
import commands.ideas as ideas_commands
import commands.people as people_commands
import commands.selfreview as selfreview_commands
import commands.skills as skills_commands
import commands.meeting as meeting_commands
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
import commands.agent_control as agent_control_commands
import commands.help as help_commands
import commands.restart as restart_commands
import commands.shutdown as shutdown_commands
import commands.weather as weather_commands
import commands.spotify as spotify_commands
import commands.calendar as calendar_commands
import commands.tasks as tasks_commands
import commands.web as web_commands
from pathlib import Path

from commands import REGISTRY, dispatch
from core.agent_backend import ClaudeCodeBackend, RedirectChannel
from core.ai import AIEngine
from core.config import BASE_DIR, Config
from core.fileio import read_json, write_json_atomic
from core.hook_gate import HookMailbox, classify_command, write_hook_settings
from core.models import Message, Plan
from core.redaction import redact
from core.planner import Planner
from core.proactive import notable_event, plan_preparation
from core.response_composer import compose_response
from core.single_instance import InstanceAlreadyRunningError, SingleInstanceLock
from core.speech import SpeechEngine
from executor.executor import ExecutionReport, Executor, confirmation_required, request_confirmation
from memory.entries import Entry, format_when
from memory.episodic import EpisodicMemory
from memory.habits import HabitStats
from memory.reflection import ReflectionJournal, reflect, suggestion_from_reflection
from memory.self_review import SelfReviewJournal, self_review
from memory.long_term import LongTermMemory
from memory.people import PeopleStore
from memory.session_summary import SessionSummary
from memory.semantic import SemanticIndex
from memory.store import JsonMemoryStore
from core.embeddings import embed_texts
from core.tool_index import ToolIndex
from core.build_suggestion import frictions_text, suggest_build, usage_text

logger = logging.getLogger("jarvis.runtime")

# Antworten, die ein schwebendes Merk-Angebot (ADR-051) annehmen/ablehnen -
# bewusst eng (nur eindeutige Kurzantworten); alles andere laesst das
# Angebot still verfallen und wird als normale Nachricht verarbeitet.
_OFFER_YES = {"ja", "j", "yes", "gerne", "ja bitte", "merk dir das"}
_OFFER_NO = {"nein", "n", "no", "lieber nicht", "nicht merken"}

# Nacktes Zuruecknehmen direkt nach einer umkehrbaren Tat (Live-Befund
# 15.07.: auf «nein» nach einem «Vermerkt, Sir» BEHAUPTETE der Chat eine
# Loeschung, die nie lief). Deterministisch statt klassifiziert (ADR-068:
# die Antwort GARANTIEREN): diese Phrasen loesen das echte Undo-Werkzeug aus.
_UNDO_PHRASES = {"nein", "nee", "ne", "nein danke", "doch nicht", "lieber nicht",
                 "nicht speichern", "das war falsch", "rueckgaengig", "rückgängig",
                 "mach das rueckgaengig", "mach das rückgängig",
                 "nimm das zurueck", "nimm das zurück", "loesch das wieder",
                 "lösch das wieder", "vergiss das wieder"}
_UNDO_WINDOW_SECONDS = 600.0

# Umkehrbare Gedaechtnis-Aktionen: hier gilt "Undo statt Rueckfrage" (ADR-068) -
# bei einer Frage handeln + antworten, weil ein Fehlgriff ein Wort entfernt ist
# (forget bzw. erneutes remember). Riskante/irreversible Aktionen sind NICHT dabei.
_REVERSIBLE_MEMORY_INTENTS = frozenset({"remember_fact", "forget_fact"})

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

# Antwortfenster (Sekunden) fuer eine Erlaubnis-Frage des Bau-Agenten (S4b
# Scheibe 2): knapp unter dem Hook-Timeout (110 s), damit die PO-Antwort den
# wartenden Hook noch erreicht.
_HOOK_ANSWER_SECONDS = 100.0
# Impuls-Kreislauf (ADR-054): eigener, deutlich langsamer Takt auf demselben
# Scheduler-Thread - Unwetter/Gewohnheiten aendern sich in Minuten, nicht
# Sekunden; der gecachte Wetterabruf (30-Min-TTL) wird so nie gehaemmert.
_IMPULSE_INTERVAL_SECONDS = 900.0
# Ab dieser Stunde (lokal) schaut die proaktive Vorbereitung auf den Kalender
# von morgen (ADR-063) - abends ist "morgen" die sinnvolle Vorausschau.
_PROACTIVE_HOUR = 18
# Wie oft der semantische Index neue Erinnerungen einliest (ADR-065 B2) - auf dem
# Scheduler-Thread, gedrosselt (Indizieren ist Kuer, nicht zeitkritisch).
_SEMANTIC_SYNC_INTERVAL_SECONDS = 600.0
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

    @property
    def can_confirm(self) -> bool:
        """Hat dieser Weg einen ECHTEN Bestaetigungsweg? Ohne (PTT/Wake) soll
        der Executor gar nicht erst fragen, sondern dem Nutzer VERSTAENDLICH
        den Weg zeigen (PO-Reibung 13.07.: 'loesch den Termin' per Stimme ->
        kryptisches 'Abgebrochen - keine Bestaetigung erhalten')."""
        return self.confirmer is not None

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
        # Werkzeug-Vorfilter (Plan B): Tool-Index + Selector fuer den denkenden
        # Kern. Nur aktiv, wenn config.tool_prefilter_enabled; sonst reicht der
        # Planner alle Tools durch (Selektor wird nicht aufgerufen). Fail-open.
        _embed_key = getattr(config, "openai_api_key", "") or os.environ.get("OPENAI_API_KEY", "")
        _embed_model = getattr(config, "embedding_model", "") or "text-embedding-3-small"
        self._tool_index = ToolIndex(
            Path(config.memory_dir) / "tool_index.json",
            lambda texts: embed_texts(texts, _embed_key, _embed_model),
        )
        _prefilter_k = int(getattr(config, "tool_prefilter_k", 12) or 12)
        self.planner = Planner(
            self.ai,
            tool_selector=lambda text, schemas: self._tool_index.select(text, schemas, k=_prefilter_k),
        )
        self._speech = _RuntimeSpeech()
        self.executor = Executor(self._speech, self.ai)
        self.memory = JsonMemoryStore(config.memory_dir, config.max_history_entries)
        self._memory_dir = Path(config.memory_dir)  # fuer stille UI-Aktionen (Vorschlag verwerfen)
        self.long_term = LongTermMemory(config.memory_dir)
        # Personen-Gedaechtnis (ADR-066 Stein 1): "wer ist wer". Store geteilt,
        # Befehl remember_person; die Runtime holt pro Anfrage den Personen-Kontext.
        self._people = PeopleStore(config.memory_dir)
        people_commands.configure(self._people)
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
        # similar_fact_fn (Kundenreview 13.07., Duplikate): Sinn-Nachbar-Suche
        # ueber den Semantik-Index. Als Methode uebergeben - sie greift erst
        # bei Aufrufen (nach __init__) auf self._semantic zu.
        memory_commands.configure(config.memory_dir, similar_fact_fn=self._similar_fact)
        # Skill-Bibliothek (Plan A1): geteilte Instanz fuer den list_skills-Befehl
        # UND die Dedup im proaktiven Bau-Vorschlag (nichts erneut vorschlagen,
        # das schon gebaut ist). delegate registriert Gebautes ueber denselben Pfad.
        self._skills = skills_commands.configure(config.memory_dir)
        # Meeting-Prep (Plan C4): der Befehl ruft diese Runtime-Funktion (sie hat
        # Kalender + Personen + Aufgaben).
        meeting_commands.configure(self.prepare_meeting)
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
        ideas_commands.configure(
            self.ai, self.habits, self._entry_store, list_store,
            history_provider=lambda: self.memory.get_history(limit=8),
        )
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
        # Plan F: neue Impulse aktiv an den Besitzer pushen (ueber den Notifier),
        # nicht nur als Dashboard-Karte. Opt-in, fail-safe.
        self._impulse_push_enabled = bool(getattr(config, "impulse_push_enabled", False))
        # Telegram-Ausbau (a), 13.07.: Morgen-Briefing + Meeting-Prep aktiv aufs
        # Handy (ueber den Notifier). Beides opt-in, read-only, fail-safe; Zustand
        # persistiert (kein Doppel-Push nach Neustart).
        self._briefing_push_enabled = bool(getattr(config, "briefing_push_enabled", False))
        self._briefing_push_time = str(getattr(config, "briefing_push_time", "") or "07:30")
        self._briefing_push_state_path = Path(config.memory_dir) / "briefing_push.json"
        self._meeting_prep_push_enabled = bool(getattr(config, "meeting_prep_push_enabled", False))
        self._meeting_prep_lead_minutes = int(
            getattr(config, "meeting_prep_lead_minutes", 30) or 30)
        self._meeting_prep_state_path = Path(config.memory_dir) / "meeting_prep_push.json"
        self._last_meeting_prep_monotonic = 0.0
        monitor_commands.configure(self.ai)
        web_commands.configure(self.ai, timeout_seconds=config.timeout)
        # News-Briefing (ADR-042): RSS-Feeds aus der Config.
        news_commands.configure(config.news_feeds, timeout_seconds=config.timeout)
        # Wetter (ADR-043): Standard-Ort aus der Config.
        weather_commands.configure(config.weather_default_location, timeout_seconds=config.timeout)
        # Spotify (ADR-058): Client aus der Config, fehlende Credentials = aus.
        spotify_commands.configure(config)
        calendar_commands.configure(config)
        # Projektstart (ADR-049): Pfade aus der Config, leer = aus.
        project_commands.configure(config.projects_root, config.framework_repo)
        mail_commands.configure(
            config,
            generate_fn=lambda system, user: self.ai.generate(system, user, model=self._compose_model),
        )
        # Agenten-Delegation (ADR-034): read-only Repo-Analyse. Backend aus der
        # Verdrahtungsschicht injiziert (Fachlogik nennt kein Backend, ADR-036).
        # ai fuer project_continue (Stufe 2): baut den Delegations-Auftrag
        # aus dem Projektstand des Zielrepos.
        # Telegram-Erlaubnis-Haken (S4b Scheibe 2, ADR-071): Mailbox + die
        # --settings-Datei mit dem PreToolUse-Hook einmal beim Start erzeugen.
        # Nur bei Opt-in; ohne Haken bleibt Folgenreiches schlicht verboten
        # (Allowlist fail-closed - der Haken kann nur mit PO-Ja ERWEITERN).
        self._hook_enabled = bool(getattr(config, "agent_permission_hook_enabled", False))
        self._hook_mailbox = HookMailbox(Path(config.memory_dir) / "hook_requests")
        self._permission_offer: Optional[tuple] = None
        self._hook_seen: set = set()
        hook_settings = None
        if self._hook_enabled:
            try:
                hook_settings = write_hook_settings(
                    Path(config.memory_dir) / "hook_settings.json",
                    Path(BASE_DIR) / "scripts" / "agent_permission_hook.py",
                    self._hook_mailbox.dir,
                )
            except Exception:  # noqa: BLE001 - ohne Settings kein Haken (fail-closed)
                logger.exception("Erlaubnis-Haken: Settings-Erzeugung fehlgeschlagen - Haken aus.")
                hook_settings = None
        delegate_commands.configure(config, ClaudeCodeBackend(), ai=self.ai,
                                    event_sink=self._agent_event_sink,
                                    redirect=self._redirect_channel,
                                    hook_settings=hook_settings)
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
        # Agenten-Stopp auf Zuruf (Telegram-Ausbau c1): der Kill-Switch
        # (cancel_delegation, ADR-056 S2) wird als Befehl verfuegbar - damit
        # kann auch das Handy einen laufenden Bau/eine Analyse hart stoppen.
        agent_control_commands.configure(self.cancel_delegation)
        # Entdeckung (Spektakulaer #1): "Was kannst du?" + "Was ist neu?" -
        # whats_new liest das ohnehin anwendersprachliche CHANGELOG.
        help_commands.configure(Path(BASE_DIR) / "docs" / "CHANGELOG.md")
        self._whats_new_hint_enabled = bool(getattr(config, "whats_new_hint_enabled", False))
        self._whats_new_seen_path = Path(config.memory_dir) / "whats_new_seen.json"
        # Neue-Version-Hinweis (Spektakulaer #5-light, Kundenreview: das
        # "starte neu"-Ritual soll der Anwender nicht erraten muessen): der
        # Scheduler prueft gedrosselt den Commit-Stand auf der Platte; weicht
        # er vom Start-Stand ab, sagt Jarvis es EINMAL von selbst.
        self._version_hint_enabled = bool(getattr(config, "version_hint_enabled", False))
        # Voll-Automat Neustart (PO-Entscheidung Nachtmodus 13.07.): neue
        # Version im LEERLAUF selbst uebernehmen - nie waehrend Delegation,
        # offener Rueckfrage oder frischem Gespraech. Die Meldung danach
        # uebernimmt der ✨-Hinweis (whats_new) beim naechsten Kontakt.
        self._auto_restart_enabled = bool(getattr(config, "auto_restart_enabled", False))
        self._auto_restart_attempted_head = ""
        # Gesprochene Erinnerungen (PO-Reibung 13.07. "Mit Sprache"): faellige
        # Erinnerungen zusaetzlich ueber die Lautsprecher sprechen. Opt-in;
        # der Sprech-Weg wird von main() injiziert (set_voice_notifier).
        self._reminder_speech_enabled = bool(getattr(config, "reminder_speech_enabled", False))
        self._voice_notifier: Optional[Callable[[str], None]] = None
        self._startup_git_head = _git_head(BASE_DIR) if self._version_hint_enabled else ""
        self._version_hint_pending = False
        self._version_hint_seen_head = ""
        self._last_version_check_monotonic = 0.0

        # Aktions-Zustand (UX-S4): echter Zustand fuer den Antwort-Kontext -
        # frischer Start, laufender Bau, letzte Aktionen. Gegen erfundene
        # Zusagen ("kein Neustart", obwohl er lief - PO-Befund 13.07.).
        self._started_monotonic = time.monotonic()
        self._recent_actions: deque = deque(maxlen=3)
        # Leerlauf-Erkennung fuer den Neustart-Voll-Automaten: Zeitpunkt der
        # letzten verarbeiteten Nachricht (egal welcher Kanal).
        self._last_message_monotonic = time.monotonic()

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

        # Episodisches Gedaechtnis (Gedaechtnis-Kampagne Stufe 1): opt-in
        # (config.episodic_memory_enabled). Ein einsehbares Tagebuch der
        # Ereignisse als Fundament fuer die spaetere naechtliche Reflexion.
        # None = aus (kein Schreiben), sonst der Store.
        self._episodic: Optional[EpisodicMemory] = (
            EpisodicMemory(config.memory_dir)
            if getattr(config, "episodic_memory_enabled", False)
            else None
        )

        # Naechtliche Reflexion ('dreaming', Stufe 2): opt-in, braucht das
        # episodische Log. Einmal pro Tag ueber den Vortag; das Journal ist
        # einsehbar (memory_dir/reflections/). _last_reflection_date ist
        # In-Memory - die Idempotenz sichert der "Journal-Datei existiert
        # schon?"-Check, damit ein Neustart am selben Tag nicht neu reflektiert.
        self._reflection: Optional[ReflectionJournal] = (
            ReflectionJournal(config.memory_dir)
            if getattr(config, "reflection_enabled", False) and self._episodic is not None
            else None
        )
        self._last_reflection_date: Optional[date] = None
        # Merk-Vorschlag aus der Reflexion (Stein 2b): opt-in, braucht Reflexion
        # + Merk-Angebote. Die naechste Reflexion legt EINE Vermutung als
        # schwebenden Vorschlag ab; das naechste Gespraech bietet sie als
        # ja/nein an (ueber die bestehende Merk-Angebot-Schiene).
        self._reflection_offers_enabled = bool(
            getattr(config, "reflection_offers_enabled", False)
        ) and self._reflection is not None and self._memory_offers_enabled
        self._reflection_suggestion_path = Path(config.memory_dir) / "reflection_suggestion.json"

        # Proaktive Vorbereitung (ADR-063): opt-in. Abends schaut Jarvis auf den
        # Kalender von morgen und legt EINEN Vorschlag ("um 8:00 erinnern?") als
        # schwebendes Angebot ab; das naechste Gespraech bietet ihn EINMAL als
        # ja/nein an ("ja" legt eine Erinnerung an). _last_proactive_date ist
        # In-Memory-Drossel; die Datei (generated_for) sichert die Idempotenz
        # ueber Neustarts UND verhindert erneutes Anbieten nach der Antwort.
        self._proactive_prep_enabled = bool(getattr(config, "proactive_prep_enabled", False))
        self._proactive_offer: Optional[tuple] = None
        self._last_proactive_date: Optional[date] = None
        self._proactive_suggestion_path = Path(config.memory_dir) / "proactive_suggestion.json"

        # Antwort-Composer (ADR-065 Saeule A): im Schatten loggen (A1) und/oder
        # die komponierte Antwort ZEIGEN (A2 - Multi-Step generell + Intent-
        # Whitelist). Opt-in, Default aus, fail-safe.
        self._response_compose_shadow = bool(getattr(config, "response_compose_shadow", False))
        self._response_compose_multistep = bool(getattr(config, "response_compose_multistep", False))
        self._response_compose_intents = frozenset(
            getattr(config, "response_compose_intents", None) or []
        )
        self._compose_model = getattr(config, "compose_model", "") or "gpt-4o-mini"
        # "Antworten + gleich tun" (ADR-068): stellt der Nutzer eine FRAGE und faellt
        # dabei eine UMKEHRBARE Aktion (merken/loeschen), beantwortet Jarvis die Frage
        # ueber den Composer UND fuehrt die Aktion aus (Undo-statt-Rueckfrage) - statt
        # ihn stumm zu handeln. Opt-in, Default aus, fail-safe.
        self._answer_and_act_enabled = bool(getattr(config, "answer_and_act_enabled", False))

        # Sitzungs-Zusammenfassung (ADR-065 B1): rollierende Zusammenfassung des
        # aelteren Verlaufs, damit der Faden in langen Gespraechen nicht reisst.
        # Opt-in, Default aus. Nutzt das guenstige Compose-Modell.
        self._session_summary_enabled = bool(getattr(config, "session_summary_enabled", False))
        self._session_summary = SessionSummary()

        # Semantischer Abruf (ADR-065 B2, Gedaechtnis Stufe 4): relevante
        # Erinnerungen (Fakten/Episoden) werden pro Anfrage in den Kontext geholt.
        # Embedding hinter austauschbarer Schicht (jetzt OpenAI, spaeter lokal).
        # Opt-in, fail-safe. Key wie im Provider (config oder Env).
        self._semantic_enabled = bool(getattr(config, "semantic_recall_enabled", False))
        self._embedding_model = getattr(config, "embedding_model", "") or "text-embedding-3-small"
        self._embedding_api_key = (
            getattr(config, "openai_api_key", "") or os.environ.get("OPENAI_API_KEY", "")
        )
        self._semantic = SemanticIndex(
            Path(config.memory_dir) / "semantic_index.json",
            lambda texts: embed_texts(texts, self._embedding_api_key, self._embedding_model),
        )
        self._last_semantic_sync = 0.0

        # Selbst-Verbesserung (ADR-066 Stein 3): Jarvis bewertet aus dem
        # episodischen Log ehrlich die EIGENE Leistung (Reibungen) und legt eine
        # einsehbare Selbstbewertung ab. Opt-in, braucht das episodische Log.
        self._self_review = SelfReviewJournal(config.memory_dir)
        # on_demand: 'wie schlaegst du dich?' erzeugt bei leerem Journal SOFORT
        # eine Bewertung (statt auf den Scheduler-Lauf zu warten).
        selfreview_commands.configure(self._self_review, on_demand=self.run_self_review)
        self._self_review_enabled = (
            bool(getattr(config, "self_review_enabled", False)) and self._episodic is not None
        )
        self._last_self_review_date: Optional[date] = None

        # Proaktiver Bau-Vorschlag (ADR-067 Stufe 1, Koenigsdisziplin): aus
        # Nutzungsmustern + Reibungen EINE baubare Werkzeug-Idee ableiten und
        # EINMAL vorlegen (mit Ausloese-Satz). Gebaut wird NIE automatisch - der
        # Nutzer sagt selbst "Bau mir X". Opt-in, fail-safe.
        self._build_offers_enabled = bool(getattr(config, "build_offers_enabled", False))
        self._build_suggestion_path = Path(config.memory_dir) / "build_suggestion.json"
        self._last_build_suggestion_date: Optional[date] = None

        # Asynchrone Repo-Analyse (ADR-035): ein von der Runtime besessener
        # Hintergrund-Worker fuer langlaufende (long_running) Commands, damit
        # der serielle Nachrichten-Worker nicht minutenlang blockiert.
        # Nebenlaeufigkeit bewusst = 1 (ADR-035): ein einzelnes Flag unter einem
        # Lock, KEIN Scheduler/keine Warteschlange - deckt "genau eine
        # gleichzeitige Delegation" exakt ab (erweiterbar, falls je noetig).
        # Letzte umkehrbare Einzel-Tat (fuer das nackte «nein» direkt danach,
        # Live-Befund 15.07.) - {undo_intent, handle, exact, ts, source}.
        self._last_undoable: Optional[dict] = None

        self._state_lock = threading.Lock()
        self._delegation_active = False
        self._delegation_thread: Optional[threading.Thread] = None
        self._delegation_cancel: Optional[threading.Event] = None

        # Auftrags-Loop (Phase B.1, ADR-074): gemeinsamer Single-Flight-
        # Koordinator (Nachtrag 4 - die Legacy-Delegation teilt sich DIESE
        # Lease mit dem TaskService; nie zwei externe Ausfuehrungspfade)
        # + EIGENER TaskService. Die Runtime traegt KEINE Auftrags-
        # zustandsmaschine - nur Verdrahtung und Kanal-Uebersetzung (§9).
        from core.execution_lease import ExecutionLease

        self.execution_lease = ExecutionLease()
        self.task_service = self._build_task_service(config)
        tasks_commands.configure(lambda: self.task_service,
                                 str(getattr(config, "task_portfolio_root", "") or ""))

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

    def _build_task_service(self, config):
        """Baut den TaskService (Phase B.1) - IMMER (Hardening H3, §9-
        Migration: er traegt auch den Kompatibilitaetsadapter der Legacy-
        Delegation). Die Portfolio-Capability + der Entscheider kommen nur
        bei konfiguriertem Root dazu. Fail-safe: ein Baufehler laesst
        task_service None - dann greift der alte Thread-Rueckfallpfad."""
        root = str(getattr(config, "task_portfolio_root", "") or "").strip()
        try:
            from core.capability_registry import CapabilityRegistry
            from core.portfolio import (
                PORTFOLIO_VERIFIERS,
                build_portfolio_capability,
                make_report_fn,
            )
            from core.task_planner import OpenAITaskDecisionProvider
            from core.task_runner import TaskRunner
            from core.task_service import TaskService
            from memory.task_store import TaskStore

            registry = CapabilityRegistry()
            decision = None
            report_fn = None
            if root:
                registry.register(build_portfolio_capability(Path(root)))
                # Nachtrag 6: EIGENER Entscheidungsweg direkt auf dem Provider -
                # kein AIEngine.choose_tool, kein Conversation-Systemprompt.
                provider = getattr(self.ai, "provider", None)
                decision = OpenAITaskDecisionProvider(provider) if provider is not None else None
                # Data Plane (handlungsunfaehig): json_mode erzwingt ein JSON-
                # Objekt, max_tokens gibt dem 9-Projekte-Bericht genug Raum.
                report_fn = make_report_fn(
                    lambda system, user: self.ai.generate(system, user,
                                                          json_mode=True, max_tokens=4000))
            runner = TaskRunner(TaskStore(config.memory_dir), registry, decision,
                                report_fn=report_fn, verifiers=PORTFOLIO_VERIFIERS)
            return TaskService(runner.store, runner, self.execution_lease,
                               listener=self._on_task_event)
        except Exception:  # noqa: BLE001 - der Loop ist Zusatz, nie Startblocker
            logger.exception("TaskService konnte nicht gebaut werden - Auftrags-Loop aus.")
            return None

    def _on_task_event(self, kind: str, task) -> None:
        """Uebersetzt TaskService-Ereignisse in Kanalnachrichten (§9): loggen
        immer; nutzerrelevante Endzustaende gehen als Push ueber die
        persistente Outbox (Nachtrag 7: mindestens einmal, dedupliziert)."""
        logger.info("Auftrag %s: %s (%s).", task.task_id[:8], kind, task.status.value)
        if kind in ("completed", "blocked", "cancelled", "failed", "waiting_for_input") \
                and self._notifier is not None and self.task_service is not None:
            try:
                self.task_service.flush_outbox(self._notifier)
            except Exception:  # noqa: BLE001 - Zustellung stoert den Lauf nie
                logger.warning("Task-Outbox-Zustellung fehlgeschlagen.", exc_info=True)

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
        Fehler hier darf den Agentenlauf nie stoeren.

        Bau-Bullauge (Spektakulaer #4): EINE Stelle ergaenzt die deutsche
        Erzaehl-Zeile (event['summary']) - deterministisch, das Roh-Detail
        bleibt am Event; jeder Kanal erbt die Erzaehlung."""
        publisher = self.agent_event_publisher
        if publisher is None:
            return
        try:
            from core.agent_narration import narrate

            enriched = dict(event)
            summary = narrate(event)
            if summary:
                enriched["summary"] = summary
        except Exception:  # noqa: BLE001 - Erzaehlung ist Beiwerk
            enriched = event
        try:
            publisher(enriched)
        except Exception:  # noqa: BLE001 - Beiwerk, nie den Lauf gefaehrden
            logger.debug("Agenten-Ereignis-Publisher warf.", exc_info=True)

    def start(self) -> None:
        """Startet den Worker-Thread. Nicht blockierend - Kanäle laufen
        unabhängig davon weiter."""
        self._worker = threading.Thread(
            target=self._run_worker, name="jarvis-runtime-worker", daemon=False
        )
        self._worker.start()
        # Auftrags-Loop (Phase B.1): Worker starten + Wiederanlauf nach
        # Vertrag §7 (unterbrochene Auftraege werden sicher fortgesetzt).
        if self.task_service is not None:
            self.task_service.start()
            self.task_service.resume_on_start()
        # Gedaechtnis-Aufraeumen (Kundenreview 13.07.: dieselbe Praeferenz
        # dreimal im Profil): einmal je Start, im Hintergrund, fail-open.
        # Sinngleiche Fakten wandern in den Papierkorb - nichts geht verloren.
        if self._semantic_enabled:
            threading.Thread(
                target=self._run_memory_dedupe, name="jarvis-memory-dedupe", daemon=True
            ).start()
        logger.info("Jarvis-Runtime gestartet (Worker-Thread aktiv).")

    def _run_memory_dedupe(self) -> None:
        try:
            moved = self.long_term.dedupe_semantic(
                lambda texts: embed_texts(texts, self._embedding_api_key, self._embedding_model)
            )
            if moved:
                logger.info(
                    "Gedaechtnis-Aufraeumen: %d sinngleiche Fakten in den Papierkorb "
                    "(wiederherstellbar per «stell den Fakt wieder her»).", len(moved),
                )
        except Exception:  # noqa: BLE001 - Aufraeumen stoert den Start nie
            logger.warning("Gedaechtnis-Aufraeumen fehlgeschlagen (ignoriert).", exc_info=True)

    def _similar_fact(self, text: str) -> Optional[str]:
        """Sinngleichen BESTEHENDEN Fakt zu `text` finden (oder None) - fuer
        die Anlege-Dedupe in commands/memory.py. Nutzt den Semantik-Index
        (nur source='fakt') und verifiziert gegen den AKTUELLEN Bestand
        (der Index darf nachhinken). Fail-open: Fehler/aus -> None."""
        if not self._semantic_enabled or not (text or "").strip():
            return None
        try:
            from memory.long_term import DEDUPE_THRESHOLD

            hits = self._semantic.search(text, k=5, min_score=DEDUPE_THRESHOLD)
            current = {" ".join(f.text.lower().split()): f.text for f in self.long_term.all_facts()}
            for hit in hits:
                if hit.get("source") != "fakt":
                    continue
                key = " ".join(str(hit.get("text", "")).lower().split())
                if key in current:
                    return current[key]
        except Exception:  # noqa: BLE001 - Dedupe stoert das Merken nie
            logger.warning("Sinn-Nachbar-Suche fehlgeschlagen (ignoriert).", exc_info=True)
        return None

    def set_notifier(self, notifier: Callable[[str], None]) -> None:
        """Injiziert den Push-Kanal fuer proaktive Meldungen (A2) - main()
        verdrahtet hier TelegramChannel.push. Die Runtime kennt Telegram
        nicht (gleiche Entkopplung wie beim Agenten-Backend, ADR-027/036)."""
        self._notifier = notifier
        # Task-Outbox (Nachtrag 7): unzugestellte Auftrags-Ergebnisse aus
        # frueheren Laeufen JETZT nachliefern (mindestens einmal, dedupliziert).
        if self.task_service is not None:
            try:
                delivered = self.task_service.flush_outbox(notifier)
                if delivered:
                    logger.info("Task-Outbox: %d Ergebnis(se) nachgeliefert.", delivered)
            except Exception:  # noqa: BLE001 - Zustellung stoert den Start nie
                logger.warning("Task-Outbox-Nachlieferung fehlgeschlagen.", exc_info=True)

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
                self._push_due_entries()
            except Exception:
                # Die Schleife darf nie sterben - naechster Tick versucht es neu.
                logger.exception("Scheduler-Tick fehlgeschlagen.")
            # Impuls-Kreislauf (ADR-054): eigener, langsamer Takt auf demselben
            # Thread - deterministische Pruefer legen stille Karten ab.
            self._maybe_run_impulses()
            # Naechtliche Reflexion ('dreaming', Stufe 2): einmal pro Tag ueber
            # den Vortag - eigener, sehr langsamer Takt auf demselben Thread.
            self._maybe_run_reflection()
            # Proaktive Vorbereitung (ADR-063): abends EINMAL auf den Kalender
            # von morgen schauen und einen Erinnerungs-Vorschlag ablegen.
            self._maybe_run_proactive()
            # Semantischer Index (ADR-065 B2): neue Erinnerungen einlesen.
            self._maybe_run_semantic_sync()
            # Selbst-Verbesserung (ADR-066 Stein 3): einmal/Tag die eigene
            # Leistung der letzten Woche bewerten.
            self._maybe_run_self_review()
            # Proaktiver Bau-Vorschlag (ADR-067): alle paar Tage eine baubare
            # Werkzeug-Idee aus den Mustern ableiten.
            self._maybe_run_build_suggestion()
            # Telegram-Ausbau (a): Morgen-Briefing (1x/Tag ab Uhrzeit) und
            # Meeting-Prep (kurz vor dem Termin) aktiv aufs Handy.
            self._maybe_run_briefing_push()
            self._maybe_run_meeting_prep_push()
            # Neue Version auf der Platte? (Spektakulaer #5-light)
            self._maybe_check_new_version()
            # Voll-Automat (PO-Entscheidung Nachtmodus 13.07.): im Leerlauf
            # uebernimmt Jarvis die neue Version selbst.
            self._maybe_auto_restart()

    def _push_due_entries(self) -> None:
        """Faellige, ungemeldete Eintraege pushen - und auf Wunsch SPRECHEN
        (PO-Reibung 13.07.: «erinner mich … Mit Sprache» kam nur als Text).
        Markiert VOR dem Push (at-most-once, ADR-039)."""
        if self._notifier is None:
            return
        for entry in self._entry_store.due_unnotified():
            if entry.repeat:
                # ADR-052: VOR dem Push aufs naechste Vorkommen vorruecken
                # (at-most-once pro Vorkommen; das entry-Objekt behaelt den
                # ALTEN Zeitpunkt fuer die ehrliche "war faellig"-Nachricht).
                self._entry_store.reschedule_repeating(entry.id)
            else:
                self._entry_store.mark_notified(entry.id)
            message = _format_due_message(entry)
            logger.info("Erinnerung faellig - pushe: %s", entry.text)
            try:
                self._notifier(message)
            except Exception:  # noqa: BLE001
                logger.exception("Erinnerungs-Push fehlgeschlagen: %r", entry.text)
            # Gesprochene Erinnerung (Spektakulaer, PO-Reibung 13.07.): faellige
            # Erinnerungen werden zusaetzlich ueber die Lautsprecher gesprochen,
            # wenn eingeschaltet UND eine Stimme verdrahtet ist. Fail-safe.
            if self._reminder_speech_enabled and self._voice_notifier is not None:
                try:
                    self._voice_notifier(f"Eine Erinnerung, Sir: {entry.text}.")
                except Exception:  # noqa: BLE001
                    logger.exception("Gesprochene Erinnerung fehlgeschlagen.")

    def set_voice_notifier(self, voice_notifier: Callable[[str], None]) -> None:
        """Injiziert die Sprachausgabe fuer proaktive Meldungen (gesprochene
        Erinnerungen) - main() verdrahtet hier den speak()-Weg des Sprach-
        Kanals. Gleiche Entkopplung wie set_notifier."""
        self._voice_notifier = voice_notifier

    def _maybe_check_new_version(self) -> None:
        """Gedrosselt (10 min): weicht der Commit-Stand auf der Platte vom
        Start-Stand ab, den Hinweis EINMAL je neuem Stand armieren. Fail-safe."""
        if not self._version_hint_enabled or not self._startup_git_head:
            return
        now = time.monotonic()
        if now - self._last_version_check_monotonic < 600.0:
            return
        self._last_version_check_monotonic = now
        try:
            head = _git_head(BASE_DIR)
            if head and head != self._startup_git_head and head != self._version_hint_seen_head:
                self._version_hint_seen_head = head
                self._version_hint_pending = True
                logger.info("Neue Version erkannt (%s) - Hinweis armiert.", head[:8])
        except Exception:  # noqa: BLE001
            logger.warning("Versions-Check fehlgeschlagen (ignoriert).", exc_info=True)

    # Leerlauf-Regeln fuer den Neustart-Voll-Automaten: so lange muss die
    # letzte Nachricht her sein (kein Gespraech unterbrechen) und so lange
    # muss der eigene Start zurueckliegen (kein Neustart-Pingpong).
    _AUTO_RESTART_IDLE_SECONDS = 15 * 60.0
    _AUTO_RESTART_MIN_UPTIME_SECONDS = 10 * 60.0

    def _maybe_auto_restart(self) -> None:
        """Voll-Automat (PO-Entscheidung Nachtmodus 13.07.): liegt ein neuer
        Stand auf der Platte, uebernimmt Jarvis ihn selbst - aber NUR im
        Leerlauf: keine laufende Delegation, keine Nachricht in der Queue,
        letzte Nachricht >= 15 min her, eigener Start >= 10 min her. Je
        neuem Stand genau EIN Versuch (kein Spawn-Pingpong bei Fehlern).
        Die 'ich habe mich aktualisiert'-Meldung uebernimmt der ✨-Hinweis
        beim naechsten Kontakt; hier wird nur geloggt."""
        if not self._auto_restart_enabled or not self._startup_git_head:
            return
        head = self._version_hint_seen_head
        if not head or head == self._startup_git_head:
            return
        if head == self._auto_restart_attempted_head:
            return
        now = time.monotonic()
        if now - self._started_monotonic < self._AUTO_RESTART_MIN_UPTIME_SECONDS:
            return
        if now - self._last_message_monotonic < self._AUTO_RESTART_IDLE_SECONDS:
            return
        thread = self._delegation_thread
        if thread is not None and thread.is_alive():
            return
        # Adapter-Pfad (H3): die Delegation laeuft im TaskService-Worker -
        # kein eigener Thread mehr; Flag + Service-Auslastung pruefen.
        if getattr(self, "_delegation_active", False):
            return
        service = getattr(self, "task_service", None)
        if service is not None and getattr(service, "is_busy", False):
            return
        if not self._queue.empty():
            return
        self._auto_restart_attempted_head = head
        logger.info(
            "Voll-Automat: neue Version %s im Leerlauf erkannt - starte selbst neu.",
            head[:8],
        )
        try:
            if not self._request_restart():
                logger.warning("Voll-Automat: Nachfolger-Start fehlgeschlagen - bleibe im Dienst.")
        except Exception:  # noqa: BLE001 - lieber im Dienst bleiben als tot
            logger.exception("Voll-Automat: Neustart fehlgeschlagen - bleibe im Dienst.")

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
            self._impulse_engine.run(on_new=self._push_impulse)
        except Exception:  # noqa: BLE001 - der Kreislauf stoert nie den Scheduler
            logger.exception("Impuls-Kreislauf-Tick fehlgeschlagen.")

    def _push_impulse(self, cand: dict) -> None:
        """Plan F: einen neu gelegten Impuls aktiv an den Besitzer pushen (nur
        wenn eingeschaltet UND ein Notifier gesetzt ist, z. B. Telegram). Der
        Text wird geschwaerzt (ADR-040). Fail-safe."""
        if not self._impulse_push_enabled or self._notifier is None:
            return
        title = redact((cand.get("title") or "").strip())
        detail = redact((cand.get("detail") or "").strip())
        message = (f"{title}\n{detail}".strip() if detail else title).strip()
        if message:
            self._notifier(message)

    def run_briefing_push(self) -> str:
        """Telegram-Ausbau (a): das Morgen-Briefing aktiv an den Besitzer pushen.
        Baut das bewaehrte Briefing (get_briefing) + falls eingerichtet den
        Mail-Ueberblick (check_mail) - beides read-only, Stufe 0 - und schickt es
        ueber den Notifier (geschwaerzt). Liefert den gesendeten Text ('' wenn
        nichts gesendet). Fail-safe."""
        if not self._briefing_push_enabled or self._notifier is None:
            return ""
        parts: list[str] = []
        try:
            r = dispatch(Plan(intent="get_briefing", raw_input=""))
            if r.ok and (r.message or "").strip():
                parts.append(r.message.strip())
        except Exception:  # noqa: BLE001 - ein Baustein-Fehler kippt den Push nicht
            logger.warning("Briefing-Push: get_briefing fehlgeschlagen.", exc_info=True)
        try:
            r = dispatch(Plan(intent="check_mail", raw_input=""))
            # Nur bei Erfolg anhaengen - "kein Konto eingerichtet" o. ae. bleibt weg.
            if r.ok and (r.message or "").strip():
                parts.append(r.message.strip())
        except Exception:  # noqa: BLE001
            logger.warning("Briefing-Push: check_mail uebersprungen.", exc_info=True)
        body = redact("\n\n".join(parts).strip())
        if not body:
            return ""
        message = f"Guten Morgen, Sir — dein Tag:\n\n{body}"
        try:
            self._notifier(message)
        except Exception:  # noqa: BLE001
            logger.exception("Briefing-Push fehlgeschlagen.")
            return ""
        logger.info("Morgen-Briefing gepusht.")
        return message

    def _maybe_run_briefing_push(self, now: Optional[datetime] = None) -> None:
        """Einmal pro Tag ab der konfigurierten Uhrzeit (briefing_push_time).
        Zustand persistiert (briefing_push.json) - ein Neustart am selben Tag
        pusht nicht doppelt. Markiert VOR dem Push (at-most-once, wie die
        Erinnerungen, ADR-039). Fail-safe, auf dem Scheduler-Thread."""
        if not self._briefing_push_enabled or self._notifier is None:
            return
        now = now or datetime.now()
        try:
            hh, mm = (int(x) for x in self._briefing_push_time.split(":", 1))
        except (ValueError, AttributeError):
            hh, mm = 7, 30
        if (now.hour, now.minute) < (hh, mm):
            return
        today = now.date().isoformat()
        state = read_json(self._briefing_push_state_path, {})
        if isinstance(state, dict) and state.get("last") == today:
            return
        write_json_atomic(self._briefing_push_state_path, {"last": today})
        try:
            self.run_briefing_push()
        except Exception:  # noqa: BLE001 - stoert den Scheduler nie
            logger.exception("Briefing-Push-Tick fehlgeschlagen.")

    def run_meeting_prep_push(self, now: Optional[datetime] = None) -> int:
        """Telegram-Ausbau (a): startet ein heutiger Termin in den naechsten
        meeting_prep_lead_minutes, wird die Vorbereitungs-Karte (Plan C4:
        Termin + Person + verwandte offene Aufgaben) EINMAL gepusht. Dedupe je
        Termin persistiert (meeting_prep_push.json, alte Eintraege werden
        beschnitten). Liefert die Anzahl der Pushes. Fail-safe."""
        if not self._meeting_prep_push_enabled or self._notifier is None:
            return 0
        now = now or datetime.now()
        try:
            events = calendar_commands.read_agenda(
                datetime(now.year, now.month, now.day)) or []
        except Exception:  # noqa: BLE001 - Kalender darf den Scheduler nie brechen
            logger.warning("Meeting-Prep-Push: Kalender nicht lesbar.", exc_info=True)
            return 0
        state = read_json(self._meeting_prep_state_path, {})
        if not isinstance(state, dict):
            state = {}
        today = now.date().isoformat()
        sent = 0
        for ev in events:
            if ev.get("all_day"):
                continue
            start_raw = str(ev.get("start") or "")
            try:
                start = datetime.fromisoformat(start_raw)
            except ValueError:
                continue
            if start.tzinfo is not None:
                # Feed-Zeiten koennen eine Zone tragen - auf lokale naive Zeit
                # normalisieren, damit der Vergleich mit `now` nie wirft.
                start = start.astimezone().replace(tzinfo=None)
            minutes = (start - now).total_seconds() / 60.0
            if not (0.0 <= minutes <= float(self._meeting_prep_lead_minutes)):
                continue
            key = f"{start_raw}|{ev.get('subject', '')}"
            if state.get(key):
                continue
            # Markieren VOR dem Push (at-most-once) + alte Tage beschneiden.
            state = {k: v for k, v in state.items() if v == today}
            state[key] = today
            write_json_atomic(self._meeting_prep_state_path, state)
            card = self.prepare_meeting(str(ev.get("subject") or ""))
            try:
                self._notifier(redact(card))
                sent += 1
                logger.info("Meeting-Prep gepusht: %s", ev.get("subject", ""))
            except Exception:  # noqa: BLE001
                logger.exception("Meeting-Prep-Push fehlgeschlagen.")
        return sent

    def _maybe_run_meeting_prep_push(self) -> None:
        """Gedrosselt (alle 5 Minuten reicht bei 30-Minuten-Vorlauf) auf dem
        Scheduler-Thread. Fail-safe."""
        if not self._meeting_prep_push_enabled or self._notifier is None:
            return
        now = time.monotonic()
        if now - self._last_meeting_prep_monotonic < 300.0:
            return
        self._last_meeting_prep_monotonic = now
        try:
            self.run_meeting_prep_push()
        except Exception:  # noqa: BLE001
            logger.exception("Meeting-Prep-Tick fehlgeschlagen.")

    def _maybe_run_reflection(self) -> None:
        """Hoechstens einmal pro Tag: sobald das Datum gewechselt ist,
        reflektiert Jarvis ueber den VORTAG (dessen Log ist dann vollstaendig).
        Fail-safe, auf dem Scheduler-Thread (wie die Impulse). Idempotent: gibt
        es das Journal des Vortags schon, wird nicht neu reflektiert (kein
        doppelter LLM-Call nach einem Neustart am selben Tag)."""
        if self._reflection is None or self._episodic is None:
            return
        today = date.today()
        if self._last_reflection_date == today:
            return
        self._last_reflection_date = today
        try:
            yesterday = today - timedelta(days=1)
            if self._reflection.read(yesterday):
                return  # schon reflektiert
            if self._episodic.for_day(yesterday):
                self.run_daily_reflection(yesterday)
        except Exception:  # noqa: BLE001 - die Reflexion stoert den Scheduler nie
            logger.exception("Reflexions-Tick fehlgeschlagen.")

    def run_daily_reflection(self, day: date) -> None:
        """Reflektiert ueber die Episoden EINES Tages und schreibt das Journal.
        Fail-safe; braucht episodisches Log + aktive Reflexion. Auch manuell
        aufrufbar (z. B. fuer eine sofortige Reflexion des heutigen Tages)."""
        if self._reflection is None or self._episodic is None:
            return
        try:
            episodes = self._episodic.for_day(day)
            text = reflect(episodes, day, lambda prompt: self.ai.answer(prompt, []))
            self._reflection.write(day, text)
            logger.info("Reflexion fuer %s geschrieben (%d Episoden).", day, len(episodes))
            # Stein 2b: eine Vermutung als schwebenden Merk-Vorschlag ablegen
            # (nur wenn Vorschlagen freigeschaltet). Wird beim naechsten
            # Gespraech EINMAL als ja/nein angeboten.
            if self._reflection_offers_enabled:
                cand = suggestion_from_reflection(text)
                if cand:
                    write_json_atomic(self._reflection_suggestion_path,
                                      {"suggestion": cand, "day": day.isoformat()})
        except Exception:  # noqa: BLE001 - die Reflexion stoert nie
            logger.exception("Taegliche Reflexion fehlgeschlagen.")

    def _pending_reflection_suggestion(self) -> str:
        """Der schwebende Reflexions-Merk-Vorschlag (oder ''). Fail-safe."""
        data = read_json(self._reflection_suggestion_path, {})
        return str(data.get("suggestion", "")).strip() if isinstance(data, dict) else ""

    def _clear_reflection_suggestion(self) -> None:
        write_json_atomic(self._reflection_suggestion_path, {})

    # --- Proaktive Vorbereitung (ADR-063) -----------------------------------

    def _maybe_run_proactive(self) -> None:
        """Hoechstens einmal pro Tag, ab dem Abend (_PROACTIVE_HOUR): schaut auf
        den Kalender von MORGEN und legt EINEN Erinnerungs-Vorschlag ab. Opt-in,
        fail-safe (stoert den Scheduler nie). Idempotent ueber Neustarts via
        `generated_for` in der Datei - so wird pro Zieltag nur einmal erzeugt und
        nach einer Antwort nicht erneut angeboten."""
        if not self._proactive_prep_enabled:
            return
        now = datetime.now()
        if now.hour < _PROACTIVE_HOUR:
            return
        today = now.date()
        if self._last_proactive_date == today:
            return
        self._last_proactive_date = today
        try:
            tomorrow = today + timedelta(days=1)
            existing = read_json(self._proactive_suggestion_path, {})
            if isinstance(existing, dict) and existing.get("generated_for") == tomorrow.isoformat():
                return  # fuer diesen Zieltag schon erzeugt/angeboten
            self.run_proactive_check(tomorrow, now=now, day_label="Morgen")
        except Exception:  # noqa: BLE001 - die Vorausschau stoert den Scheduler nie
            logger.exception("Proaktive-Vorbereitung-Tick fehlgeschlagen.")

    def run_proactive_check(self, day: date, now: Optional[datetime] = None,
                            day_label: str = "Morgen") -> Optional[dict]:
        """Liest den Kalender fuer `day`, baut hoechstens einen Vorschlag und
        legt ihn als schwebendes Angebot ab. Auch direkt aufrufbar (Test/manuell).
        Liefert den abgelegten Vorschlag (dict) oder None."""
        now = now or datetime.now()
        events = calendar_commands.read_agenda(datetime(day.year, day.month, day.day))
        # ADR-066 Stein 2: den bemerkenswerten Termin mit Person + verwandten
        # offenen Aufgaben anreichern (der COO verbindet die Punkte).
        ev = notable_event(events)
        subject = str((ev or {}).get("subject") or "").strip()
        people = self._people.find_in_text(subject) if subject else []
        related = self._related_open_tasks(subject) if subject else []
        suggestion = plan_preparation(events, now, day_label=day_label,
                                      people=people, related_tasks=related)
        if suggestion is None:
            return None
        payload = suggestion.to_dict()
        payload["generated_for"] = day.isoformat()
        payload["done"] = False
        write_json_atomic(self._proactive_suggestion_path, payload)
        logger.info("Proaktive Vorbereitung: Vorschlag fuer %s abgelegt (%s).",
                    day, suggestion.subject)
        return payload

    def _related_open_tasks(self, subject: str, limit: int = 2) -> list[str]:
        """Offene Eintraege, die thematisch zum Termin-Titel passen (gemeinsamer
        Wort-Stamm >= 5 Zeichen, z. B. 'Steuerberater' <-> 'Steuerunterlagen') -
        ADR-066 Stein 2. Fail-safe leer."""
        try:
            entries = self._entry_store.list_open()
        except Exception:  # noqa: BLE001
            return []

        def stems(text: str) -> set:
            return {w[:5] for w in (text or "").lower().replace("-", " ").split() if len(w) >= 5}

        subj = stems(subject)
        if not subj:
            return []
        out: list[str] = []
        for entry in entries:
            if stems(entry.text) & subj:
                out.append(entry.text)
                if len(out) >= limit:
                    break
        return out

    def prepare_meeting(self, query: str = "") -> str:
        """Meeting-Prep (Plan C4): buendelt zu einem anstehenden Termin (heute/
        morgen) den Kontext - Termin + bekannte Person(en) + verwandte offene
        Aufgaben - zu einer Vorbereitungs-Karte. On-demand ('bereite mein Meeting
        vor'). Deterministisch, read-only, fail-safe."""
        try:
            events: list[dict] = []
            for offset in (0, 1):
                d = date.today() + timedelta(days=offset)
                events.extend(calendar_commands.read_agenda(datetime(d.year, d.month, d.day)) or [])
        except Exception:  # noqa: BLE001 - Kalender darf die Prep nie brechen
            logger.warning("Meeting-Prep: Kalender nicht lesbar.", exc_info=True)
            return "Ich komme gerade nicht an deinen Kalender, Sir."
        if not events:
            return "Ich sehe heute und morgen keinen Termin, Sir."

        ev = self._pick_meeting(events, query)
        subject = str(ev.get("subject") or "Termin").strip()
        when = str(ev.get("start") or "").replace("T", " ")[:16]
        people = self._people.find_in_text(f"{subject} {query}".strip())
        person_ctx = PeopleStore.context_block(people)
        related = self._related_open_tasks(subject)

        lines = [f"Vorbereitung «{subject}»" + (f" ({when})" if when else "") + ":"]
        if person_ctx:
            lines.append(person_ctx)
        if related:
            lines.append("Dazu ist bei dir noch offen: " + "; ".join(related) + ".")
        if not person_ctx and not related:
            lines.append("Ich habe dazu keinen weiteren Kontext gespeichert, Sir.")
        return "\n".join(lines)

    @staticmethod
    def _pick_meeting(events: list[dict], query: str) -> dict:
        """Waehlt den Termin: passt ein Wort aus der Anfrage zu einem Betreff,
        diesen - sonst den ersten (naechsten). Fail-safe."""
        words = {w for w in (query or "").lower().split() if len(w) >= 3}
        if words:
            for ev in events:
                subject = str(ev.get("subject") or "").lower()
                if any(w in subject for w in words):
                    return ev
        return notable_event(events) or events[0]

    def _pending_proactive(self) -> dict:
        """Der schwebende, noch nicht beantwortete Vorbereitungs-Vorschlag (oder
        {}). Fail-safe."""
        data = read_json(self._proactive_suggestion_path, {})
        if isinstance(data, dict) and data.get("nudge") and not data.get("done"):
            return data
        return {}

    def _mark_proactive_offered(self) -> None:
        """Markiert den Vorschlag als angeboten (done=true), OHNE `generated_for`
        zu verlieren - so wird er nicht erneut erzeugt und nicht erneut gefragt."""
        data = read_json(self._proactive_suggestion_path, {})
        if isinstance(data, dict) and data:
            data["done"] = True
            write_json_atomic(self._proactive_suggestion_path, data)

    def _should_compose_show(self, steps, results) -> bool:
        """Soll die komponierte Antwort GEZEIGT werden (ADR-065 A2)? Nur bei
        durchweg erfolgreichen Schritten (bei Fehler/Rueckfrage bleibt die klare
        Schablone). Multi-Step generell (der groesste Gewinn) und/oder die
        freigegebenen Einzel-Intents (Whitelist)."""
        if not results or not all(getattr(r, "ok", False) for r in results):
            return False
        if self._response_compose_multistep and len(results) >= 2:
            return True
        wl = self._response_compose_intents
        return bool(wl) and all(s.intent in wl for s in steps[:len(results)])

    def _reversible_answer_directive(self, user_input, steps, results) -> str:
        """"Antworten + gleich tun" (ADR-068): Hat der Nutzer eine FRAGE gestellt
        ('?') und wurde dabei EINE umkehrbare Gedaechtnis-Aktion (merken/loeschen)
        erfolgreich ausgefuehrt, liefert dies die Composer-Weisung, die Frage zu
        beantworten UND die Tat samt Undo-Hinweis zu nennen. Sonst ''. Der PO-
        Grundsatz 12.07.: eine Frage NIE stumm mit einer Tat quittieren."""
        if not self._answer_and_act_enabled:
            return ""
        if "?" not in (user_input or ""):
            return ""
        if not results or not all(getattr(r, "ok", False) for r in results):
            return ""
        if not steps or not all(s.intent in _REVERSIBLE_MEMORY_INTENTS for s in steps[:len(results)]):
            return ""
        return (
            "Der Nutzer hat eine FRAGE gestellt UND du hast dabei etwas Umkehrbares "
            "getan (gemerkt bzw. geloescht). Beantworte ZUERST seine Frage ehrlich "
            "und mit knapper Begruendung; sag DANN in einem Satz, was du getan hast; "
            "weise am Ende dezent darauf hin, dass er es rueckgaengig machen kann "
            "('sag Bescheid, wenn nicht'). Quittiere die Frage NIE nur mit der Tat."
        )

    def _compose_reply(self, user_input, history, steps, results, long_term_summary,
                       extra_directive: str = ""):
        """Baut die komponierte Antwort aus dem vollen Kontext - fail-safe:
        None bei Fehler/leer (der Aufrufer behaelt dann die Schablone). Der
        Composer FORMULIERT nur, er handelt nie (ADR-065)."""
        try:
            composed = compose_response(
                user_input, history, steps, results,
                lambda system, user_text: self.ai.generate(system, user_text, model=self._compose_model),
                long_term_summary=long_term_summary,
                owner_name=getattr(getattr(self.ai, "config", None), "owner_name", "") or "",
                extra_directive=extra_directive,
                persona_form=getattr(getattr(self.ai, "config", None), "persona_form", "du") or "du",
            )
            return composed or None
        except Exception:  # noqa: BLE001 - der Composer stoert den Live-Pfad nie
            logger.warning("Antwort-Composer fehlgeschlagen (ignoriert) -> Schablone.", exc_info=True)
            return None

    def _summarize_conversation(self, prev_summary: str, messages) -> str:
        """LLM-Zusammenfassung fuer die Sitzungs-Zusammenfassung (ADR-065 B1) auf
        dem guenstigen Modell. Faltet die uebergebenen (aelteren) Nachrichten in
        die bisherige Zusammenfassung. Fail-safe: bei Fehler bleibt der alte
        Stand (Rueckgabe prev_summary)."""
        convo = "\n".join(
            f"{'Nutzer' if getattr(m, 'role', '') == 'user' else 'Jarvis'}: "
            f"{(getattr(m, 'content', '') or '').strip()[:300]}"
            for m in messages if (getattr(m, "content", "") or "").strip()
        )
        system = (
            "Du fuehrst eine KNAPPE, sachliche Gespraechs-Zusammenfassung fort. "
            "Behalte, was fuer den weiteren Verlauf wichtig ist: Ziele/Wuensche des "
            "Nutzers, getroffene Entscheidungen, offene Punkte, wichtige Fakten. "
            "Keine Floskeln, keine Anrede, hoechstens ein paar Saetze."
        )
        user = (f"Bisherige Zusammenfassung:\n{prev_summary or '(noch keine)'}\n\n"
                f"Neue (aeltere) Nachrichten, die du einarbeiten sollst:\n{convo}\n\n"
                "Gib die AKTUALISIERTE Gesamt-Zusammenfassung zurueck.")
        try:
            return self.ai.generate(system, user, model=self._compose_model) or prev_summary
        except Exception:  # noqa: BLE001
            logger.warning("Sitzungs-Zusammenfassung: LLM-Fehler (ignoriert).", exc_info=True)
            return prev_summary

    def run_semantic_sync(self) -> int:
        """Indiziert neue Gedaechtnis-Inhalte (Fakten + Episoden der letzten Tage)
        semantisch (ADR-065 B2). Nur neue (Dedupe im Index). Fail-safe; liefert
        die Zahl neu indizierter Eintraege. Auch manuell aufrufbar (Test)."""
        if not self._semantic_enabled:
            return 0
        entries: list[tuple[str, str]] = []
        try:
            for fact in self.long_term.all_facts():
                if fact.text.strip():
                    entries.append((fact.text.strip(), "fakt"))
        except Exception:  # noqa: BLE001
            pass
        try:                                          # Personen (ADR-066) mit-indizieren
            for person in self._people.all():
                notes = "; ".join(person.get("notes", []))
                if notes:
                    entries.append((f"{person.get('name', '?')}: {notes}", "person"))
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._episodic is not None:
                for offset in range(7):                       # die letzten 7 Tage
                    day = date.today() - timedelta(days=offset)
                    for ep in self._episodic.for_day(day):
                        ui = (ep.get("user_input") or "").strip()
                        resp = (ep.get("response") or "").strip()
                        if ui:
                            entries.append((ui + (f" -> {resp[:120]}" if resp else ""), "episode"))
        except Exception:  # noqa: BLE001
            pass
        if not entries:
            return 0
        try:
            n = self._semantic.add_texts(entries)
        except Exception:  # noqa: BLE001 - Indizieren stoert nie den Live-Pfad
            logger.warning("Semantik-Sync fehlgeschlagen (ignoriert).", exc_info=True)
            return 0
        if n:
            logger.info("Semantik: %d neue Erinnerung(en) indiziert.", n)
        return n

    def _maybe_run_semantic_sync(self) -> None:
        """Gedrosselter Sync auf dem Scheduler-Thread (wie die Impulse). Fail-safe."""
        if not self._semantic_enabled:
            return
        now = time.monotonic()
        if now - self._last_semantic_sync < _SEMANTIC_SYNC_INTERVAL_SECONDS:
            return
        self._last_semantic_sync = now
        try:
            self.run_semantic_sync()
        except Exception:  # noqa: BLE001
            logger.exception("Semantik-Sync-Tick fehlgeschlagen.")

    def _semantic_recall(self, query: str) -> str:
        """Relevante Erinnerungen zu `query` als kurzer Kontext-Block (oder '').
        Ueberspringt triviale Eingaben (Kosten/Latenz). Fail-safe."""
        if not self._semantic_enabled or len((query or "").split()) < 3:
            return ""
        try:
            hits = self._semantic.search(query, k=3)
        except Exception:  # noqa: BLE001
            return ""
        if not hits:
            return ""
        return "Relevante Erinnerungen:\n" + "\n".join(f"- {h['text']}" for h in hits)

    def run_self_review(self, day: Optional[date] = None, days: int = 7) -> str:
        """Bewertet die eigene Leistung ueber die letzten `days` Tage und schreibt
        das Journal (ADR-066 Stein 3). Auch manuell aufrufbar. Liefert den Text
        (oder ''). Fail-safe; braucht episodisches Log + Freigabe."""
        if not self._self_review_enabled or self._episodic is None:
            return ""
        day = day or date.today()
        episodes: list[dict] = []
        try:
            for offset in range(days):
                episodes.extend(self._episodic.for_day(day - timedelta(days=offset)))
        except Exception:  # noqa: BLE001
            return ""
        text = self_review(
            episodes, f"letzte {days} Tage (Stand {day.isoformat()})",
            lambda prompt: self.ai.generate(
                "Du bist Jarvis und bewertest ehrlich und nuechtern deine eigene "
                "Leistung als Assistent.", prompt, model=self._compose_model),
        )
        if text:
            self._self_review.write(day, text)
            logger.info("Selbstbewertung fuer %s geschrieben (%d Episoden).", day, len(episodes))
        return text

    def _maybe_run_self_review(self) -> None:
        """Hoechstens einmal pro Tag (rollierend ueber die letzte Woche). Fail-safe,
        auf dem Scheduler-Thread."""
        if not self._self_review_enabled:
            return
        today = date.today()
        if self._last_self_review_date == today:
            return
        self._last_self_review_date = today
        try:
            self.run_self_review(today)
        except Exception:  # noqa: BLE001
            logger.exception("Selbstbewertungs-Tick fehlgeschlagen.")

    def run_build_suggestion(self, day: Optional[date] = None) -> str:
        """Leitet aus Nutzung + Reibungen EINE baubare Werkzeug-Idee ab und legt
        sie als schwebenden Vorschlag ab (ADR-067). Gebaut wird nie automatisch.
        Auch manuell aufrufbar. Liefert den Text (oder ''). Fail-safe."""
        if not self._build_offers_enabled:
            return ""
        day = day or date.today()
        counts: dict = {}
        try:
            with self.habits._lock:  # noqa: SLF001 - geteilte Instanz, wie in commands/ideas
                counts = self.habits._read().get("counts", {})  # noqa: SLF001
        except Exception:  # noqa: BLE001
            counts = {}
        episodes: list[dict] = []
        try:
            if self._episodic is not None:
                for offset in range(7):
                    episodes.extend(self._episodic.for_day(day - timedelta(days=offset)))
        except Exception:  # noqa: BLE001
            pass
        try:
            known_skills = self._skills.names()
        except Exception:  # noqa: BLE001
            known_skills = []
        text = suggest_build(
            usage_text(counts), frictions_text(episodes),
            lambda system, prompt: self.ai.generate(system, prompt, model=self._compose_model),
            existing_skills=known_skills,
        )
        if text:
            write_json_atomic(self._build_suggestion_path,
                              {"text": text, "done": False, "generated": day.isoformat()})
            logger.info("Bau-Vorschlag abgelegt.")
        return text

    def _maybe_run_build_suggestion(self) -> None:
        """Hoechstens alle paar Tage einen neuen Bau-Vorschlag (gedrosselt, nervt
        nicht). Fail-safe, auf dem Scheduler-Thread."""
        if not self._build_offers_enabled:
            return
        today = date.today()
        if self._last_build_suggestion_date == today:
            return
        self._last_build_suggestion_date = today
        try:
            data = read_json(self._build_suggestion_path, {})
            if isinstance(data, dict):
                if data.get("text") and not data.get("done"):
                    return                       # noch ein un-gesurfter Vorschlag pending
                gen = data.get("generated")
                if gen:
                    try:
                        if (today - date.fromisoformat(gen)).days < 3:
                            return               # nicht oefter als alle 3 Tage
                    except ValueError:
                        pass
            self.run_build_suggestion(today)
        except Exception:  # noqa: BLE001
            logger.exception("Bau-Vorschlags-Tick fehlgeschlagen.")

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

        # Auftrags-Loop (Phase B.1): begrenzter Join (§9) - der laufende
        # Auftrag bleibt crash-sicher im Store und setzt beim naechsten
        # Start fort (Wiederanlauf-Regeln §7).
        if self.task_service is not None:
            self.task_service.stop(join_seconds=10.0)

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
        self._last_message_monotonic = time.monotonic()  # Leerlauf-Uhr (Voll-Automat)
        self._speech.confirmer = confirmer
        try:
            self._process_inner(text, reply_callback, plan_filter, allow_async, source)
        finally:
            self._last_message_monotonic = time.monotonic()
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

    def _note_undoable(self, steps: list[Plan], results, source: str) -> None:
        """Merkt sich die letzte UMKEHRBARE Einzel-Tat fuers nackte «nein»
        direkt danach (Live-Befund 15.07.). Nur bei genau EINEM erfolgreichen
        Schritt - bei Mehrschritt wird nie geraten, was gemeint ist. Jede
        andere Tat loescht den Merker (das «nein» gehoert immer zur LETZTEN
        Antwort). Fail-safe: nie werfend."""
        try:
            self._last_undoable = None
            if len(steps) != 1 or len(results) != 1 or not getattr(results[0], "ok", False):
                return
            data = results[0].data or {}
            intent = steps[0].intent
            if intent == "add_entry" and data.get("id"):
                self._last_undoable = {
                    "undo_intent": "delete_entry", "handle": str(data["id"]),
                    "exact": False, "ts": time.monotonic(), "source": source,
                }
            elif intent == "remember_fact" and data.get("text"):
                self._last_undoable = {
                    "undo_intent": "forget_fact", "handle": str(data["text"]),
                    "exact": True, "ts": time.monotonic(), "source": source,
                }
        except Exception:  # noqa: BLE001 - der Merker ist Beiwerk
            logger.debug("Undo-Merker fehlgeschlagen (ignoriert).", exc_info=True)

    def _maybe_undo_last(self, text: str, reply_callback: Callable[[str], None],
                         source: str) -> bool:
        """Behandelt ein nacktes «nein»/«doch nicht» als ECHTES Undo der
        letzten umkehrbaren Tat: das Werkzeug loescht (Papierkorb faengt es),
        die Antwort ist die ehrliche Werkzeug-Antwort - nie behaupteter
        Vollzug. Kanalgebunden und zeitbegrenzt; ohne Merker laeuft die
        Nachricht normal weiter (nie verschluckt)."""
        last = self._last_undoable
        if last is None:
            return False
        normalized = text.strip().lower().rstrip(".!,")
        if normalized not in _UNDO_PHRASES:
            return False
        self._last_undoable = None                      # einmalig
        if time.monotonic() - float(last.get("ts", 0)) > _UNDO_WINDOW_SECONDS:
            return False
        if source and last.get("source") and source != last["source"]:
            return False                                 # fremder Kanal: normal weiter
        result = dispatch(Plan(
            intent=str(last["undo_intent"]), target=str(last["handle"]),
            parameters={"text": str(last["handle"]), "exact": bool(last.get("exact"))},
        ))
        reply = result.message or "Erledigt, Sir — zurückgenommen."
        logger.info("Undo per nacktem «%s»: %s -> %s.", normalized,
                    last["undo_intent"], "ok" if result.ok else "fehlgeschlagen")
        self.memory.append_history(Message(role="user", content=text))
        self.memory.append_history(Message(role="assistant", content=reply))
        self._safe_reply(reply_callback, reply, text)
        return True

    def _process_inner(
        self,
        text: str,
        reply_callback: Callable[[str], None],
        plan_filter: Optional[Callable[[list[Plan]], tuple[list[Plan], Optional[str]]]] = None,
        allow_async: bool = False,
        source: str = "",
    ) -> None:
        started = time.monotonic()
        # Erlaubnis-Frage des Bau-Agenten (S4b Scheibe 2, ADR-071) konsumieren -
        # VOR allem anderen: der Hook-Prozess WARTET auf diese Antwort. Nur der
        # Frage-Kanal (Telegram) darf antworten; ja/nein schreibt die
        # Entscheidung in die Mailbox, alles andere laesst die Frage verfallen
        # (Hook-Timeout = NEIN, fail-closed) und laeuft normal weiter.
        perm = self._permission_offer
        if perm is not None:
            offer_source, req_id, deadline = perm
            answer = text.strip().lower().rstrip(".!,")
            # PO-Live-Befund 13.07.: er antwortete zuerst am Desktop - ein
            # ja/nein zaehlt deshalb aus JEDEM Kanal des Besitzers (alle
            # Kanaele sind besitzer-gebunden; wer die Frage sieht, darf
            # antworten). Anderes Thema aus dem FRAGE-Kanal laesst die Frage
            # verfallen; fremde Kanaele lassen sie armiert.
            if answer in (_OFFER_YES | _OFFER_NO):
                self._permission_offer = None
                allow = answer in _OFFER_YES and time.monotonic() < deadline
                self._hook_mailbox.answer(req_id, allow)
                if answer in _OFFER_YES and not allow:
                    reply = ("Die Frage war schon abgelaufen, Sir - ich habe "
                             "sicherheitshalber mit Nein geantwortet.")
                elif allow:
                    reply = "Erlaubt, Sir - der Agent führt den Befehl aus."
                else:
                    reply = ("Abgelehnt, Sir - der Agent baut weiter, nur ohne "
                             "diesen Befehl. («stopp den Agenten» hält ihn ganz an.)")
                self.memory.append_history(Message(role="user", content=text))
                self.memory.append_history(Message(role="assistant", content=reply))
                self._safe_reply(reply_callback, reply, text)
                return
            if source == offer_source:
                # anderes Thema aus demselben Kanal: Frage verfaellt (Hook-
                # Timeout uebernimmt das NEIN), Nachricht laeuft normal.
                self._permission_offer = None

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

        # Proaktiver Vorbereitungs-Vorschlag (ADR-063) konsumieren, BEVOR der
        # Planner laeuft - kanalgebunden wie das Merk-Angebot. "ja" legt die
        # Erinnerung an, "nein" verwirft; alles andere laesst ihn still verfallen.
        prep_pending = self._proactive_offer
        if prep_pending is not None:
            self._proactive_offer = None
            offer_source, payload = prep_pending
            answer = text.strip().lower().rstrip(".!,")
            if source != offer_source:
                answer = ""  # fremder Kanal: Angebot verfaellt, Nachricht laeuft normal
            if answer in _OFFER_YES:
                self._entry_store.add(
                    text=str(payload.get("reminder_text", "")).strip() or "Termin",
                    when=str(payload.get("reminder_when_iso", "")),
                )
                reply = (f"Erledigt, Sir — ich melde mich um {payload.get('reminder_time', '')} Uhr "
                         f"wegen «{payload.get('subject', '')}».")
                self.memory.append_history(Message(role="user", content=text))
                self.memory.append_history(Message(role="assistant", content=reply))
                self._safe_reply(reply_callback, reply, text)
                return
            if answer in _OFFER_NO:
                reply = "Alles klar, Sir — dann erinnere ich nicht daran."
                self.memory.append_history(Message(role="user", content=text))
                self.memory.append_history(Message(role="assistant", content=reply))
                self._safe_reply(reply_callback, reply, text)
                return

        # Nacktes «nein»/«doch nicht» direkt nach einer umkehrbaren Tat =
        # deterministisches Undo (Live-Befund 15.07.: der Chat behauptete
        # sonst eine Loeschung, die nie lief). VOR dem Planner - die Antwort
        # wird garantiert, nicht klassifiziert (ADR-068-Lehre).
        if self._maybe_undo_last(text, reply_callback, source):
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
                if confirmation_required(command, steps[0]) and not steps[
                    0
                ].parameters.get("confirmed"):
                    # Kundendeutsch statt Alttext (Chatlog-Review 14.07.: hier
                    # lebte noch das kryptische 'Abgebrochen - keine
                    # Bestätigung erhalten', das der Executor-Pfad laengst
                    # verloren hat). Kein Bestaetigungsweg -> Weg erklaeren;
                    # Nein/keine Antwort -> ehrlich und folgenlos.
                    if not getattr(self._speech, "can_confirm", True):
                        self._safe_reply(reply_callback, (
                            "Das braucht deine ausdrückliche Bestätigung, Sir — "
                            "über diesen Weg kann ich sie nicht einholen. Schreib "
                            "es mir kurz im Chat oder am Handy; dort frage ich "
                            "mit ja/nein nach."), text)
                        return
                    if not request_confirmation(self._speech, command, steps[0]):
                        self._safe_reply(reply_callback, (
                            "Verstanden, Sir — ich lasse es. Ohne dein «ja» "
                            "passiert hier nichts."), text)
                        return
                    steps[0].parameters["confirmed"] = True
                self._emit_timeline(
                    stage="delegation", job=job, index=0,
                    intent=steps[0].intent, target=(steps[0].target or ""),
                )
                self._dispatch_delegation(text, steps[0], command, reply_callback, job=job)
                return

        long_term_summary = self.long_term.summary_text()

        # Aktions-Zustand (UX-Scheibe S4, PO-Live-Befund 13.07.: nach 'starte
        # neu' + 'nein' behauptete der Chat 'kein Neustart', obwohl er lief):
        # der Kern bekommt den ECHTEN Zustand (frischer Start, laufender Bau,
        # letzte Aktionen) und die Regel, Aktionszustaende NIE zu erfinden.
        state_block = self._action_state_block()
        if state_block:
            long_term_summary = (
                (long_term_summary + "\n\n" if long_term_summary else "") + state_block
            )

        # Sitzungs-Zusammenfassung (ADR-065 B1): in langen Gespraechen faellt der
        # aeltere Verlauf aus dem Fenster - eine rollierende Zusammenfassung haelt
        # den Faden. Sie reitet auf long_term_summary mit (fliesst so zu Chat UND
        # Composer). Opt-in, fail-safe.
        # HINTERGRUND statt Antwortpfad (Latenz-Messung 13.07.: das Einfalten
        # blockierte die Antwort um 8,3 s - groesster Einzelposten der
        # 16,5-s-Wetterantwort). Diese Runde nutzt den Stand der Vorrunde;
        # zusammengefasst wird ohnehin nur AELTERER Verlauf - verlustfrei.
        if self._session_summary_enabled:
            try:
                self._session_summary.maybe_update_async(
                    list(self.memory.get_history()), self._summarize_conversation)
            except Exception:  # noqa: BLE001 - stoert den Live-Pfad nie
                logger.warning("Sitzungs-Zusammenfassung fehlgeschlagen (ignoriert).", exc_info=True)
            sess = self._session_summary.summary()
            if sess:
                long_term_summary = (
                    (long_term_summary + "\n\n" if long_term_summary else "")
                    + f"Bisheriges Gespraech (Zusammenfassung):\n{sess}"
                )

        # Semantischer Abruf (ADR-065 B2): relevante Erinnerungen zur Anfrage in
        # den Kontext holen (reitet ebenfalls auf long_term_summary -> Chat + Composer).
        recall = self._semantic_recall(text)
        if recall:
            long_term_summary = (long_term_summary + "\n\n" if long_term_summary else "") + recall

        # Personen-Gedaechtnis (ADR-066 Stein 1): in der Anfrage erwaehnte bekannte
        # Personen mit ihrem Kontext einspielen ("Meeting mit Anna" -> wer Anna ist).
        try:
            people_block = PeopleStore.context_block(self._people.find_in_text(text))
        except Exception:  # noqa: BLE001 - stoert den Live-Pfad nie
            people_block = ""
        if people_block:
            long_term_summary = (long_term_summary + "\n\n" if long_term_summary else "") + people_block

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
        # Aktions-Zustand (UX-S4): echte Aktionen (kein chat) festhalten, damit
        # spaetere Antworten sich auf FAKTEN stuetzen statt zu raten.
        for index, r in enumerate(report.results):
            intent = steps[index].intent if index < len(steps) else "?"
            if intent != "chat":
                self._recent_actions.append((intent, bool(r.ok), time.monotonic()))
        response_text = "\n".join(report.summary_lines()) or "Alles klar."

        # Letzte umkehrbare Tat fuer das nackte «nein» merken (15.07.).
        self._note_undoable(steps, report.results, source)
        # Antwort-Composer (ADR-065): im Schatten loggen (A1) und/oder die
        # komponierte Antwort ZEIGEN (A2). Ein Aufruf, fail-safe (bei Fehler/leer
        # bleibt die Schablone). "Antworten + gleich tun" (ADR-068): faellt bei
        # einer Frage eine umkehrbare Merk-/Loesch-Aktion, erzwingt eine Weisung den
        # Composer (Frage beantworten + Tat + Undo-Hinweis) statt der stummen Tat.
        directive = self._reversible_answer_directive(text, steps, report.results)
        show_composed = self._should_compose_show(steps, report.results) or bool(directive)
        if self._response_compose_shadow or show_composed:
            composed = self._compose_reply(text, history, steps, report.results,
                                           long_term_summary, extra_directive=directive)
            if self._response_compose_shadow and composed:
                intents = "+".join(s.intent for s in steps) or "?"
                logger.info("Antwort-Schatten [%s]: template=%dZ composed=%dZ",
                            intents, len(response_text), len(composed))
                logger.info("Antwort-Schatten SCHABLONE: %s", response_text.replace("\n", " ")[:600])
                logger.info("Antwort-Schatten COMPOSED:  %s", composed.replace("\n", " ")[:600])
            if show_composed and composed:
                logger.info("Antwort-Composer FUEHRT (%s): komponierte Antwort (ADR-065 A2).",
                            "+".join(s.intent for s in steps))
                response_text = composed

        # Merk-Angebot (ADR-051) anbieten: nur wenn eingeschaltet, der Fakt
        # weder bekannt noch abgelehnt ist - und IMMER als Frage, nie als Tat.
        if self._memory_offers_enabled:
            suggestion = next(
                (s.memory_suggestion for s in steps if getattr(s, "memory_suggestion", "")), ""
            )
            if suggestion and not self._memory_suggestion_known(suggestion):
                response_text += f"\n\nSoll ich mir dauerhaft merken: «{suggestion}»? (ja/nein)"
                self._memory_offer = (source, suggestion)  # kanalgebunden (Fix A)

        # Stein 2b: ist KEIN inline-Angebot gesetzt, biete ggf. einen Reflexions-
        # Merk-Vorschlag an (die Schleife beobachten->reflektieren->EINMAL
        # fragen). Ueber dieselbe kanalgebundene ja/nein-Schiene; genau EINMAL
        # (danach geloescht), Nerv-Schutz via _memory_suggestion_known.
        if self._memory_offer is None and self._reflection_offers_enabled:
            pending = self._pending_reflection_suggestion()
            if pending:
                if not self._memory_suggestion_known(pending):
                    response_text += (
                        f"\n\nMir ist uebrigens aufgefallen: «{pending}». "
                        "Soll ich mir das als Gewohnheit merken? (ja/nein)"
                    )
                    self._memory_offer = (source, pending)
                self._clear_reflection_suggestion()  # nur EINMAL vorschlagen

        # Proaktive Vorbereitung (ADR-063): steht ein Vorschlag der abendlichen
        # Vorausschau bereit und ist gerade KEIN anderes Angebot offen, haenge ihn
        # EINMAL als ja/nein an die Antwort. Kanalgebunden; danach als angeboten
        # markiert (kein erneutes Fragen).
        if (self._memory_offer is None and self._proactive_offer is None
                and self._proactive_prep_enabled):
            prep = self._pending_proactive()
            if prep:
                response_text += f"\n\n{prep['nudge']}"
                self._proactive_offer = (source, prep)
                self._mark_proactive_offered()

        # Proaktiver Bau-Vorschlag (ADR-067): EINMAL anhaengen, wenn gerade kein
        # anderes Angebot offen ist. Reiner Hinweis (kein ja/nein) - der Nutzer
        # loest den Bau selbst per "Bau mir X" aus (bestehender gated Pfad).
        if (self._build_offers_enabled and self._memory_offer is None
                and self._proactive_offer is None):
            _bs = read_json(self._build_suggestion_path, {})
            if isinstance(_bs, dict) and _bs.get("text") and not _bs.get("done"):
                response_text += f"\n\n{_bs['text']}"
                _bs["done"] = True
                write_json_atomic(self._build_suggestion_path, _bs)

        # "Neu bei mir"-Hinweis (Spektakulaer #1, Kundenreview: neue Faehig-
        # keiten stellen sich EINMAL selbst vor): hat sich der juengste
        # CHANGELOG-Eintrag seit dem letzten Hinweis geaendert, EIN dezenter
        # Satz - nie zusammen mit einem anderen Angebot. Fail-safe.
        if (self._whats_new_hint_enabled and self._memory_offer is None
                and self._proactive_offer is None):
            try:
                head = help_commands.latest_headline()
                seen = read_json(self._whats_new_seen_path, {})
                if head and (not isinstance(seen, dict) or seen.get("head") != head):
                    write_json_atomic(self._whats_new_seen_path, {"head": head})
                    title = head.split(" - ", 1)[-1].strip()
                    response_text += (
                        f"\n\n✨ Übrigens, ich habe Neues gelernt: {title}. "
                        "Frag «Was ist neu?», wenn du mehr wissen willst."
                    )
            except Exception:  # noqa: BLE001 - der Hinweis stoert nie
                logger.warning("Neu-bei-mir-Hinweis fehlgeschlagen (ignoriert).", exc_info=True)

        # Neue-Version-Hinweis (Spektakulaer #5-light): einmal je neuem Stand,
        # nie neben einem anderen Angebot.
        if (self._version_hint_pending and self._memory_offer is None
                and self._proactive_offer is None):
            self._version_hint_pending = False
            if self._auto_restart_enabled:
                # Voll-Automat an: der Hinweis verspricht die Selbst-Uebernahme,
                # statt das «starte neu»-Ritual zu verlangen.
                response_text += (
                    "\n\n✨ Ich habe übrigens eine neue Version bekommen — ich "
                    "übernehme sie von selbst, sobald hier gerade nichts ansteht. "
                    "Eilig? Sag «starte neu»."
                )
            else:
                response_text += (
                    "\n\n✨ Ich habe übrigens eine neue Version bekommen — sag "
                    "«starte neu», dann übernehme ich sie (dauert nur einen Moment, "
                    "unser Gespräch bleibt erhalten)."
                )

        self.memory.append_history(Message(role="user", content=text))
        self.memory.append_history(Message(role="assistant", content=response_text))
        # Episodisches Gedaechtnis (Stufe 1): eine Episode ins Tagebuch - was
        # der Nutzer wollte, welche Werkzeuge liefen, was Jarvis antwortete.
        # record() ist selbst fail-safe (stoert den Live-Pfad nie).
        if self._episodic is not None:
            self._episodic.record(
                user_input=text,
                intents=[s.intent for s in steps],
                response=response_text,
                source=source,
            )
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
        """Quittiert sofort und fuehrt den long_running-Lauf aus - seit
        Hardening H3 (§9-Migration) ueber den TaskService-Adapter (EIN
        Worker, EINE Lease, keine eigene Thread-Schicht). Ist bereits etwas
        aktiv, wird hoeflich abgelehnt (Nebenlaeufigkeit = 1, ADR-035).
        Der alte Thread-Pfad bleibt NUR als Rueckfall, falls der TaskService
        nicht gebaut werden konnte (fail-safe, nie beide gleichzeitig)."""
        service = self.task_service
        if service is not None:
            with self._state_lock:
                busy = self._delegation_active
            accepted = (not busy) and service.submit_legacy(
                "delegation",
                lambda cancel_event: self._run_delegation_adapter(
                    text, step, command, reply_callback, cancel_event, job),
            )
            if not accepted:
                self._safe_reply(
                    reply_callback,
                    "Es läuft bereits eine Analyse, Sir - eins nach dem anderen; ich melde mich.",
                    text,
                )
                return
            self._safe_reply(
                reply_callback,
                "Ich kümmere mich darum, Sir - Bericht folgt, sobald das Ergebnis vorliegt.",
                text,
            )
            self._recent_actions.append((f"{step.intent} (gestartet, laeuft)", True, time.monotonic()))
            return

        # --- Rueckfall: alter Thread-Pfad (nur ohne TaskService) -----------
        with self._state_lock:
            if self._delegation_active:
                busy = True
            else:
                # Nachtrag 4 (ADR-074): auch der Rueckfall teilt sich die
                # ExecutionLease - nie zwei Ausfuehrungspfade.
                busy = not self.execution_lease.acquire("delegation")
                if not busy:
                    self._delegation_active = True
        if busy:
            self._safe_reply(
                reply_callback,
                "Es läuft bereits eine Analyse, Sir - eins nach dem anderen; ich melde mich.",
                text,
            )
            return
        self._safe_reply(
            reply_callback,
            "Ich kümmere mich darum, Sir - Bericht folgt, sobald das Ergebnis vorliegt.",
            text,
        )
        cancel_event = threading.Event()
        self._delegation_cancel = cancel_event

        def _legacy_thread_run() -> None:
            try:
                self._run_delegation(text, step, command, reply_callback, cancel_event, job)
            finally:
                self.execution_lease.release("delegation")

        thread = threading.Thread(
            target=_legacy_thread_run, name="jarvis-delegation", daemon=False,
        )
        self._delegation_thread = thread
        thread.start()
        self._recent_actions.append((f"{step.intent} (gestartet, laeuft)", True, time.monotonic()))
        self._start_hook_watcher(cancel_event)

    def _run_delegation_adapter(
        self, text: str, step: Plan, command, reply_callback: Callable[[str], None],
        cancel_event: threading.Event, job: int,
    ) -> None:
        """Kompatibilitaetsadapter (§9-Migration): der Legacy-Lauf im
        TaskService-Worker. Haelt die bekannten Zustaende (_delegation_active,
        _delegation_cancel) fuer Kill-Switch, Redirect, Statusanzeige und
        Voll-Automat aufrecht; die Lease haelt der Service-Worker."""
        with self._state_lock:
            self._delegation_active = True
        self._delegation_cancel = cancel_event
        self._start_hook_watcher(cancel_event)
        self._run_delegation(text, step, command, reply_callback, cancel_event, job)

    def _start_hook_watcher(self, cancel_event: threading.Event) -> None:
        # Erlaubnis-Haken (S4b Scheibe 2, ADR-071): waehrend der Delegation
        # lauscht ein Watcher auf Hook-Anfragen und pusht sie aufs Handy.
        # Daemon + an die Lauf-Dauer gebunden; ohne Haken/Notifier passiert
        # nichts (Anfragen laufen dann in ihren Timeout = NEIN, fail-closed).
        if self._hook_enabled and self._notifier is not None:
            threading.Thread(
                target=self._watch_hook_requests, args=(cancel_event,),
                name="jarvis-hook-watch", daemon=True,
            ).start()

    def _action_state_block(self) -> str:
        """Der ECHTE Aktions-Zustand fuer den Antwort-Kontext (UX-S4): frischer
        Start, laufende Delegation, letzte ausgefuehrte Aktionen - plus die
        Regel, Aktionszustaende NIE zu erfinden (DNA-Ehrlichkeit; PO-Befund
        13.07.: erfundenes 'kein Neustart'). Fail-safe ''."""
        try:
            lines: list[str] = []
            up = time.monotonic() - self._started_monotonic
            if up < 180:
                lines.append(
                    f"- Jarvis ist vor {int(up)} Sekunden (neu) gestartet - eine zuvor "
                    "zugesagte Aktion (z. B. ein Neustart) IST demnach passiert und "
                    "laesst sich nicht mehr abbrechen."
                )
            with self._state_lock:
                active = self._delegation_active
            if active:
                lines.append(
                    "- GERADE LAEUFT eine Delegation (Bau/Analyse) im Hintergrund - "
                    "stoppbar mit «stopp den Agenten»."
                )
            now = time.monotonic()
            for intent, ok, ts in list(self._recent_actions):
                lines.append(
                    f"- vor {int(now - ts)} Sekunden ausgefuehrt: {intent} "
                    f"({'ok' if ok else 'fehlgeschlagen'})"
                )
            if not lines:
                return ""
            return (
                "AKTIONS-ZUSTAND (Fakten - stuetze JEDE Aussage ueber Aktionen NUR "
                "hierauf und auf den Verlauf; behaupte NIE, eine Aktion sei "
                "abgebrochen oder nicht passiert, wenn sie hier oder im Verlauf als "
                "ausgefuehrt/zugesagt steht):\n" + "\n".join(lines)
            )
        except Exception:  # noqa: BLE001 - der Zustand stoert den Live-Pfad nie
            return ""

    def _permission_question(self, command: str) -> str:
        """Baut die Erlaubnis-Frage VERSTAENDLICH (PO-Live-Befund 13.07.: die
        rohe Shell-Zeile war 'Kauderwelsch'): ein Klartext-Satz (guenstiges
        LLM, fail-safe ohne), eine deterministische Risiko-Einordnung
        (core/hook_gate.classify_command) und der rohe Befehl als 'Technisch:'
        darunter (Transparenz - nie verstecken, was wirklich laeuft)."""
        _, einordnung = classify_command(command)
        explanation = ""
        try:
            generate = getattr(self.ai, "generate", None)
            if callable(generate):
                explanation = (generate(
                    "Erklaere einem Menschen OHNE Programmierkenntnisse in EINEM "
                    "kurzen deutschen Satz, was dieser Shell-Befehl tut. Keine "
                    "Fachbegriffe, keine Bewertung, nur die Wirkung.",
                    command, model=self._compose_model) or "").strip()
        except Exception:  # noqa: BLE001 - ohne LLM bleibt die Einordnung
            explanation = ""
        lines = ["🔐 Der Bau-Agent bittet um Erlaubnis."]
        if explanation:
            lines.append(f"Was er tun will: {explanation}")
        lines.append(f"Einordnung: {einordnung}")
        lines.append(f"Technisch: «{command}»")
        lines.append("Erlauben? (ja/nein — ohne Antwort lehne ich ab)")
        return "\n".join(lines)

    def _watch_hook_requests(self, cancel_event: threading.Event) -> None:
        """Poll-Schleife (1,5 s) fuer die Dauer EINER Delegation: neue Hook-
        Anfrage -> Frage aufs Handy + als schwebendes ja/nein-Angebot armieren
        (genau EINE offene Frage zugleich; der Hook wartet derweil und laeuft
        sonst in seinen Timeout = NEIN). Fail-safe."""
        try:
            while True:
                with self._state_lock:
                    active = self._delegation_active
                if not active or cancel_event.is_set():
                    return
                if self._permission_offer is None:
                    for req in self._hook_mailbox.pending():
                        req_id = str(req.get("id"))
                        if req_id in self._hook_seen:
                            continue
                        self._hook_seen.add(req_id)
                        command = redact(str(req.get("command") or ""))[:300]
                        deadline = time.monotonic() + _HOOK_ANSWER_SECONDS
                        # Frage-Kanal ist der Notifier (Telegram); geantwortet
                        # werden darf aber aus JEDEM Kanal des Besitzers (PO-
                        # Live-Befund 13.07.: er antwortete zuerst am Desktop).
                        self._permission_offer = ("telegram", req_id, deadline)
                        try:
                            self._notifier(self._permission_question(command))
                        except Exception:  # noqa: BLE001
                            logger.exception("Erlaubnis-Frage-Push fehlgeschlagen.")
                        break
                elif self._permission_offer[2] < time.monotonic():
                    self._permission_offer = None      # abgelaufen -> naechste Frage
                time.sleep(1.5)
        except Exception:  # noqa: BLE001 - der Watcher stoert den Bau nie
            logger.exception("Hook-Watcher fehlgeschlagen.")

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


def _git_head(repo) -> str:
    """Aktueller Commit-Hash des Repos ('' bei Fehler/kein git). Fuer den
    Neue-Version-Hinweis (Spektakulaer #5): laeuft versteckt, fail-safe."""
    try:
        import subprocess
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


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


def _terminate_running_dashboards(timeout: float = 5.0) -> None:
    """Beendet laufende dashboard.py-Prozesse und WARTET, bis sie wirklich
    tot sind, bevor der Aufrufer einen neuen startet.

    Live-Bug 2026-07-11: bei JEDEM Neustart blieb ein Doppelgaenger mit
    altem Code zurueck. Ursache war eine Race - terminate() signalisiert nur
    asynchron, der neue Prozess startete sofort und scheiterte am noch
    belegten Dashboard-Port (bind() -> OSError, stiller Tod), waehrend der
    alte Zombie unveraendert weiterserierte. wait_procs schliesst das Fenster:
    erst terminate, warten, hartes kill fuer Nachzuegler, dann ist der Port
    frei. Fail-safe: ohne psutil (optional) wird nur geloggt."""
    try:
        import psutil
    except Exception:  # noqa: BLE001 - psutil optional, Abloesung ist Beiwerk
        logger.warning("Dashboard-Abloesung: psutil fehlt, alte Prozesse bleiben.", exc_info=True)
        return

    victims = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if "dashboard.py" in cmdline:
                proc.terminate()
                victims.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception:  # noqa: BLE001 - ein sperriger Prozess darf die Runde nicht kippen
            continue
    if not victims:
        return

    _gone, alive = psutil.wait_procs(victims, timeout=timeout)
    for proc in alive:
        try:
            proc.kill()  # terminate verpufft -> hart nachsetzen, sonst haelt er den Port
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if alive:
        psutil.wait_procs(alive, timeout=timeout)


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
        _terminate_running_dashboards()
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

    # Gesprochene Erinnerungen (PO-Reibung 13.07. "Mit Sprache"): der Scheduler
    # spricht faellige Erinnerungen ueber DENSELBEN speak()-Weg, wenn
    # reminder_speech_enabled gesetzt ist.
    runtime.set_voice_notifier(speak)

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
        followup_seconds=getattr(config, "voice_followup_seconds", 3.5),
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
