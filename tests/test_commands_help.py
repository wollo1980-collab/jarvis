"""Tests fuer commands/help.py - "Was kannst du?" + "Was ist neu?"
(Spektakulaer-Kampagne #1, Kundenreview 13.07.2026)."""
from __future__ import annotations

import commands.help as help_commands
from core.models import Plan, Status


def _plan(intent: str) -> Plan:
    return Plan(intent=intent, raw_input="")


# --- show_help --------------------------------------------------------------

def test_help_lists_categories_and_examples():
    result = help_commands.ShowHelpCommand().execute(_plan("show_help"))
    assert result.status == Status.SUCCESS
    for anchor in ("Briefing", "Merk dir", "Bau mir", "Was ist neu?",
                   "normales Deutsch"):
        assert anchor in result.message, anchor


def test_help_references_only_real_intents():
    """Die eiserne Erdung: JEDE in der Hilfe versprochene Faehigkeit existiert
    wirklich in der Registry - die Hilfe erfindet NIE etwas (Kundenreview-Regel
    'nie erfundene Versprechen')."""
    from commands import REGISTRY

    for intent in help_commands.REFERENCED_INTENTS:
        assert intent in REGISTRY, f"Hilfe verspricht unregistriertes '{intent}'"


def test_help_greeting_follows_time_of_day():
    from datetime import datetime

    assert help_commands._greeting(datetime(2026, 7, 13, 8, 0)).startswith("Guten Morgen")
    assert help_commands._greeting(datetime(2026, 7, 13, 20, 0)).startswith("Guten Abend")
    assert help_commands._greeting(datetime(2026, 7, 13, 14, 0)).startswith("Gern")


# --- whats_new --------------------------------------------------------------

_CHANGELOG = """# Changelog

## 2026-07-13 - Jarvis meldet sich morgens von selbst

### Neu
- **Morgen-Briefing aufs Handy:** Einmal am Tag kommt dein Tages-Briefing aktiv per Telegram.
- **Termin-Vorbereitung kurz vorher:** 30 Minuten vor einem Termin kommt die Karte.

## 2026-07-12 - Jarvis baut Werkzeuge

### Neu
- **Bau mir X:** Jarvis baut echte kleine Tools.

## 2026-07-11 - Alte Eintraege

### Neu
- Sollte nicht mehr auftauchen (nur die juengsten 2 Bloecke).
"""


def test_whats_new_truncates_at_line_boundary_never_mid_word():
    """Live-Reibung 13.07. 23:00: die Antwort endete mitten im Wort («ist
    ent …»). Der Deckel schneidet jetzt an der letzten vollstaendigen Zeile
    und rundet ehrlich ab."""
    lines = "\n".join(f"- Punkt {i}: eine ordentlich lange Beschreibungszeile "
                      f"mit vielen Woertern darin." for i in range(40))
    out = help_commands._latest_blocks(f"## 2026-07-14 - Titel\n{lines}\n", max_chars=500)

    assert out.endswith("… und ein paar Dinge mehr.")
    body = out.rsplit("\n\n", 1)[0]
    assert body.endswith("darin.")            # letzte Zeile vollstaendig
    assert len(out) < 620                      # Deckel wirkt weiterhin


def test_whats_new_reads_latest_changelog_blocks(tmp_path):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(_CHANGELOG, encoding="utf-8")
    help_commands.configure(path)
    try:
        result = help_commands.WhatsNewCommand().execute(_plan("whats_new"))
    finally:
        help_commands.configure(None)

    assert result.status == Status.SUCCESS
    assert "Morgen-Briefing aufs Handy" in result.message
    assert "Bau mir X" in result.message
    assert "Sollte nicht mehr auftauchen" not in result.message   # nur 2 Bloecke
    assert "**" not in result.message                             # sprechtauglich
    assert "###" not in result.message
    assert result.data and "compose_context" in result.data


def test_whats_new_without_changelog_is_honest(tmp_path):
    help_commands.configure(tmp_path / "gibt-es-nicht.md")
    try:
        result = help_commands.WhatsNewCommand().execute(_plan("whats_new"))
    finally:
        help_commands.configure(None)
    assert result.status == Status.SUCCESS
    assert "keine Neuigkeiten-Liste" in result.message


def test_latest_headline(tmp_path):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(_CHANGELOG, encoding="utf-8")
    assert help_commands.latest_headline(path) == "2026-07-13 - Jarvis meldet sich morgens von selbst"
    assert help_commands.latest_headline(tmp_path / "fehlt.md") == ""
