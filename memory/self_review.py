"""
Selbst-Verbesserung (ADR-066 Stein 3) - „lernt und wird besser".

Ein COO reflektiert die EIGENE Leistung. Aus dem episodischen Log destilliert
Jarvis eine ehrliche Selbstbewertung: wo hat er den Nutzer NICHT gut genug
verstanden/bedient (Missverstaendnisse, unnoetige Rueckfragen, Fehlgriffe,
mehrfaches Umformulieren)? Ergebnis ist ein EINSEHBARES Journal + hoechstens EIN
konkreter Verbesserungs-Bereich, formuliert als OFFENE Beobachtung mit Bitte um
die Sicht des Nutzers - kein Versprechen, keine Selbst-Aenderung (Jarvis kann
sich nicht selbst umprogrammieren; er macht seine Reibungen transparent und
laedt zur Steuerung ein).

Deterministische Signale (Kennzahlen) + ein injizierter LLM-Aufruf (testbar).
Fail-safe.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Callable

logger = logging.getLogger("jarvis.self_review")

_MAX_EPISODES = 400
_FRICTION_SAMPLE = 8
_FAILURE_MARK = "✗"
_CLARIFY_MARK = "?"


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def _similar(a: str, b: str) -> bool:
    """Grobe Aehnlichkeit zweier Nutzereingaben (Jaccard der Wortmengen >= 0.5) -
    Heuristik fuer 'musste umformulieren'."""
    wa, wb = set(a.split()), set(b.split())
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= 0.5


def _is_friction(ep: dict) -> bool:
    resp = (ep.get("response") or "").strip()
    return _FAILURE_MARK in resp or resp.startswith(_CLARIFY_MARK)


def collect_signals(episodes: list[dict]) -> dict:
    """Deterministische Kennzahlen: Interaktionen, Fehlgriffe, Rueckfragen,
    mutmassliche Umformulierungen (aufeinanderfolgende aehnliche Eingaben)."""
    total = len(episodes)
    failures = clarifications = rephrasings = 0
    prev = None
    for ep in episodes:
        resp = (ep.get("response") or "").strip()
        if _FAILURE_MARK in resp:
            failures += 1
        elif resp.startswith(_CLARIFY_MARK):
            clarifications += 1
        cur = _norm(ep.get("user_input", ""))
        if prev is not None and _similar(prev, cur):
            rephrasings += 1
        prev = cur
    return {"total": total, "failures": failures,
            "clarifications": clarifications, "rephrasings": rephrasings}


def build_self_review_prompt(signals: dict, frictions: list[dict], period_label: str) -> str:
    lines = [
        f"Das ist eine EHRLICHE Selbstbewertung deiner Leistung als Assistent "
        f"Jarvis ({period_label}). Bewerte nuechtern und OHNE Schoenfaerberei, WO "
        "du dem Nutzer nicht gut genug geholfen hast: Missverstaendnisse, unnoetige "
        "Rueckfragen, Fehlgriffe, Dinge, die er mehrfach umformulieren musste.",
        f"Kennzahlen: {signals.get('total', 0)} Interaktionen, "
        f"{signals.get('failures', 0)} Fehlgriffe/Fehler, "
        f"{signals.get('clarifications', 0)} Rueckfragen, "
        f"{signals.get('rephrasings', 0)} mutmassliche Umformulierungen.",
        "Nenne HOECHSTENS EINEN konkreten Bereich, in dem du dich verbessern "
        "koenntest, und formuliere ihn als OFFENE Beobachtung mit Bitte um die "
        "Sicht/den Wunsch des Nutzers - KEIN Versprechen, KEINE Aktion, die du "
        "selbst ausfuehrst. Kurz, konkret, kein Markdown-Fett.",
    ]
    if frictions:
        lines.append("")
        lines.append("Beispiele fuer Reibungen (Eingabe -> deine Antwort):")
        for ep in frictions[:_FRICTION_SAMPLE]:
            lines.append(f"- «{ep.get('user_input', '')}» -> {(ep.get('response') or '')[:120]}")
    return "\n".join(lines)


def self_review(episodes: list[dict], period_label: str, answer_fn: Callable[[str], str]) -> str:
    """Destilliert die Episoden zu einer Selbstbewertung (Markdown). Leerer
    Zeitraum -> stille Notiz; LLM-Fehler -> '' (Aufrufer schreibt dann nichts)."""
    if not episodes:
        return f"# Selbstbewertung {period_label}\n\n(Keine Ereignisse — nichts zu bewerten.)\n"
    signals = collect_signals(episodes[:_MAX_EPISODES])
    frictions = [ep for ep in episodes if _is_friction(ep)]
    try:
        body = answer_fn(build_self_review_prompt(signals, frictions, period_label))
    except Exception:  # noqa: BLE001 - die Selbstbewertung stoert nie
        logger.warning("Selbstbewertung: LLM-Aufruf fehlgeschlagen (ignoriert).", exc_info=True)
        return ""
    body = (body or "").strip()
    if not body:
        return ""
    return f"# Selbstbewertung {period_label}\n\n{body}\n"


class SelfReviewJournal:
    """Das einsehbare Selbstbewertungs-Journal: ein Markdown je Erstelltag."""

    def __init__(self, base_dir: Path):
        self._dir = Path(base_dir) / "self_reviews"

    def _file_for(self, day: date) -> Path:
        return self._dir / f"{day.isoformat()}.md"

    def write(self, day: date, text: str) -> None:
        if not text or not text.strip():
            return
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._file_for(day).write_text(text, encoding="utf-8")
        except OSError:
            logger.warning("Selbstbewertung: Schreiben fehlgeschlagen (ignoriert).", exc_info=True)

    def read(self, day: date) -> str:
        try:
            return self._file_for(day).read_text(encoding="utf-8")
        except OSError:
            return ""

    def latest(self) -> str:
        try:
            files = sorted(self._dir.glob("*.md"))
        except OSError:
            return ""
        return files[-1].read_text(encoding="utf-8") if files else ""
