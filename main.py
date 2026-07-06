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
from datetime import date

import commands.mail as mail_commands
import commands.memory as memory_commands
import commands.monitor as monitor_commands
import commands.reports as reports_commands
import commands.web as web_commands
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


def main() -> None:
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

        # Tabellen-Auswertung (v0.5, ADR-015): analyze_report ruft als
        # erster Command direkt die KI auf - dieselbe AIEngine-Instanz wird
        # hier injiziert (Registry instanziiert Commands vor diesem Punkt).
        reports_commands.configure(ai)

        # PC-Analyse (v0.7 Phase 1, ADR-020): analyze_pc ruft ebenfalls
        # direkt die KI auf - eigenes, zu reports_commands bewusst
        # dupliziertes configure()-Muster (siehe ADR-020).
        monitor_commands.configure(ai)

        # Mail-Briefing (Nutzwert-Phase, ADR-031): baut die Postfächer aus
        # config.mail_accounts + Env-Passwörtern und den lokalen Regel-Speicher.
        mail_commands.configure(config)
        web_commands.configure(ai, timeout_seconds=config.timeout)

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
