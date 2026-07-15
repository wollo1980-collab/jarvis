"""
Markdown-Reste aus LLM-Antworten entfernen (Kundenreview 13.07., Schmerzpunkt
'Unfertige Formatierung: Antworten zeigen **-Zeichen').

Die Prompts verbieten Markdown laengst ('kein Markdown-Fett') - Modelle
rutschen trotzdem regelmaessig hinein. Wie beim Gespraechs-Faden gilt: die
letzte Stufe GARANTIERT, statt auf Prompt-Gehorsam zu hoffen. Eine Stelle
fuer ALLE Kanaele (UI, Sprache, Telegram): gestrippt wird dort, wo die
LLM-Antwort entsteht (AIEngine.answer, response_composer).

Bewusst KONSERVATIV: nur eindeutige Markdown-Paare (**fett**, __fett__,
*kursiv*, `code`) und Ueberschriften-Rauten am Zeilenanfang. Listen ('- '),
einzelne Sternchen (Mathe: 2*3) und alles Unklare bleiben unangetastet -
lieber ein Rest-Sternchen als ein zerstoerter Satz.
"""
from __future__ import annotations

import re

_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
_BOLD_UNDER = re.compile(r"__(.+?)__", re.S)
# Kursiv nur, wenn das Paar direkt am Wort klebt (*so*) - '2 * 3' bleibt.
_ITALIC = re.compile(r"(?<!\*)\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\*)")
_CODE = re.compile(r"`([^`\n]+)`")
_HEADING = re.compile(r"^#{1,4}\s+", re.M)


def strip_markdown_marks(text: str) -> str:
    """Entfernt Markdown-Auszeichnungen, laesst den Inhalt woertlich stehen.
    Fail-safe: bei Nicht-String kommt der Wert unveraendert zurueck."""
    if not isinstance(text, str) or not text:
        return text
    out = _BOLD.sub(r"\1", text)
    out = _BOLD_UNDER.sub(r"\1", out)
    out = _ITALIC.sub(r"\1", out)
    out = _CODE.sub(r"\1", out)
    out = _HEADING.sub("", out)
    return out
