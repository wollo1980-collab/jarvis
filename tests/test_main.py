"""Test für main.py - nur die EXIT_WORDS-Liste, kein voller Pipeline-
Lauf (der ist bereits in test_integration.py abgedeckt).

Lesson Learned 2026-07-01: "Ende" war nicht in der Exit-Liste, ist
stattdessen an die KI gegangen und wurde faelschlich als shutdown_pc
erkannt - ein bestaetigtes "ja" hat den echten PC heruntergefahren.
"""
from __future__ import annotations

import main


def test_common_exit_words_are_covered():
    expected = {"exit", "quit", "beenden", "ende", "stop", "stopp", "tschüss", "bye"}
    assert expected <= main.EXIT_WORDS


def test_exit_words_are_lowercase():
    # main.py vergleicht user_input.lower() gegen EXIT_WORDS - jedes
    # Wort hier muss deshalb bereits klein geschrieben sein.
    assert all(word == word.lower() for word in main.EXIT_WORDS)
