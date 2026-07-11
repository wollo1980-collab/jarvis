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

Optionaler preview()-Hook (v0.7 Phase 4, ADR-023): ein Command kann
zusaetzlich eine Methode preview(plan) -> Optional[str] implementieren.
Ist sie vorhanden, wird ihr Ergebnis vor der Bestaetigungsfrage
angezeigt (z. B. eine frisch gescannte Zusammenfassung bei
clean_temp_files). Commands OHNE preview() verhalten sich exakt wie
zuvor - kein Zugriff auf SpeechEngine fuer Commands, die Anzeige
bleibt vollstaendig Aufgabe des Executors.
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


def request_confirmation(speech, command, step: Plan) -> bool:
    """Holt die Stufe-2/3-Bestaetigung fuer einen Schritt ein - genutzt vom
    sequenziellen Executor-Pfad UND vom Async-Zweig der Runtime.

    Sicherheits-Befund 2026-07-10: der Async-Dispatch (_dispatch_delegation,
    ADR-035) rief run_async() DIREKT auf und umging requires_confirmation
    komplett - bei delegate_analysis (Stufe 0) folgenlos, bei delegate_work
    (Stufe 2, ADR-050) eine echte Luecke, die live nur der Sauberer-Baum-
    Waechter abgefangen hat. Deshalb lebt die Bestaetigungslogik jetzt in
    genau EINER Funktion, die beide Pfade nutzen. True = bestaetigt."""
    phrase = getattr(command, "confirmation_phrase", None)

    # Optionaler preview()-Hook (ADR-023): nur aufrufen, wenn das Command ihn
    # tatsaechlich implementiert - liefert er nichts, bleibt der Text nackt.
    preview_fn = getattr(command, "preview", None)
    preview_text = preview_fn(step) if callable(preview_fn) else None

    # Die Rueckfrage nennt die AKTION (Intent + Ziel), nicht die Roheingabe
    # (Nutzungslauf-Befund 2026-07-10) - Fehl-Routings werden sichtbar.
    target = (step.target or "").strip()
    action = f"{step.intent} ({target})" if target else step.intent
    announcement = f"Ich würde jetzt ausführen: {action}."
    if preview_text:
        announcement = f"{announcement} {preview_text}"

    if phrase:
        # Sicherheitsstufe 3: exakte Phrase statt einfachem Ja/Nein.
        speech.say(
            f"{announcement} Das ist eine kritische Aktion (Sicherheitsstufe 3). "
            f"Bitte tippe zur Bestätigung genau: {phrase}"
        )
        return speech.listen().strip() == phrase
    # Sicherheitsstufe 2: einfaches Ja/Nein reicht.
    speech.say(f"{announcement} Bestätigen?")
    return speech.listen().strip().lower() in _CONFIRM_WORDS


def _notify_step(on_step, phase: str, index: int, step: Plan, result: Optional[Result] = None) -> None:
    """Fortschritts-Callback (Live-Ablauf-Timeline 2026-07-10) - Beiwerk:
    ein kaputter Callback darf die Ausfuehrung nie stoeren."""
    if on_step is None:
        return
    try:
        on_step(phase, index, step, result)
    except Exception:  # noqa: BLE001
        logger.debug("on_step-Callback fehlgeschlagen.", exc_info=True)


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
        on_step=None,
    ) -> ExecutionReport:
        """Führt Schritte der Reihe nach aus. Bricht ab, sobald ein
        Schritt fehlschlägt oder eine Bestätigung verweigert wird.

        history wird 1:1 an ai.answer() für chat-Schritte durchgereicht,
        damit sich Jarvis auch bei Tool-Zwischenschritten weiterhin an
        das bisherige Gespräch erinnert. long_term_summary (v0.4,
        ADR-009) wird ebenso durchgereicht, damit Chat-Antworten auf
        zuvor gemerkte Fakten zurückgreifen können.

        on_step (optional, Live-Ablauf 2026-07-10): Fortschritts-Callback
        on_step(phase, index, step, result) mit phase "start" (Arbeit am
        Schritt beginnt - nach einer etwaigen Bestätigung) und "done"
        (Ergebnis liegt vor). Vorher meldete die Timeline Schritte erst
        NACH Abschluss aller Schritte - "man sieht nicht, dass er
        arbeitet" (PO-Befund)."""
        report = ExecutionReport()
        history = history or []

        if len(steps) > 1:
            preview = "; ".join(s.raw_input for s in steps)
            logger.info("Trockenlauf: %d Schritte geplant: %s", len(steps), preview)

        for index, step in enumerate(steps):
            command = self.tool_manager.resolve(step)

            if command is None:
                _notify_step(on_step, "start", index, step)
                result = dispatch(step)
                if result.data and result.data.get("chat"):
                    text = self.ai.answer(step.raw_input, history, long_term_summary)
                    result = Result(status=Status.SUCCESS, message=text, data={"chat": True})
                _notify_step(on_step, "done", index, step, result)
                report.results.append(result)
                logger.info("Schritt '%s': %s", step.intent, result.status.symbol)
                if not result.ok:
                    break
                continue

            if getattr(command, "requires_confirmation", False) and not step.parameters.get(
                "confirmed"
            ):
                if not request_confirmation(self.speech, command, step):
                    result = Result(
                        status=Status.NEEDS_CLARIFICATION,
                        message="Abgebrochen - keine Bestätigung erhalten.",
                    )
                    report.results.append(result)
                    logger.info("Schritt '%s' abgebrochen: keine Bestätigung.", step.intent)
                    break
                step.parameters["confirmed"] = True

            # "start" bewusst NACH der Bestätigung: solange die Rückfrage
            # offen ist, arbeitet niemand (Orb: wartet, Timeline: offen).
            _notify_step(on_step, "start", index, step)
            try:
                result = command.execute(step)
            except Exception as e:
                logger.exception("Command '%s' fehlgeschlagen", step.intent)
                result = Result(status=Status.FAILED, message=f"Fehler bei '{step.intent}': {e}")

            _notify_step(on_step, "done", index, step, result)
            report.results.append(result)
            logger.info("Schritt '%s': %s %s", step.intent, result.status.symbol, result.message)

            if not result.ok:
                break

        return report
