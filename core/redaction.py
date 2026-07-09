"""
Auto-Redaction (Welle 2.1, ADR-040): Secrets werden geschwaerzt, BEVOR sie
auf Platte landen - an den drei Persistenz-Punkten Gespraechsverlauf
(memory/store.py), Langzeitgedaechtnis (memory/long_term.py) und Eintraege
(memory/entries.py). Diktiert der Nutzer versehentlich einen API-Key oder
ein Passwort, bleibt der Satz lesbar, das Geheimnis verschwindet.

Bewusst NUR echte Secrets (benannte Muster + Passwort-Phrasen). E-Mail-
Adressen und Telefonnummern werden absichtlich NICHT geschwaerzt - sie sind
bei Jarvis Nutzdaten (Mail-Triage lebt von Absendern; ein Eintrag "ruf X
unter 0171... an" waere geschwaerzt sinnlos). Siehe ADR-040.

Ehrliche Grenze: Muster fangen BEKANNTE Formate - keine Garantie gegen
exotische Secrets. Idempotent (bereits geschwaerzter Text bleibt gleich).
"""
from __future__ import annotations

import re

REDACTED = "[Secret entfernt]"

# Reihenfolge zaehlt: spezifische Muster vor generischen (sk-ant- wuerde
# sonst vom OpenAI-Muster halb getroffen).
_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    (
        "private-key-block",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)",
            re.DOTALL,
        ),
    ),
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}")),
    ("openai-key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    (
        "github-token",
        re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"),
    ),
    ("aws-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    # Telegram-Bot-Token (JARVIS_TELEGRAM_BOT_TOKEN-Format) - unser
    # sensibelstes Secret: <bot-id>:<35 Zeichen Key>.
    ("telegram-bot-token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b")),
    ("bearer-token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
)

# Passwort-Phrasen ("mein Passwort ist geheim123"): nur das Secret wird
# ersetzt, der Satz bleibt lesbar/nachvollziehbar.
_PASSWORD_PHRASE = re.compile(
    r"(?i)\b(passwort|password|passwd|pwd|pin)\b(\s*(?:ist|lautet|=|:)\s*)(\S+)"
)


def redact(text: str) -> str:
    """Schwaerzt bekannte Secret-Formate in `text`. Fail-safe: leerer/None-
    aehnlicher Text kommt unveraendert zurueck; normaler Text bleibt normal."""
    if not text:
        return text
    for _name, pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    text = _PASSWORD_PHRASE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    return text
