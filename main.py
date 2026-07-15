"""
Einstiegspunkt. Verbindet Speech, Planner, Executor und Memory zu der
Request-Pipeline: Eingabe -> Planner zerlegt in Schritte -> Executor
löst pro Schritt ein Tool über den Tool Manager auf und führt es aus
(oder holt bei chat-Intent eine echte Antwort von der KI) -> Report
-> Antwort ausgeben -> Memory speichern.

Kein Wake-Word/Mikrofon in v0.2/v0.3 - Konsolen-I/O reicht, um die
Pipeline End-to-End zu testen. Keine Business-Logik hier: main.py
verdrahtet nur, die eigentliche Arbeit passiert in den Modulen.
"""
from __future__ import annotations

import logging
import sys
from datetime import date

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
import commands.news as news_commands
import commands.owner as owner_commands
import commands.weather as weather_commands
import commands.spotify as spotify_commands
import commands.plan as plan_commands
import commands.project as project_commands
import commands.monitor as monitor_commands
import commands.web as web_commands
from core.agent_backend import ClaudeCodeBackend
from core.ai import AIEngine
from core.config import Config
from core.models import Message
from core.planner import Planner
from core.single_instance import InstanceAlreadyRunningError, SingleInstanceLock
from core.speech import SpeechEngine
from executor.executor import Executor
from memory.long_term import LongTermMemory
from memory.store import JsonMemoryStore

# Woerter, die das Programm beenden - werden VOR dem Planner geprueft,
# damit sie niemals von der KI als Systembefehl (miss-)interpretiert
# werden koennen.
EXIT_WORDS = {"exit", "quit", "beenden", "ende", "stop", "stopp", "tschuess", "tschüss", "bye"}


def setup_logging(config: Config) -> None:
    log_file = config.log_dir / f"{date.today().isoformat()}.log"
    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
    )


