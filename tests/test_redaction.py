"""Tests fuer core/redaction.py (ADR-040) und die drei Persistenz-Einhaenge:
Secrets duerfen nie im Klartext auf Platte landen.
release-scan: datei-ok (alle Secrets hier sind bewusst erfundene Beispiele -
genau sie zu erkennen ist der Zweck dieser Tests)."""
from __future__ import annotations

from pathlib import Path

from core.models import Message
from core.redaction import REDACTED, redact
from memory.entries import EntryStore
from memory.long_term import LongTermMemory
from memory.store import JsonMemoryStore


def test_known_key_formats_are_redacted():
    cases = [
        "sk-abcdefghijklmnopqrstuvwx1234",              # OpenAI
        "sk-ant-abcdefghijklmnop1234",                   # Anthropic
        "ghp_abcdefghijklmnopqrstuv123456",              # GitHub
        "github_pat_abcdefghijklmnopqrstuv_12345",       # GitHub fine-grained
        "AKIAIOSFODNN7EXAMPLE",                          # AWS
        "xoxb-1234567890-abcdefghij",                    # Slack
        "1234567890:AAHdqwerty-abcdefghijklmnopqrstuv1",  # Telegram-Bot-Token
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",   # Bearer
    ]
    for secret in cases:
        out = redact(f"hier: {secret} ende")
        assert secret not in out, f"nicht geschwaerzt: {secret}"
        assert REDACTED in out
        assert out.startswith("hier: ") and out.endswith(" ende")


def test_private_key_block_is_redacted():
    text = "davor\n-----BEGIN RSA PRIVATE KEY-----\nMIIabc\nxyz\n-----END RSA PRIVATE KEY-----\ndanach"
    out = redact(text)
    assert "MIIabc" not in out
    assert "davor" in out and "danach" in out


def test_password_phrase_redacts_only_the_secret():
    out = redact("Merk dir: mein Passwort lautet geheim123 fuer den Router")
    assert "geheim123" not in out
    assert "Passwort lautet" in out          # Satz bleibt lesbar
    assert "fuer den Router" in out
    # Frage-Formulierung ohne Secret bleibt unangetastet:
    assert redact("Wie lautet mein Passwort?") == "Wie lautet mein Passwort?"


def test_normal_text_is_untouched():
    for text in (
        "Erinnere mich morgen um 9 an den Zahnarzt",
        "Max ist mein Sohn",
        "Der Termin am 12.07.2025 in Musterstadt",
        "skifahren macht spass",                 # kein sk-Key
        "",
    ):
        assert redact(text) == text


def test_redact_is_idempotent():
    once = redact("key: sk-abcdefghijklmnopqrstuvwx1234")
    assert redact(once) == once


def test_history_persists_redacted(tmp_path: Path):
    store = JsonMemoryStore(tmp_path)
    store.append_history(Message(role="user", content="mein key ist sk-abcdefghijklmnopqrstuvwx1234"))

    raw = (tmp_path / "history.json").read_text(encoding="utf-8")
    assert "sk-abcdefghijklmnopqrstuvwx1234" not in raw
    assert REDACTED in store.get_history()[0].content


def test_long_term_persists_redacted(tmp_path: Path):
    memory = LongTermMemory(tmp_path)
    fact = memory.remember("passwort ist supergeheim42")

    raw = (tmp_path / "long_term.json").read_text(encoding="utf-8")
    assert "supergeheim42" not in raw
    assert REDACTED in fact.text  # Echo zeigt die Schwaerzung


def test_entries_persist_redacted(tmp_path: Path):
    store = EntryStore(tmp_path)
    entry = store.add("Token 1234567890:AAHdqwerty-abcdefghijklmnopqrstuv1 eintragen")

    raw = (tmp_path / "entries.json").read_text(encoding="utf-8")
    assert "AAHdqwerty" not in raw
    assert REDACTED in entry.text
