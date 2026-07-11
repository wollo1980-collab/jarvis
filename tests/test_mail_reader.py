"""Tests für core/mail_reader.py (ADR-031). imaplib wird gemockt - kein
echtes Postfach, keine Netzwerkverbindung. Prüft insbesondere das strikte
Read-only-Verhalten (kein Setzen von \\Seen)."""
from __future__ import annotations

import core.mail_reader as mail_reader
from core.mail_reader import MailAccount, MailHeader, fetch_unseen_headers, is_advertising

RAW = (
    b"From: Amazon.de <versand@amazon.de>\r\n"
    b"Subject: Deine Bestellung\r\n"
    b"List-Unsubscribe: <mailto:unsub@amazon.de>\r\n"
    b"\r\n"
)
RAW_ENCODED = (
    b"From: =?UTF-8?Q?B=C3=BCcherei?= <info@buecherei.de>\r\n"
    b"Subject: =?UTF-8?B?TcOkaG51bmc=?=\r\n"  # "Mähnung"
    b"\r\n"
)


class _FakeIMAP:
    def __init__(self):
        self.select_args = None
        self.fetch_specs = []
        self.logged_out = False

    def login(self, user, password):
        self.creds = (user, password)

    def select(self, mailbox, readonly=False):
        self.select_args = (mailbox, readonly)
        return ("OK", [b"2"])

    def search(self, charset, criterion):
        self.search_args = (charset, criterion)
        return ("OK", [b"1 2"])

    def fetch(self, num, spec):
        self.fetch_specs.append(spec)
        return ("OK", [(b"%s (BODY[HEADER] {%d}" % (num, len(RAW)), RAW), b")"])

    def logout(self):
        self.logged_out = True


def _account():
    return MailAccount(label="Gmail", host="imap.gmail.com", port=993, username="u", password="p")


def test_fetch_is_read_only_and_uses_peek(monkeypatch):
    fake = _FakeIMAP()
    monkeypatch.setattr(mail_reader.imaplib, "IMAP4_SSL", lambda host, port: fake)

    headers = fetch_unseen_headers(_account())

    # readonly=True -> EXAMINE, setzt niemals \Seen:
    assert fake.select_args == ("INBOX", True)
    # BODY.PEEK statt BODY (doppelte Absicherung):
    assert all("BODY.PEEK" in s for s in fake.fetch_specs)
    assert fake.search_args == (None, "UNSEEN")
    assert fake.logged_out is True
    assert len(headers) == 2
    assert headers[0].sender_display == "Amazon.de"
    assert headers[0].subject == "Deine Bestellung"
    assert headers[0].list_unsubscribe != ""


def test_fetch_decodes_mime_encoded_headers(monkeypatch):
    fake = _FakeIMAP()
    fake.fetch = lambda num, spec: ("OK", [(b"1 (x", RAW_ENCODED), b")"])
    fake.search = lambda charset, crit: ("OK", [b"1"])
    monkeypatch.setattr(mail_reader.imaplib, "IMAP4_SSL", lambda host, port: fake)

    headers = fetch_unseen_headers(_account())
    assert len(headers) == 1
    assert headers[0].sender_display == "Bücherei"
    assert headers[0].subject == "Mähnung"


def test_fetch_returns_empty_on_no_unseen(monkeypatch):
    fake = _FakeIMAP()
    fake.search = lambda charset, crit: ("OK", [b""])
    monkeypatch.setattr(mail_reader.imaplib, "IMAP4_SSL", lambda host, port: fake)
    assert fetch_unseen_headers(_account()) == []


def _hdr(**kw):
    base = dict(account="Gmail", sender="", sender_display="", subject="", date="",
               list_unsubscribe="", precedence="")
    base.update(kw)
    return MailHeader(**base)


def test_is_advertising_list_unsubscribe():
    assert is_advertising(_hdr(sender="Shop <a@shop.de>", list_unsubscribe="<mailto:x>")) is True


def test_is_advertising_precedence_bulk():
    assert is_advertising(_hdr(sender="Shop <a@shop.de>", precedence="bulk")) is True


def test_is_advertising_noreply_sender():
    assert is_advertising(_hdr(sender="Info <no-reply@shop.de>")) is True


def test_is_not_advertising_personal():
    assert is_advertising(_hdr(sender="Max Mustermann <max@gmx.de>", subject="Mittagessen?")) is False