def make_console_output_safe() -> None:
    """Konsolenausgabe gegen nicht kodierbare Zeichen haerten.

    Antworttexte enthalten Zeichen wie das Executor-Haekchen (U+2713), die
    eine cp1252-Konsole nicht kodieren kann - ohne diese Haertung stirbt
    main.py mitten in der Antwort an einem UnicodeEncodeError (Live-Fund
    Nutzwert-Phase, 2026-07-06). Nicht darstellbare Zeichen werden ersetzt
    statt zu crashen; an UTF-8-Konsolen aendert sich nichts.
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def main() -> None:
    make_console_output_safe()
    config = Config.load()
    setup_logging(config)
    logger = logging.getLogger("jarvis.main")

    # Single-Instance-Schutz (ADR-026): allererste Aktion, vor jedem
    # Core-Stack-Aufbau - main.py, telegram_main.py und jarvis_runtime.py
    # teilen sich ohne besondere Konfiguration dasselbe memory_dir, das
    # keinerlei Locking hat.
    lock = SingleInstanceLock(config.memory_dir, entry_point="main.py")
    try:
        lock.acquire()
    except InstanceAlreadyRunningError as e:
        logger.error("Start abgebrochen: %s", e)
        print(f"Jarvis konnte nicht gestartet werden: {e}")
        return

    try:
        speech = SpeechEngine(config)
        ai = AIEngine(config)
        planner = Planner(ai)
        executor = Executor(speech, ai)
        memory = JsonMemoryStore(config.memory_dir, config.max_history_entries)

        # Langzeitgedächtnis (v0.4, ADR-009): eigener Store neben dem
        # Gesprächsverlauf, siehe memory/long_term.py. configure() macht
        # dieselbe Instanz auch für remember_fact/forget_fact verfügbar
        # (Commands werden bereits beim Modul-Import instanziiert, bevor
        # config.memory_dir bekannt ist - deshalb dieser Umweg statt
        # Konstruktor-Injection).
        long_term = LongTermMemory(config.memory_dir)
        memory_commands.configure(config.memory_dir)
        # Anzeigename auf Zuruf (ADR-057): dasselbe Config-Objekt wie die
        # AIEngine oben (Chat folgt live) + long_term fuer die Fakten-Raeumung.
        owner_commands.configure(config, long_term)
        # Eintraege (A1): eigener Store neben dem Langzeitgedaechtnis.
        entry_store = entries_commands.configure(config.memory_dir)
        list_store = lists_commands.configure(config.memory_dir)
        briefing_commands.configure(
            entry_store, list_store,
            config.weather_default_location, config.news_feeds, config.timeout,
        )
        from memory.habits import HabitStats

        ideas_commands.configure(ai, HabitStats(config.memory_dir), entry_store, list_store)
        from core.config import BASE_DIR as _base_dir

        review_commands.configure(_base_dir / "docs" / "CHANGELOG.md", config.log_dir)
        # Impuls-Kreislauf (ADR-054): der ✕-Befehl braucht den Store auch in
        # der Konsolen-Verdrahtung (die Engine selbst laeuft nur in der Runtime).
        from memory.impulses import ImpulseStore

        impulses_commands.configure(ImpulseStore(config.memory_dir))
        # News-Briefing (ADR-042): RSS-Feeds aus der Config.
        news_commands.configure(config.news_feeds, timeout_seconds=config.timeout)
        # Wetter (ADR-043): Standard-Ort aus der Config.
        weather_commands.configure(config.weather_default_location, timeout_seconds=config.timeout)
        # Spotify (ADR-058): Client aus der Config, fehlende Credentials = aus.
        spotify_commands.configure(config)
        # Projektstart (ADR-049): Pfade aus der Config, leer = aus.
        project_commands.configure(config.projects_root, config.framework_repo)

        # PC-Analyse (v0.7 Phase 1, ADR-020): analyze_pc ruft direkt die KI
        # auf - die AIEngine-Instanz wird hier injiziert (Registry
        # instanziiert Commands vor diesem Punkt).
        monitor_commands.configure(ai)

        # Mail-Briefing (Nutzwert-Phase, ADR-031): baut die Postfächer aus
        # config.mail_accounts + Env-Passwörtern und den lokalen Regel-Speicher.
        mail_commands.configure(config)
        web_commands.configure(ai, timeout_seconds=config.timeout)

        # Agenten-Delegation (ADR-034): read-only Repo-Analyse. Backend hier in
        # der Verdrahtungsschicht gewählt und injiziert - die Fachlogik
        # (commands/delegate.py) nennt bewusst kein Backend (ADR-036).
        # ai fuer project_continue: baut den Fortsetzungs-Auftrag per LLM.
        delegate_commands.configure(config, ClaudeCodeBackend(), ai=ai)

        # Nächsten Schritt planen (erste Orchestrierungs-Kette, ADR-036 /
        # Handbook 4.2). Das Backend wird hier in der Verdrahtungsschicht
        # gewählt und injiziert - die Fachlogik (commands/plan.py) nennt
        # bewusst kein konkretes Backend (Modellunabhängigkeit).
        plan_commands.configure(config, ClaudeCodeBackend())
        # Selbstkontrolle Stufe 3 (ADR-055): Verifikations-Harnisch.
        verify_commands.configure(config)

        logger.info("Jarvis v0.4 gestartet.")
        speech.say("Jarvis ist bereit.")

        while True:
            user_input = speech.listen()
            # Abschiedsworte werden VOR dem Planner abgefangen - sie duerfen
            # niemals erst an die KI/den Executor gehen (siehe Logbook
            # 2026-07-01: "Ende" wurde faelschlich als shutdown_pc erkannt).
            if user_input.lower().strip() in EXIT_WORDS:
                break

            logger.info("User: %s", user_input)
            history = memory.get_history(limit=20)

            steps = planner.plan(user_input, history)
            for step in steps:
                logger.info(
                    "Plan: intent=%s target=%s confidence=%.2f",
                    step.intent,
                    step.target,
                    step.confidence,
                )

            long_term_summary = long_term.summary_text()
            report = executor.run(steps, history, long_term_summary)
            response_text = "\n".join(report.summary_lines()) or "Alles klar."

            speech.say(response_text)

            memory.append_history(Message(role="user", content=user_input))
            memory.append_history(Message(role="assistant", content=response_text))

            if not report.all_ok:
                logger.warning("Nicht alle Schritte erfolgreich.")
    finally:
        lock.release()


if __name__ == "__main__":
    main()
