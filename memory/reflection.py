"""
Nächtliche Reflexion ('dreaming', Gedaechtnis-Kampagne Stufe 2) - aus den rohen
Episoden des Tages (memory/episodic.py) destilliert Jarvis in Ruhephasen ein
kurzes, EINSEHBARES Journal: was war, welche Muster/Gewohnheiten sich zeigen,
woraus zu lernen ist. Muster konvergent mit OpenClaws 'dreaming' (idle-time-
Konsolidierung) und der [[gewohnheits-lernen-vision]].

Leitplanken (Governance + DNA):
- VORSCHLAG statt Aktion: die Reflexion behauptet NICHTS als Fakt und HANDELT
  nie - sie nennt hoechstens VERMUTUNGEN als Frage-Kandidaten. Ob daraus ein
  Merk-Vorschlag wird, entscheidet ein spaeterer Stein (einmal fragen, nie
  heimlich speichern).
- Einsehbar/redigierbar: ein Markdown-Journal je Tag (memory_dir/reflections/).
- Fail-safe: LLM-/Schreibfehler stoeren nie (nur WARNING). Der LLM-Aufruf ist
  als Callable injiziert - testbar ohne Netz.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Callable

logger = logging.getLogger("jarvis.reflection")

_MAX_EPISODES = 200  # ein Tag ist ueberschaubar; Deckel gegen Ausreisser

# Zieht die These aus einer "Vermutung: … — nachfragen?"-Zeile (das Format, das
# build_reflection_prompt anfordert) heraus - fuer den Merk-Vorschlag (Stein 2b).
_VERMUTUNG_RE = re.compile(r"Vermutung:\s*(.+?)\s*(?:—|–|--|-|\n|$)")


def build_reflection_prompt(episodes: list[dict], day: date) -> str:
    """Baut den Reflexions-Prompt aus den Tagesepisoden - kompakt (eine Zeile je
    Episode) und mit klarer Vorschlag-statt-Aktion-Anweisung."""
    lines = [
        f"Das ist Jarvis' Ereignis-Tagebuch vom {day.isoformat()}. Reflektiere",
        "kurz und nuechtern als inneres Journal (nicht ansprechen, keine Anrede):",
        "- Worum ging es dem Nutzer heute (Themen)?",
        "- Faellt eine wiederkehrende Gewohnheit auf (z. B. regelmaessig zur",
        "  gleichen Zeit dasselbe)?",
        "- Gab es Reibungen/Fehlschlaege, aus denen zu lernen ist?",
        "Schliesse mit HOECHSTENS 1-2 VERMUTUNGEN als Frage-Kandidaten in der",
        "Form 'Vermutung: … — nachfragen?'. Behaupte NIE etwas als Tatsache und",
        "schlage keine Aktion vor, die du selbst ausfuehrst.",
        "",
        "Ereignisse:",
    ]
    for ep in episodes[:_MAX_EPISODES]:
        intents = "+".join(ep.get("intents") or []) or "chat"
        lines.append(f"- [{ep.get('ts', '')}] «{ep.get('user_input', '')}» -> {intents}")
    return "\n".join(lines)


def reflect(episodes: list[dict], day: date, answer_fn: Callable[[str], str]) -> str:
    """Destilliert die Episoden zu einem Reflexions-Text (Markdown). `answer_fn`
    ist der LLM-Aufruf (injiziert). Leerer Tag -> stille Notiz; LLM-Fehler ->
    leerer String (der Aufrufer schreibt dann nichts)."""
    if not episodes:
        return f"# Reflexion {day.isoformat()}\n\n(Keine Ereignisse — ein stiller Tag.)\n"
    try:
        body = answer_fn(build_reflection_prompt(episodes, day))
    except Exception:  # noqa: BLE001 - die Reflexion stoert nie
        logger.warning("Reflexion: LLM-Aufruf fehlgeschlagen (ignoriert).", exc_info=True)
        return ""
    body = (body or "").strip()
    if not body:
        return ""
    return f"# Reflexion {day.isoformat()}\n\n{body}\n"


def suggestion_from_reflection(text: str) -> str:
    """Die ERSTE 'Vermutung: …' aus einem Reflexions-Text als knappen Merk-
    Kandidaten (nur die These, ohne '— nachfragen?'). '' wenn keine oder zu
    lang/leer (Muell-/Nerv-Schutz). Das ist bewusst PARSING statt zweitem LLM-
    Call: das Format kommt aus unserem eigenen Reflexions-Prompt."""
    if not text:
        return ""
    match = _VERMUTUNG_RE.search(text)
    if not match:
        return ""
    cand = match.group(1).strip().strip('.«»"„“').strip()
    if not cand or len(cand) > 140:
        return ""
    return cand


class ReflectionJournal:
    """Das einsehbare Reflexions-Journal: ein Markdown je Tag."""

    def __init__(self, base_dir: Path):
        self._dir = Path(base_dir) / "reflections"

    def _file_for(self, day: date) -> Path:
        return self._dir / f"{day.isoformat()}.md"

    def write(self, day: date, text: str) -> None:
        """Schreibt (ueberschreibt) das Journal des Tages. Leerer Text -> nichts.
        Fail-safe."""
        if not text or not text.strip():
            return
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._file_for(day).write_text(text, encoding="utf-8")
        except OSError:
            logger.warning("Reflexion: Schreiben fehlgeschlagen (ignoriert).", exc_info=True)

    def read(self, day: date) -> str:
        try:
            return self._file_for(day).read_text(encoding="utf-8")
        except OSError:
            return ""

    def latest(self) -> str:
        """Die juengste vorhandene Reflexion (fuer 'was ist dir aufgefallen?')."""
        try:
            files = sorted(self._dir.glob("*.md"))
        except OSError:
            return ""
        return files[-1].read_text(encoding="utf-8") if files else ""
