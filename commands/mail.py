"""
Mail-Briefing "Was liegt an?" (Nutzwert-Phase, erster externer Connector,
ADR-031).

Auf "Jarvis, was liegt an?" ruft Jarvis die konfigurierten Postfaecher
nur-lesend ab (core/mail_reader.py), sortiert Werbung/Newsletter per Heuristik
und gelernten Regeln (memory/mail_rules.py) aus und traegt den Rest knapp in
seiner Stimme vor. Werbung wird zusammengefaltet, nicht versteckt ("anzeigen?").
Reines Lesen (Sicherheitsstufe 0): kein Senden/Loeschen/Markieren; kein
Mailinhalt, nichts an eine KI.

configure()-Muster wie commands/memory.py (die Registry instanziiert Commands
vor Config.load()). Der IMAP-Reader ist injizierbar, damit Tests ohne echtes
Postfach/imaplib laufen.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from core.mail_reader import MailAccount, MailHeader, fetch_unseen_headers, is_advertising
from core.models import Plan, Result, Status
from memory.mail_rules import MailRules

logger = logging.getLogger("jarvis.commands.mail")

_accounts: list[MailAccount] = []
_rules: Optional[MailRules] = None
_reader: Callable[[MailAccount], list[MailHeader]] = fetch_unseen_headers


def configure(config, reader: Optional[Callable[[MailAccount], list[MailHeader]]] = None) -> None:
    """Von main.py einmal beim Start aufgerufen. Baut die Konten aus
    config.mail_accounts + Env-Passwoertern und den Regel-Speicher im
    memory_dir. Tests rufen dies mit tmp_path-Config und einem Fake-Reader auf."""
    global _accounts, _rules, _reader
    _accounts = _build_accounts(config)
    _rules = MailRules(config.memory_dir)
    if reader is not None:
        _reader = reader


def _build_accounts(config) -> list[MailAccount]:
    """Konten aus config.mail_accounts; Passwort NUR aus der Umgebungsvariable
    (ADR-018). Konten ohne gesetztes Passwort werden uebersprungen - so kann man
    z. B. Gmail zuerst einrichten und Hotmail spaeter nachziehen."""
    accounts: list[MailAccount] = []
    for entry in getattr(config, "mail_accounts", []) or []:
        env_name = entry.get("password_env", "")
        password = os.environ.get(env_name, "")
        if not password:
            logger.warning(
                "Mail-Konto '%s' uebersprungen: Umgebungsvariable %s nicht gesetzt.",
                entry.get("label", "?"), env_name or "(kein password_env)",
            )
            continue
        accounts.append(
            MailAccount(
                label=entry.get("label", entry.get("username", "?")),
                host=entry["imap_host"],
                port=int(entry.get("imap_port", 993)),
                username=entry["username"],
                password=password,
            )
        )
    return accounts


def _require_configured() -> MailRules:
    if _rules is None:
        raise RuntimeError(
            "Mail-Briefing nicht konfiguriert - commands.mail.configure() muss "
            "beim Start aufgerufen werden (siehe main.py)."
        )
    return _rules


def _classify(headers: list[MailHeader]) -> tuple[list[MailHeader], list[MailHeader]]:
    """(relevant, werbung). Gelernte Regel schlaegt die Heuristik."""
    rules = _require_configured()
    relevant: list[MailHeader] = []
    ads: list[MailHeader] = []
    for h in headers:
        rule = rules.classify(h.sender)
        if rule == "keep":
            relevant.append(h)
        elif rule == "hide":
            ads.append(h)
        elif is_advertising(h):
            ads.append(h)
        else:
            relevant.append(h)
    return relevant, ads


def _collect() -> tuple[list[MailHeader], list[MailHeader], list[str]]:
    """Ueber alle Konten sammeln. Ein fehlerhaftes Konto bricht das Briefing
    nicht ab (fail-safe) - es wird als Hinweis vermerkt."""
    all_headers: list[MailHeader] = []
    errors: list[str] = []
    for account in _accounts:
        try:
            all_headers.extend(_reader(account))
        except Exception as e:  # noqa: BLE001 - Netzwerk/IMAP kann vielfaeltig scheitern
            logger.warning("Konto '%s' nicht erreichbar: %s", account.label, e)
            errors.append(f"{account.label} nicht erreichbar")
    relevant, ads = _classify(all_headers)
    return relevant, ads, errors


def _line(h: MailHeader) -> str:
    subject = h.subject or "(kein Betreff)"
    return f"- {h.sender_display}: {subject}"


def _briefing(relevant: list[MailHeader], ads: list[MailHeader], errors: list[str], *, show_ads: bool) -> str:
    lines: list[str] = []
    if relevant:
        lines.append(f"{len(relevant)} Nachricht(en), die für dich wichtig wirken:")
        lines += [_line(h) for h in relevant]
        if ads and show_ads:
            lines.append(f"Zusätzlich {len(ads)} Werbe-/Newsletter-Mail(s):")
            lines += [_line(h) for h in ads]
        elif ads:
            lines.append(
                f"Zusätzlich {len(ads)} Werbe-/Newsletter-Mail(s) ausgeblendet - "
                "sag 'zeig die Werbung', wenn du sie sehen willst."
            )
    elif ads:
        if show_ads:
            lines.append(f"Nichts Dringendes, Wolfgang. Hier sind die {len(ads)} Werbe-/Newsletter-Mail(s):")
            lines += [_line(h) for h in ads]
        else:
            lines.append(
                f"Nichts Dringendes, Wolfgang - nur {len(ads)} Werbe-/Newsletter-Mail(s), "
                "ausgeblendet. Sag 'zeig die Werbung', wenn du sie dennoch sehen willst."
            )
    else:
        lines.append("Nichts Neues, Wolfgang. Die Postfächer sind ruhig.")

    if errors:
        lines.append("Hinweis: " + "; ".join(errors) + ".")
    return "\n".join(lines)


class CheckMailCommand:
    name = "check_mail"
    description = (
        "Gibt einen Ueberblick ueber neue/ungelesene private Mails "
        "(z. B. 'was liegt an', 'neue Mails', 'was ist im Postfach') - "
        "Werbung wird ausgeblendet, Wichtiges vorgetragen."
    )
    requires_confirmation = False  # Sicherheitsstufe 0 (reines Lesen)

    def execute(self, plan: Plan) -> Result:
        _require_configured()
        if not _accounts:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=(
                    "Es ist noch kein Mail-Konto eingerichtet. Bitte in config.json unter "
                    "'mail_accounts' hinterlegen und das App-Passwort als Umgebungsvariable "
                    "setzen (siehe README)."
                ),
            )
        relevant, ads, errors = _collect()
        return Result(status=Status.SUCCESS, message=_briefing(relevant, ads, errors, show_ads=False))


class ShowMailAdvertisingCommand:
    name = "show_mail_advertising"
    description = "Zeigt die zuvor ausgeblendeten Werbe-/Newsletter-Mails an (z. B. 'zeig mir die Werbung')."
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        _require_configured()
        if not _accounts:
            return Result(status=Status.NEEDS_CLARIFICATION, message="Es ist noch kein Mail-Konto eingerichtet.")
        relevant, ads, errors = _collect()
        return Result(status=Status.SUCCESS, message=_briefing(relevant, ads, errors, show_ads=True))


class MailHideSenderCommand:
    name = "mail_hide_sender"
    description = (
        "Merkt sich dauerhaft, einen Absender kuenftig auszublenden "
        "(z. B. 'von Amazon will ich nichts mehr', 'X immer ausblenden'). "
        "target = der Absendername."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        pattern = (plan.target or "").strip()
        if not pattern:
            return Result(status=Status.NEEDS_CLARIFICATION, message="Welchen Absender soll ich künftig ausblenden?")
        _require_configured().hide(pattern)
        return Result(status=Status.SUCCESS, message=f"Verstanden. Post von '{pattern}' blende ich künftig aus.")


class MailKeepSenderCommand:
    name = "mail_keep_sender"
    description = (
        "Merkt sich dauerhaft, einen Absender kuenftig immer zu zeigen - schlaegt die "
        "Werbung-Erkennung (z. B. 'das ist keine Werbung', 'von X will ich immer hoeren'). "
        "target = der Absendername."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        pattern = (plan.target or "").strip()
        if not pattern:
            return Result(status=Status.NEEDS_CLARIFICATION, message="Von welchem Absender soll ich künftig immer hören?")
        _require_configured().keep(pattern)
        return Result(status=Status.SUCCESS, message=f"Verstanden: Post von '{pattern}' zeige ich dir künftig immer.")


# Registrierungspunkt - commands/__init__.py liest diese Liste beim Start ein.
COMMANDS = [
    CheckMailCommand(),
    ShowMailAdvertisingCommand(),
    MailHideSenderCommand(),
    MailKeepSenderCommand(),
]
