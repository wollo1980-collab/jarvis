"""Tests für telegram_main.py (v0.6 Phase 1, ADR-018). Kein echter
Bot-Token, kein Netzwerk, keine echte python-telegram-bot-Application -
nur die Sicherheits-/Filterlogik und JarvisBridge werden getestet."""
from __future__ import annotations

import logging
from pathlib import Path

import commands.web as web_commands
import telegram_main
from core.config import Config
from core.models import Message, Plan
from core.web_search import SearchResult
from telegram_main import (
    ALLOWED_INTENTS,
    JarvisBridge,
    TelegramSpeech,
    filter_plan,
    is_authorized,
    rejection_reason,
)


def test_dampen_http_loggers_protects_token_by_setting_warning():
    """Sicherheit: httpx/httpcore loggen sonst den Telegram-Request-URL
    inkl. Bot-Token auf INFO - _dampen_http_loggers() hebt sie auf WARNING,
    damit der Token nie in Logdatei/Konsole landet."""
    loggers = [logging.getLogger("httpx"), logging.getLogger("httpcore")]
    orig = [lg.level for lg in loggers]
    try:
        for lg in loggers:
            lg.setLevel(logging.INFO)
        telegram_main._dampen_http_loggers()
        assert all(lg.level == logging.WARNING for lg in loggers)
    finally:
        for lg, lvl in zip(loggers, orig):
            lg.setLevel(lvl)


class FakeAI:
    """Ersetzt AIEngine 1:1 (gleiche öffentliche Methoden wie
    tests/test_integration.py::FakeAI) - kein echter API-Key nötig."""

    def get_plan(self, user_input: str, history: list[Message]) -> Plan:
        text = user_input.lower()
        if "installier" in text:
            return Plan(intent="install_program", target="vlc", raw_input=user_input, confidence=1.0)
        if "shutdown" in text or "herunter" in text:
            return Plan(intent="shutdown_pc", raw_input=user_input, confidence=1.0)
        if "excel" in text and "lies" in text:
            return Plan(intent="read_excel", target="a.xlsx", raw_input=user_input, confidence=1.0)
        if text.startswith("merk dir"):
            fact = user_input.split(",", 1)[-1].strip()
            return Plan(
                intent="remember_fact",
                target=fact,
                parameters={"category": "gewohnheit"},
                raw_input=user_input,
                confidence=1.0,
            )
        if "web" in text or "internet" in text or "recherch" in text:
            return Plan(
                intent="search_web",
                target="aktuelle KI Nachrichten",
                raw_input=user_input,
                confidence=1.0,
            )
        if "auslastung" in text:
            return Plan(intent="system_status", raw_input=user_input, confidence=1.0)
        return Plan(intent="chat", raw_input=user_input, confidence=1.0)

    def answer(self, user_input: str, history: list[Message], long_term_summary: str = "") -> str:
        return "Alles klar."


def _make_bridge(tmp_path: Path, allowed_chat_id: str = "12345") -> JarvisBridge:
    config = Config(memory_dir=tmp_path)
    return JarvisBridge(config, allowed_chat_id, ai=FakeAI())


# --- is_authorized ---------------------------------------------------


def test_is_authorized_accepts_matching_chat_id():
    assert is_authorized(12345, "12345") is True


def test_is_authorized_rejects_wrong_chat_id():
    assert is_authorized(99999, "12345") is False


def test_is_authorized_compares_as_string():
    # Telegram liefert chat_id als int, die Env-Var ist ein String.
    assert is_authorized(12345, "12345") is True
    assert is_authorized("12345", "12345") is True


# --- rejection_reason --------------------------------------------------


def test_rejection_reason_allows_whitelisted_intents():
    for intent in ALLOWED_INTENTS:
        assert rejection_reason(Plan(intent=intent)) is None


def test_rejection_reason_blocks_non_whitelisted_intent():
    reason = rejection_reason(Plan(intent="read_excel", target="a.xlsx"))
    assert reason is not None
    assert "read_excel" in reason


def test_delegate_analysis_rejected_on_standalone_bot():
    # ADR-035: die asynchrone Repo-Analyse ist NUR ueber den Runtime-Kanal
    # erreichbar (der hat den Hintergrund-Worker). Der aeltere synchrone
    # Standalone-Bot (telegram_main.py) hat keinen Async-Worker und wuerde bei
    # einer Minuten-Analyse den Event-Loop blockieren - deshalb bleibt
    # delegate_analysis hier bewusst NICHT in der Whitelist.
    assert "delegate_analysis" not in ALLOWED_INTENTS
    reason = rejection_reason(Plan(intent="delegate_analysis", target="jarvis"))
    assert reason is not None
    assert "delegate_analysis" in reason


def test_plan_next_step_rejected_on_standalone_bot():
    # Wie delegate_analysis: die langlaufende Planungs-Faehigkeit ist nur ueber
    # den Runtime-Kanal (Async-Worker) erreichbar, nicht ueber den synchronen
    # Standalone-Bot.
    assert "plan_next_step" not in ALLOWED_INTENTS
    reason = rejection_reason(Plan(intent="plan_next_step"))
    assert reason is not None
    assert "plan_next_step" in reason


