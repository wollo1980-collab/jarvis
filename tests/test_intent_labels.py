"""Drift-Waechter fuer core/intent_labels.py (Live-Reibung 13.07. spät: die
Ja/Nein-Frage nannte 'build_project' roh - Raten statt Verstehen). Zwei
Kopplungen: an die Command-Registry (kein Command ohne deutschen Namen) und
an die Dashboard-JS-Tabelle (beide Tabellen sagen WORTGLEICH dasselbe)."""
from __future__ import annotations

import re
from pathlib import Path

import commands
from core.intent_labels import INTENT_LABELS, label_for


def test_every_registered_command_has_a_german_label():
    missing = sorted(set(commands.REGISTRY) - set(INTENT_LABELS))
    assert not missing, f"Intents ohne deutschen Aktions-Namen: {missing}"


def test_python_and_dashboard_tables_are_word_identical():
    """EINE Wahrheit auch hier: weicht ein Wortlaut zwischen Python (Ja/Nein-
    Fragen) und JS (LIVE-ABLAUF) ab, bricht dieser Test - nicht erst das
    naechste Review."""
    src = (Path(__file__).resolve().parent.parent / "dashboard.py").read_text(encoding="utf-8")
    block = re.search(r"const INTENT_LABELS = \{(.*?)\};", src, re.S)
    assert block, "INTENT_LABELS-Tabelle nicht in dashboard.py gefunden"
    js = dict(re.findall(r"^\s*(\w+):\s*'([^']*)'", block.group(1), re.M))

    assert js == INTENT_LABELS


def test_label_for_falls_back_to_raw_name():
    assert label_for("build_project") == "Projekt bauen"
    assert label_for("voellig_unbekannt") == "voellig_unbekannt"   # ehrlich roh
