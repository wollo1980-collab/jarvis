"""
Telegram-Fernzugriff (v0.6 Phase 1, ADR-018). Separater Einstiegspunkt -
main.py bleibt für die lokale Konsole komplett unverändert.

Long-Polling über python-telegram-bot (kein Webhook/FastAPI/ngrok -
Wolfgangs Entscheidung: einfacher, kein öffentlich erreichbarer Server,
passend für einen privaten Start).

Sicherheitsmodell (Phase 1, Wolfgangs Entscheidungen):
- Nur eine einzige, per Umgebungsvariable JARVIS_TELEGRAM_ALLOWED_CHAT_ID
  autorisierte Chat-ID wird verarbeitet - alle anderen werden stillschweigend
  ignoriert (kein Fehler, kein Hinweis nach außen).
- Nur eine feste Intent-Whitelist (chat, remember_fact, forget_fact,
  system_status, search_web) ist über Telegram erreichbar - Excel/Reports/KPI/
  install_program/shutdown_pc sind in Phase 1 NICHT erreichbar.
- Zusätzliche, von der Whitelist unabhängige Sicherung: jeder Intent,
  dessen Command requires_confirmation=True setzt (Sicherheitsstufe 2/3),
  wird ebenfalls abgelehnt - auch falls die Whitelist später versehentlich
  erweitert würde.
- Enthält ein Mehrschritt-Plan auch nur einen nicht erlaubten Schritt,
  wird der GESAMTE Plan abgelehnt (keine Teilausführung über einen
  Textkanal ohne Rückfragemöglichkeit).
- Bot-Token und Chat-ID ausschließlich über Umgebungsvariablen, niemals
  in config.json oder Git.

Bewusst KEINE Änderung an core/ai.py, core/planner.py,
core/tool_manager.py, executor/executor.py, main.py oder commands/*.py -
die Beschränkungen leben ausschließlich in diesem Modul.

Kein gleichzeitiger Betrieb von Konsole und Telegram in Phase 1
(Wolfgangs Entscheidung) - beide teilen sich dieselben memory_data/-
Dateien, aber es läuft jeweils nur einer der beiden Kanäle.
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Optional

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

import commands.mail as mail_commands
import commands.memory as memory_commands
import commands.web as web_commands
from commands import REGISTRY
from core.ai import AIEngine
from core.config import Config
from core.models import Message, Plan
from core.planner import Planner
from core.single_instance import InstanceAlreadyRunningError, SingleInstanceLock
from executor.executor import Executor
from memory.long_term import LongTermMemory
from memory.store import JsonMemoryStore

logger = logging.getLogger("jarvis.telegram")

BOT_TOKEN_ENV = "JARVIS_TELEGRAM_BOT_TOKEN"
ALLOWED_CHAT_ID_ENV = "JARVIS_TELEGRAM_ALLOWED_CHAT_ID"

# Telegram bleibt bewusst eng freigeschaltet: nur sichere, bestaetigungsfreie
# Alltags-Intents. Web v1 ist read-only und passt deshalb in dieselbe Whitelist.
# Das Mail-Briefing (check_mail/show_mail_advertising) ist ebenfalls rein lesend
# (Sicherheitsstufe 0) und per PO-Entscheidung 2026-07-06 remote freigeschaltet
# (ADR-031-Nachtrag); die schreibenden Regel-Lern-Intents bleiben bewusst lokal.
ALLOWED_INTENTS = {
    "chat",
    "remember_fact",
    "forget_fact",
    # Sichtbares Gedaechtnis (Welle 1.3): rein lesend, Sicherheitsstufe 0 -
    # gehoert in dieselbe Klasse wie remember/forget/check_mail.
    "list_facts",
    "system_status",
    "search_web",
    "check_mail",
    "show_mail_advertising",
}


class TelegramSpeech:
    """say()/listen()-Adapter, damit Executor unverändert wiederverwendet
    werden kann (Kap. 31: Schnittstellenprinzip - Kanal austauschen, ohne
    den Executor anzufassen). Beide Methoden sollten in Phase 1 NIE
    aufgerufen werden, da nur bestätigungsfreie Intents (requires_confirmation
    = False) den Executor überhaupt erreichen - jede tatsächliche
    Ausführung fällt sicherheitshalber fail-closed aus und wird laut
    geloggt statt stillschweigend zu funktionieren."""

    def say(self, text: str) -> None:
        logger.error("TelegramSpeech.say() aufgerufen - unerwartet in Phase 1: %r", text)

    def listen(self) -> str:
        logger.error(
            "TelegramSpeech.listen() aufgerufen - unerwartet in Phase 1. "
            "Fail closed: keine Bestätigung."
        )
        return ""


def is_authorized(chat_id: object, allowed_chat_id: str) -> bool:
    """Vergleicht als String, um Telegrams int-Chat-ID nicht versehentlich
    typfehleranfällig gegen die string-Umgebungsvariable zu vergleichen."""
    return str(chat_id) == str(allowed_chat_id)


def rejection_reason(step: Plan, allowed: Optional[set] = None) -> Optional[str]:
    """Liefert einen Ablehnungsgrund, falls dieser Schritt per Telegram
    nicht erlaubt ist, sonst None.

    allowed (optional, ADR-035): erlaubte Intent-Menge. Default None ->
    Auflösung auf das Modul-Set ALLOWED_INTENTS ZUR AUFRUFZEIT (damit Tests
    ALLOWED_INTENTS weiterhin per monkeypatch ersetzen koennen). Der
    Runtime-Telegram-Kanal reicht ein erweitertes Set (inkl. delegate_analysis)
    durch, ohne das Standalone-Verhalten zu aendern."""
    allowed_intents = ALLOWED_INTENTS if allowed is None else allowed
    if step.intent not in allowed_intents:
        return f"'{step.intent}' ist per Telegram (Phase 1) nicht verfügbar."

    command = REGISTRY.get(step.intent)
    if command is not None and getattr(command, "requires_confirmation", False):
        return (
            f"'{step.intent}' erfordert eine Bestätigung (Sicherheitsstufe 2/3) "
            "- per Telegram nicht erlaubt."
        )
    return None


def filter_plan(
    steps: list[Plan], allowed: Optional[set] = None
) -> tuple[list[Plan], Optional[str]]:
    """Prüft alle Schritte eines Plans. Ist auch nur einer nicht erlaubt,
    wird der GESAMTE Plan abgelehnt (Wolfgangs Entscheidung) - liefert
    ([], Ablehnungsgrund). Sind alle Schritte erlaubt, liefert (steps, None).

    allowed (optional, ADR-035) wird an rejection_reason durchgereicht;
    Default None -> Modul-ALLOWED_INTENTS (Standalone-Verhalten unveraendert)."""
    for step in steps:
        reason = rejection_reason(step, allowed)
        if reason:
            return [], f"Anfrage abgelehnt: {reason}"
    return steps, None


def setup_logging(config: Config) -> None:
    log_file = config.log_dir / f"{date.today().isoformat()}-telegram.log"
    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
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


class JarvisBridge:
    """Verdrahtet dieselbe Pipeline wie main.py (Config/AIEngine/Planner/
    Executor/Memory), aber mit Telegram statt Konsole als Kanal. `ai`
    ist injizierbar, damit Tests ohne echten API-Key/Netzwerk laufen
    (gleiches Muster wie tests/test_integration.py::FakeAI)."""

    def __init__(self, config: Config, allowed_chat_id: str, ai: Optional[AIEngine] = None):
        self.allowed_chat_id = allowed_chat_id
        self.ai = ai if ai is not None else AIEngine(config)
        self.planner = Planner(self.ai)
        self.executor = Executor(TelegramSpeech(), self.ai)
        self.memory = JsonMemoryStore(config.memory_dir, config.max_history_entries)
        self.long_term = LongTermMemory(config.memory_dir)
        memory_commands.configure(config.memory_dir)
        web_commands.configure(self.ai, timeout_seconds=config.timeout)
        mail_commands.configure(config)

    def handle_message(self, chat_id: object, user_input: str) -> str:
        """Verarbeitet eine eingehende Nachricht, gibt den Antworttext
        zurück (leerer String = nichts antworten, z. B. bei nicht
        autorisiertem Chat)."""
        if not is_authorized(chat_id, self.allowed_chat_id):
            logger.warning("Nicht autorisierter Chat %s - Nachricht ignoriert.", chat_id)
            return ""

        history = self.memory.get_history(limit=20)
        steps = self.planner.plan(user_input, history)

        allowed_steps, rejection = filter_plan(steps)
        if rejection:
            logger.info("Plan abgelehnt für Chat %s: %s", chat_id, rejection)
            return rejection

        long_term_summary = self.long_term.summary_text()
        report = self.executor.run(allowed_steps, history, long_term_summary)
        response_text = "\n".join(report.summary_lines()) or "Alles klar."

        self.memory.append_history(Message(role="user", content=user_input))
        self.memory.append_history(Message(role="assistant", content=response_text))
        return response_text


async def _on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bridge: JarvisBridge = context.application.bot_data["bridge"]
    if update.effective_chat is None or update.message is None or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user_input = update.message.text

    response_text = bridge.handle_message(chat_id, user_input)
    if response_text:
        await context.bot.send_message(chat_id=chat_id, text=response_text)


def main() -> None:
    config = Config.load()
    setup_logging(config)
    logger_main = logging.getLogger("jarvis.telegram.main")

    # Single-Instance-Schutz (ADR-026): allererste Aktion, vor jedem
    # Core-Stack-Aufbau - main.py, telegram_main.py und jarvis_runtime.py
    # teilen sich ohne besondere Konfiguration dasselbe memory_dir, das
    # keinerlei Locking hat.
    lock = SingleInstanceLock(config.memory_dir, entry_point="telegram_main.py")
    try:
        lock.acquire()
    except InstanceAlreadyRunningError as e:
        raise SystemExit(f"Jarvis konnte nicht gestartet werden: {e}")

    try:
        try:
            bot_token = os.environ[BOT_TOKEN_ENV]
            allowed_chat_id = os.environ[ALLOWED_CHAT_ID_ENV]
        except KeyError as e:
            raise SystemExit(
                f"Umgebungsvariable {e.args[0]} fehlt - {BOT_TOKEN_ENV} und "
                f"{ALLOWED_CHAT_ID_ENV} müssen gesetzt sein (siehe README "
                "Abschnitt 'Telegram-Fernzugriff')."
            )

        bridge = JarvisBridge(config, allowed_chat_id)

        application = Application.builder().token(bot_token).build()
        application.bot_data["bridge"] = bridge
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_message))

        logger_main.info("Telegram-Bot gestartet (Long-Polling, Phase 1).")
        application.run_polling()
    finally:
        lock.release()


if __name__ == "__main__":
    main()