def test_filter_plan_allowed_override_lets_intent_through():
    # ADR-035: filter_plan/rejection_reason akzeptieren ein erweitertes Set;
    # damit schaltet der Runtime-Kanal delegate_analysis gezielt frei, ohne das
    # Standalone-Verhalten (Default-Set) zu aendern.
    extended = ALLOWED_INTENTS | {"delegate_analysis"}
    assert rejection_reason(Plan(intent="delegate_analysis", target="jarvis"), extended) is None
    steps, rejection = filter_plan([Plan(intent="delegate_analysis", target="jarvis")], extended)
    assert rejection is None
    assert len(steps) == 1


def test_mail_briefing_intents_are_whitelisted():
    # PO-Entscheidung 2026-07-06 (ADR-031-Nachtrag): das rein lesende
    # Mail-Briefing ist remote erreichbar.
    assert rejection_reason(Plan(intent="check_mail")) is None
    assert rejection_reason(Plan(intent="show_mail_advertising")) is None


def test_mail_rule_writing_intents_stay_local():
    # Bewusste Scope-Grenze: die schreibenden Regel-Lern-Intents bleiben
    # der lokalen Konsole vorbehalten (kein reines Lesen mehr).
    for intent in ("mail_hide_sender", "mail_keep_sender"):
        reason = rejection_reason(Plan(intent=intent, target="amazon"))
        assert reason is not None
        assert intent in reason


def test_bridge_configures_mail(tmp_path: Path, monkeypatch):
    # Regressionsanker: das Mail-Briefing muss im Telegram-Pfad konfiguriert
    # werden (fehlte urspruenglich - Whitelist allein liefe sonst ins Leere).
    calls = []
    monkeypatch.setattr(
        telegram_main.mail_commands, "configure", lambda config: calls.append(config)
    )
    _make_bridge(tmp_path)
    assert len(calls) == 1


def test_rejection_reason_blocks_stufe2_even_if_hypothetically_whitelisted(monkeypatch):
    import telegram_main

    monkeypatch.setattr(telegram_main, "ALLOWED_INTENTS", {"install_program"})
    reason = telegram_main.rejection_reason(Plan(intent="install_program", target="vlc"))
    assert reason is not None
    assert "Bestätigung" in reason or "Sicherheitsstufe" in reason


def test_rejection_reason_blocks_shutdown_pc():
    reason = rejection_reason(Plan(intent="shutdown_pc"))
    assert reason is not None


# --- filter_plan ---------------------------------------------------------


def test_filter_plan_allows_all_when_all_steps_allowed():
    steps = [Plan(intent="chat"), Plan(intent="system_status")]
    allowed, rejection = filter_plan(steps)
    assert allowed == steps
    assert rejection is None


def test_filter_plan_rejects_whole_plan_if_any_step_disallowed():
    steps = [Plan(intent="remember_fact", target="x"), Plan(intent="install_program", target="vlc")]
    allowed, rejection = filter_plan(steps)
    assert allowed == []
    assert rejection is not None
    assert "install_program" in rejection


# --- TelegramSpeech (fail-closed) ---------------------------------------


def test_telegram_speech_listen_is_fail_closed():
    assert TelegramSpeech().listen() == ""


def test_telegram_speech_say_does_not_raise():
    TelegramSpeech().say("sollte nie passieren")


# --- JarvisBridge --------------------------------------------------------


def test_bridge_ignores_unauthorized_chat(tmp_path: Path):
    bridge = _make_bridge(tmp_path, allowed_chat_id="12345")
    response = bridge.handle_message(chat_id=99999, user_input="hallo")
    assert response == ""


def test_bridge_handles_chat_intent(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    response = bridge.handle_message(chat_id="12345", user_input="hallo jarvis")
    assert response == "Alles klar."


def test_bridge_handles_remember_fact(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    response = bridge.handle_message(
        chat_id="12345", user_input="merk dir, dass ich montags Reports mache"
    )
    assert "montags Reports" in response


def test_bridge_handles_search_web(tmp_path: Path, monkeypatch):
    bridge = _make_bridge(tmp_path)
    monkeypatch.setattr(
        web_commands,
        "_searcher",
        lambda query, max_results, timeout_seconds: [
            SearchResult(
                title="KI Nachrichten",
                url="https://example.com/ki",
                snippet="Die Lage ist ruhig, aber aktiv.",
            )
        ],
    )

    response = bridge.handle_message(chat_id="12345", user_input="suche im web nach ki")

    assert "Quellen:" in response
    assert "https://example.com/ki" in response


def test_bridge_rejects_forbidden_intent_without_executing(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    response = bridge.handle_message(chat_id="12345", user_input="installier vlc")
    assert "abgelehnt" in response.lower()
    assert "install_program" in response


def test_bridge_rejects_shutdown_pc(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    response = bridge.handle_message(chat_id="12345", user_input="fahr den rechner herunter")
    assert "abgelehnt" in response.lower()


def test_bridge_rejects_whole_multistep_plan_with_one_forbidden_step(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    response = bridge.handle_message(
        chat_id="12345",
        user_input="merk dir, dass ich Kaffee mag und installier vlc",
    )
    assert "abgelehnt" in response.lower()

    # Der erlaubte Teil (remember_fact) darf NICHT ausgefuehrt worden sein,
    # da der gesamte Plan verworfen wird (Wolfgangs Entscheidung).
    from memory.long_term import LongTermMemory

    facts = LongTermMemory(tmp_path).all_facts()
    assert facts == []


def test_bridge_persists_history(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    bridge.handle_message(chat_id="12345", user_input="hallo")
    history = bridge.memory.get_history()
    assert len(history) == 2  # user + assistant
