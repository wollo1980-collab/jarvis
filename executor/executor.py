"""
Executor: führt eine geordnete Liste von Plänen (Schritten) aus.
Meldet für jeden Schritt ✓ (Erfolg), ✗ (Fehler) oder ? (Unsicher /
Rückfrage nötig) - siehe Handbook Kap. 5 (Executor-Regeln).

Trockenlauf-Prinzip (Handbook Kap. 10): bevor eine Aktion ausgeführt
wird, die eine Bestätigung braucht (Command.requires_confirmation),
zeigt der Executor den geplanten Schritt an und fragt nach. Ohne
Bestätigung wird die Aktion NICHT ausgeführt.

Sicherheitsstufen (Kap. 10): ein Command kann zusätzlich
`confirmation_phrase` setzen (Stufe 3 - "mehrfache/eindeutige
Bestätigung"). Dann reicht ein einfaches "ja" NICHT - der Nutzer muss
die exakte Phrase eintippen. Ohne `confirmation_phrase` gilt die
einfache Ja/Nein-Bestätigung (Stufe 2). Lesson Learned 2026-07-01:
ein einzelnes "ja" hat gereicht, um versehentlich einen echten
PC-Shutdown auszulösen - das war zu schwach für eine Stufe-3-Aktion.

Bei einem gescheiterten oder unsicheren Zwischenschritt bricht der
Executor die restlichen Schritte ab - keine Kettenreaktion auf Basis
eines Ergebnisses, dem nicht vertraut werden kann ("niemals raten,
sondern nachfragen").
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from commands import dispatch
from core.ai import AIEngine
from core.models import Message, Plan, Result, Status
from core.speech import SpeechEngine
from core.tool_manager import ToolManager

logger = logging.getLogger("jarvis.executor")

_CONFIRM_WORDS = {"ja", "j", "yes", "y"}


@dataclass
class ExecutionReport:
    """Sammelergebnis eines Executor-Laufs über 1..n Schritte."""

    results: list[Result] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return bool(self.results) and all(r.ok for r in self.results)

    def summary_lines(self) -> list[str]:
        """Formatierte Ausgabe: Chat-Antworten bleiben Freitext,
        Tool-Ergebnisse bekommen das Status-Symbol vorangestellt."""
        lines: list[str] = []
        for r in self.results:
            if not r.message:
                continue
            if r.data and r.data.get("chat"):
                lines.append(r.message)
            else:
                lines.append(f"{r.status.symbol} {r.message}")
        return lines


class Executor:
    def __init__(self, speech: SpeechEngine, ai: AIEngine, tool_manager: Optional[ToolManager] = None):
        self.speech = speech
        self.ai = ai
        self.tool_manager = tool_manager or ToolManager()

    def run(
        self,
        steps: list[Plan],
        history: list[Message] | None = None,
        long_term_summary: str = "",
    ) -> ExecutionReport:
        """Führt Schritte der Reihe nach aus. Bricht ab, sobald ein
        Schritt fehlschlägt oder eine Bestätigung verweigert wird.

        history wird 1:1 an ai.answer() für chat-Schritte durchgereicht,
        damit sich Jarvis auch bei Tool-Zwischenschritten weiterhin an
        das bisherige Gespräch erinnert. long_term_summary (v0.4,
        ADR-009) wird ebenso durchgereicht, damit Chat-Antworten auf
        zuvor gemerkte Fakten zurückgreifen können."""
        report = ExecutionReport()
        history = history or []

        if len(steps) > 1:
            preview = "; ".join(s.raw_input for s in steps)
            logger.info("Trockenlauf: %d Schritte geplant: %s", len(steps), preview)

        for step in steps:
            command = self.tool_manager.resolve(step)

            if command is None:
                result = dispatch(step)
                if result.data and result.data.get("chat"):
                    text = self.ai.answer(step.raw_input, history, long_term_summary)
                    result = Result(status=Status.SUCCESS, message=text, data={"chat": True})
                report.results.append(result)
                logger.info("Schritt '%s': %s", step.intent, result.status.symbol)
                if not result.ok:
                    break
                continue

            if getattr(command, "requires_confirmation", False) and not step.parameters.get(
                "confirmed"
            ):
                phrase = getattr(command, "confirmation_phrase", None)

                if phrase:
                    # Sicherheitsstufe 3: exakte Phrase statt einfachem Ja/Nein.
                    self.speech.say(
                        f"Ich würde jetzt ausführen: {step.raw_input!r}. Das ist eine "
                        f"kritische Aktion (Sicherheitsstufe 3). Bitte tippe zur "
                        f"Bestätigung genau: {phrase}"
                    )
                    answer = self.speech.listen().strip()
                    confirmed = answer == phrase
                else:
                    # Sicherheitsstufe 2: einfaches Ja/Nein reicht.
                    self.speech.say(f"Ich würde jetzt ausführen: {step.raw_input!r}. Bestätigen?")
                    answer = self.speech.listen().strip().lower()
                    confirmed = answer in _CONFIRM_WORDS

                if not confirmed:
                    result = Result(
                        status=Status.NEEDS_CLARIFICATION,
                        message="Abgebrochen - keine Bestätigung erhalten.",
                    )
                    report.results.append(result)
                    logger.info("Schritt '%s' abgebrochen: keine Bestätigung.", step.intent)
                    break
                step.parameters["confirmed"] = True

            try:
                result = command.execute(step)
            except Exception as e:
                logger.exception("Command '%s' fehlgeschlagen", step.intent)
                result = Result(status=Status.FAILED, message=f"Fehler bei '{step.intent}': {e}")

            report.results.append(result)
            logger.info("Schritt '%s': %s %s", step.intent, result.status.symbol, result.message)

            if not result.ok:
                break

        return report
