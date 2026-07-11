"""
Mail-Reader für das Briefing „Was liegt an?" (Nutzwert-Phase, ADR-031).

Erster externer Connector. Bewusst minimal und sicher:
- **Nur lesend** (IMAP `select(readonly=True)` + `BODY.PEEK`), Jarvis markiert
  nichts als gelesen, löscht/verschickt nichts (Sicherheitsstufe 0).
- **Nur Kopfzeilen** (From, Subject, Date, List-Unsubscribe, Precedence) -
  kein Mailinhalt wird abgerufen oder gespeichert, nichts geht an eine KI.
- **Bordmittel** (`imaplib`/`email`, stdlib) - keine neue Pflichtabhängigkeit.

Die Werbung-Heuristik ist absichtlich einfach und lokal; sie ist nicht perfekt
(deshalb „ausblenden ≠ wegwerfen" im Command). Das stärkste Signal ist die
`List-Unsubscribe`-Kopfzeile, die Massen-/Newsletter-Mails fast immer tragen.
"""
from __future__ import annotations

import imaplib
import logging
from dataclasses import dataclass
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parseaddr

logger = logging.getLogger("jarvis.mail_reader")

# Nur schwache Zusatzsignale - das Hauptsignal ist List-Unsubscribe. Bewusst
# konservativ (kein "info@"), damit legitime Absender nicht fälschlich als
# Werbung gelten.
_ADVERTISING_SENDER_HINTS = ("no-reply@", "noreply@", "do-not-reply@", "newsletter@", "mailing@")

_HEADER_FIELDS = "FROM SUBJECT DATE LIST-UNSUBSCRIBE PRECEDENCE"


@dataclass
class MailAccount:
    label: str
    host: str
    port: int
    username: str
    password: str


@dataclass
class MailHeader:
    account: str
    sender: str          # dekodierte From-Kopfzeile (Anzeigename + Adresse)
    sender_display: str  # nur der Anzeigename (Fallback: Adresse)
    subject: str
    date: str
    list_unsubscribe: str
    precedence: str


def is_advertising(header: MailHeader) -> bool:
    """Lokale Heuristik: Werbung/Newsletter ja/nein - nur aus Kopfzeilen."""
    if header.list_unsubscribe.strip():
        return True
    if "bulk" in header.precedence.lower():
        return True
    sender = header.sender.lower()
    return any(hint in sender for hint in _ADVERTISING_SENDER_HINTS)


def _decode(value: str) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # pragma: no cover - defensive; kaputte Kopfzeile
        return value


def _to_header(label: str, raw: bytes) -> MailHeader:
    msg = message_from_bytes(raw)
    from_raw = _decode(msg.get("From", ""))
    display, address = parseaddr(from_raw)
    return MailHeader(
        account=label,
        sender=from_raw,
        sender_display=(display or address or from_raw).strip(),
        subject=_decode(msg.get("Subject", "")).strip(),
        date=msg.get("Date", ""),
        list_unsubscribe=msg.get("List-Unsubscribe", ""),
        precedence=msg.get("Precedence", ""),
    )


def _extract_header_bytes(fetch_data) -> bytes:
    for part in fetch_data:
        if isinstance(part, tuple) and len(part) >= 2 and part[1]:
            return part[1]
    return b""


def fetch_unseen_headers(account: MailAccount, limit: int = 50) -> list[MailHeader]:
    """Ungelesene Nachrichten eines Kontos als Kopfzeilen. Strikt read-only.
    Wirft bei Verbindungs-/Login-Fehlern - der Aufrufer (commands/mail.py)
    fängt das pro Konto ab und fällt fail-safe zurück."""
    conn = imaplib.IMAP4_SSL(account.host, account.port)
    try:
        conn.login(account.username, account.password)
        # readonly=True -> EXAMINE statt SELECT: setzt niemals \Seen.
        conn.select("INBOX", readonly=True)
        typ, data = conn.search(None, "UNSEEN")
        if typ != "OK" or not data or not data[0]:
            return []
        ids = data[0].split()[-limit:]
        headers: list[MailHeader] = []
        for num in ids:
            # BODY.PEEK holt Kopfzeilen, ohne \Seen zu setzen (doppelte
            # Absicherung zusätzlich zum readonly-select).
            typ, msgdata = conn.fetch(num, f"(BODY.PEEK[HEADER.FIELDS ({_HEADER_FIELDS})])")
            if typ != "OK":
                continue
            raw = _extract_header_bytes(msgdata)
            if raw:
                headers.append(_to_header(account.label, raw))
        return headers
    finally:
        try:
            conn.logout()
        except Exception:  # pragma: no cover - Verbindung evtl. schon tot
            pass
