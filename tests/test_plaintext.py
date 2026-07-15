"""Tests fuer core/plaintext.py (Kundenreview 13.07.: sichtbare **-Zeichen).
Konservativ: nur eindeutige Markdown-Paare fallen, Inhalt bleibt woertlich."""
from __future__ import annotations

from core.plaintext import strip_markdown_marks


def test_strips_bold_italic_code_and_headings():
    text = "## Lage\n**Wichtig:** der *Termin* ist um `9:00` - __bitte__ merken."
    assert strip_markdown_marks(text) == (
        "Lage\nWichtig: der Termin ist um 9:00 - bitte merken."
    )


def test_keeps_math_lists_and_single_asterisks():
    text = "- 2 * 3 = 6\n- Sternchen * bleibt\n* auch am Anfang"
    assert strip_markdown_marks(text) == text


def test_multiline_bold_and_empty_and_nonstring_are_safe():
    assert strip_markdown_marks("**mehr\nzeilig**") == "mehr\nzeilig"
    assert strip_markdown_marks("") == ""
    assert strip_markdown_marks(None) is None
