"""Test für main.py - nur die EXIT_WORDS-Liste, kein voller Pipeline-
Lauf (der ist bereits in test_integration.py abgedeckt).

Lesson Learned 2026-07-01: "Ende" war nicht in der Exit-Liste, ist
stattdessen an die KI gegangen und wurde faelschlich als shutdown_pc
erkannt - ein bestaetigtes "ja" hat den echten PC heruntergefahren.
"""
from __future__ import annotations

import main


class _FakeStream:
    """Minimaler Stream-Stub, der reconfigure()-Aufrufe protokolliert."""

    def __init__(self, supports_reconfigure: bool = True) -> None:
        self._supports = supports_reconfigure
        self.reconfigure_kwargs: dict | None = None

    def __getattr__(self, name: str):
        if name == "reconfigure" and self._supports:
            def _reconfigure(**kwargs):
                self.reconfigure_kwargs = kwargs
            return _reconfigure
        raise AttributeError(name)


def test_make_console_output_safe_sets_replace(monkeypatch):
    out, err = _FakeStream(), _FakeStream()
    monkeypatch.setattr(main.sys, "stdout", out)
    monkeypatch.setattr(main.sys, "stderr", err)
    main.make_console_output_safe()
    assert out.reconfigure_kwargs == {"errors": "replace"}
    assert err.reconfigure_kwargs == {"errors": "replace"}


def test_make_console_output_safe_tolerates_missing_reconfigure(monkeypatch):
    # Streams ohne reconfigure (z. B. umgeleitete Pipes) duerfen nicht crashen.
    monkeypatch.setattr(main.sys, "stdout", _FakeStream(supports_reconfigure=False))
    monkeypatch.setattr(main.sys, "stderr", None)
    main.make_console_output_safe()  # darf keine Exception werfen


def test_common_exit_words_are_covered():
    expected = {"exit", "quit", "beenden", "ende", "stop", "stopp", "tschüss", "bye"}
    assert expected <= main.EXIT_WORDS


def test_exit_words_are_lowercase():
    # main.py vergleicht user_input.lower() gegen EXIT_WORDS - jedes
    # Wort hier muss deshalb bereits klein geschrieben sein.
    assert all(word == word.lower() for word in main.EXIT_WORDS)
