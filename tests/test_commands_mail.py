"""Tests für commands/mail.py + memory/mail_rules.py (ADR-031).

Kein echtes Postfach: der IMAP-Reader wird über configure(config, reader=...)
durch einen Fake ersetzt. Prüft Regel-Vorrang, Werbung-Zusammenfalten, das
gelernte Korrigieren und fail-safe bei Kontofehlern."""
from __future__ import annotations

import pytest

import commands.mail as mail
from core.config import Config
from core.mail_reader import MailAccount, MailHeader
from core.models import Plan, Status
from memory.mail_rules import MailRules


def _hdr(sender_display, subject, sender=None, list_unsubscribe="", precedence=""):
    return MailHeader(
        account="Gmail",
        sender=sender or f"{sender_display} <x@example.com>",
        sender_display=sender_display,
        subject=subject,
        date="",
        list_unsubscribe=list_unsubscribe,
        precedence=precedence,
    )


def _config(tmp_path, monkeypatch, with_account=True):
    accounts = []
    if with_account:
        monkeypatch.setenv("JARVIS_TEST_MAIL_PW", "secret")
        accounts = [{
            "label": "Gmail", "imap_host": "imap.gmail.com", "imap_port": 993,
            "username": "u@gmail.com", "password_env": "JARVIS_TEST_MAIL_PW",
        }]
    return Config(memory_dir=tmp_path, mail_accounts=accounts)


# --- MailRules ------------------------------------------------------------

def test_rules_hide_keep_and_precedence(tmp_path):
    r = MailRules(tmp_path)
    assert r.classify("Amazon <x@amazon.de>") is None
    r.hide("amazon")
    assert r.classify("Amazon.de <versand@amazon.de>") == "hide"
    # keep gewinnt vor hide (im Zweifel zeigen):
    r.hide("newsletter")
    r.keep("chef")
    assert r.classify("Chef Newsletter <chef@firma.de>") == "keep"


def test_keep_removes_from_hide(tmp_path):
    r = MailRules(tmp_path)
    r.hide("amazon")
    r.keep("amazon")
    assert r.classify("Amazon <x@amazon.de>") == "keep"
    assert "amazon" not in r.all_rules()["hide"]


def test_empty_pattern_is_ignored(tmp_path):
    r = MailRules(tmp_path)
    assert r.hide("   ") is False
    assert r.all_rules() == {"hide": [], "keep": []}


# --- Klassifikation: Regel schlägt Heuristik ------------------------------

def test_learned_rule_overrides_heuristic(tmp_path, monkeypatch):
    mail.configure(_config(tmp_path, monkeypatch), reader=lambda a: [])
    mail._require_configured().keep("wichtig")
    mail._require_configured().hide("kollege")

    ad_but_kept = _hdr("Wichtig AG", "Angebot", list_unsubscribe="<mailto:x>")   # wäre Werbung
    personal_but_hidden = _hdr("Kollege", "Hi")                                  # wäre relevant
    relevant, ads = mail._classify([ad_but_kept, personal_but_hidden])

    assert ad_but_kept in relevant       # keep-Regel überstimmt List-Unsubscribe
    assert personal_but_hidden in ads    # hide-Regel überstimmt "kein Werbesignal"


# --- Briefing-Text --------------------------------------------------------

def test_briefing_collapses_advertising(tmp_path, monkeypatch):
    mail.configure(_config(tmp_path, monkeypatch), reader=lambda a: [])
    relevant = [_hdr("PayPal", "Zahlung erhalten")]
    ads = [_hdr("Shop", "Sale"), _hdr("News", "Wochenrückblick")]
    text = mail._briefing(relevant, ads, [], show_ads=False)
    assert "PayPal: Zahlung erhalten" in text
    assert "2 Werbe-/Newsletter-Mail(s) ausgeblendet" in text
    assert "Sale" not in text  # zusammengefaltet, nicht gelistet


def test_briefing_show_ads_lists_them(tmp_path, monkeypatch):
    mail.configure(_config(tmp_path, monkeypatch), reader=lambda a: [])
    text = mail._briefing([], [_hdr("Shop", "Sale")], [], show_ads=True)
    assert "Sale" in text


def test_briefing_quiet_when_nothing(tmp_path, monkeypatch):
    mail.configure(_config(tmp_path, monkeypatch), reader=lambda a: [])
    assert "ruhig" in mail._briefing([], [], [], show_ads=False)


# --- CheckMailCommand -----------------------------------------------------

def test_check_mail_briefs_and_hides_ads(tmp_path, monkeypatch):
    inbox = [
        _hdr("Chef", "Bitte anrufen"),
        _hdr("Shop", "Mega Sale", list_unsubscribe="<mailto:x>"),
    ]
    mail.configure(_config(tmp_path, monkeypatch), reader=lambda a: list(inbox))

    result = mail.CheckMailCommand().execute(Plan(intent="check_mail"))
    assert result.status == Status.SUCCESS
    assert "Chef: Bitte anrufen" in result.message
    assert "1 Werbe-/Newsletter-Mail(s) ausgeblendet" in result.message


def test_check_mail_without_account_asks_to_configure(tmp_path, monkeypatch):
    mail.configure(_config(tmp_path, monkeypatch, with_account=False), reader=lambda a: [])
    result = mail.CheckMailCommand().execute(Plan(intent="check_mail"))
    assert result.status == Status.NEEDS_CLARIFICATION
    assert "kein Mail-Konto" in result.message


def test_account_error_is_fail_safe(tmp_path, monkeypatch):
    def boom(account):
        raise ConnectionError("timeout")

    mail.configure(_config(tmp_path, monkeypatch), reader=boom)
    result = mail.CheckMailCommand().execute(Plan(intent="check_mail"))
    # Kein Absturz - Briefing kommt trotzdem, mit Hinweis.
    assert result.status == Status.SUCCESS
    assert "nicht erreichbar" in result.message


# --- Korrektur-Commands (das „Lernen") ------------------------------------

def test_hide_sender_command_persists_rule(tmp_path, monkeypatch):
    mail.configure(_config(tmp_path, monkeypatch), reader=lambda a: [])
    result = mail.MailHideSenderCommand().execute(Plan(intent="mail_hide_sender", target="Amazon"))
    assert result.status == Status.SUCCESS
    assert mail._require_configured().classify("Amazon <x@amazon.de>") == "hide"


def test_keep_sender_command_persists_rule(tmp_path, monkeypatch):
    mail.configure(_config(tmp_path, monkeypatch), reader=lambda a: [])
    result = mail.MailKeepSenderCommand().execute(Plan(intent="mail_keep_sender", target="Stepstone"))
    assert result.status == Status.SUCCESS
    assert mail._require_configured().classify("Stepstone <jobs@stepstone.de>") == "keep"


def test_hide_sender_without_target_asks_back(tmp_path, monkeypatch):
    mail.configure(_config(tmp_path, monkeypatch), reader=lambda a: [])
    result = mail.MailHideSenderCommand().execute(Plan(intent="mail_hide_sender", target=None))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_not_configured_raises(monkeypatch):
    monkeypatch.setattr(mail, "_rules", None)
    with pytest.raises(RuntimeError):
        mail.CheckMailCommand().execute(Plan(intent="check_mail"))
