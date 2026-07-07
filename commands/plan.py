"""
Nächsten Entwicklungsschritt planen (erste Orchestrierungs-Kette, ADR-036 /
Handbook 4.2 „Governance-Invariante").

Auf „plane den nächsten Schritt" / „bereite die nächste Scheibe vor" liest Jarvis
den eigenen Projektstand (PROJECT_STATE, Handbook, jüngste ADRs, CHANGELOG,
logbook, offene TODOs) **read-only** über das Agenten-Backend und lässt daraus
EINEN konkreten, klein geschnittenen nächsten Schritt vorschlagen — mit
Begründung, Risiken und einer Governance-/ADR-Konfliktprüfung, in fester Struktur.
Den Entwurf schreibt Jarvis anschließend **selbst** additiv als Markdown in
`<memory_dir>/proposals/` und legt ihn zur Freigabe vor.

Sicherheitsstufe 0. Der Agent bleibt strikt read-only (kein Write/Bash); die
einzige Schreibaktion macht dieser Command (vertrauenswürdiger Code) an genau
einen isolierten Ort — „additiv, kein Überschreiben, kein Code" ist damit
strukturell garantiert, ohne dem Agenten Schreibmacht zu geben. Jarvis schlägt
nur vor; er setzt nichts eigenmächtig um (Handbook 4.2).

Modellunabhängigkeit (ADR-036): Diese Fachlogik nennt KEIN konkretes Backend/
Modell. Das Backend wird über configure() aus der Verdrahtungsschicht (main.py/
jarvis_runtime.py) injiziert.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.agent_backend import AgentBackend, AgentLimits
from core.config import BASE_DIR
from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.plan")

_backend: Optional[AgentBackend] = None
_repo: Path = BASE_DIR
_proposals_dir: Optional[Path] = None
_limits: AgentLimits = AgentLimits()
_configured: bool = False

_SUMMARY_CHARS = 600

# Der eigentliche Wert dieser Fähigkeit steckt im Prompt: Er zwingt zu einem
# konkreten, klein geschnittenen Schritt in fester Struktur, erlaubt aber
# ausdrücklich das ehrliche „kein sinnvoller Schritt" statt eines erzwungenen
# Vorschlags (Governance / Produktphilosophie).
_PLANNING_PROMPT = (
    "Du bist die Planungs-Fähigkeit von Jarvis. Ziel: den sinnvollsten NÄCHSTEN "
    "kleinen Entwicklungsschritt für das Jarvis-Projekt vorschlagen — nicht mehr.\n\n"
    "Lies dazu zuerst selbst den Projektstand im aktuellen Repo (nutze Read/Grep/"
    "Glob): PROJECT_STATE.md, docs/handbook/HANDBOOK.md, die jüngsten Dateien in "
    "docs/adr/, docs/CHANGELOG.md, docs/logbook.md sowie die offenen Aufgaben/TODOs. "
    "Stütze dich nur auf das, was dort wirklich steht.\n\n"
    "WICHTIG - ehrlich bleiben: Wenn sich nach der Analyse KEIN klar begründbarer "
    "kleiner nächster Schritt zeigt, sage das ausdrücklich und begründe es "
    "(Empfehlung: 'Ich sehe aktuell keinen klar begründbaren nächsten Schritt.') - "
    "erzwinge NIEMALS einen Vorschlag. Ein ehrliches 'nichts Dringendes' ist ein "
    "gültiges Ergebnis.\n\n"
    "Schlage höchstens EINEN Schritt vor, klein geschnitten und reviewbar "
    "(keine Roadmap, keine Sammelpakete). Prüfe ausdrücklich auf Widersprüche zu "
    "bestehenden ADRs und zur Governance-Invariante des Handbooks.\n\n"
    "Antworte auf Deutsch als Markdown mit GENAU diesen Abschnitten, in dieser "
    "Reihenfolge:\n"
    "# <Titel>\n"
    "## Kurzfassung\n"
    "## Warum jetzt?\n"
    "## Vorgeschlagener Umfang\n"
    "## Begründung\n"
    "## Risiken\n"
    "## Governance-/ADR-Prüfung\n"
    "## Offene Fragen\n"
    "## Empfehlung\n"
)


def configure(config, backend: Optional[AgentBackend] = None) -> None:
    """Von main.py/jarvis_runtime.py einmal beim Start aufgerufen. Das Backend
    wird injiziert (Adapterschicht) - diese Fachlogik kennt kein konkretes
    Backend (ADR-036). Tests rufen dies mit tmp_path-Config und Fake-Backend auf."""
    global _backend, _repo, _proposals_dir, _limits, _configured
    _backend = backend
    _repo = BASE_DIR
    _proposals_dir = Path(config.memory_dir) / "proposals"
    _limits = AgentLimits(timeout_seconds=float(getattr(config, "agent_timeout", 300.0)))
    _configured = True


def _require_configured() -> AgentBackend:
    if not _configured or _backend is None:
        raise RuntimeError(
            "plan_next_step nicht konfiguriert - commands.plan.configure(config, backend) "
            "muss beim Start aufgerufen werden (siehe main.py)."
        )
    return _backend


def _summary(text: str) -> str:
    clean = (text or "").strip()
    if len(clean) <= _SUMMARY_CHARS:
        return clean
    return f"{clean[:_SUMMARY_CHARS].rsplit(' ', 1)[0]} …"


def _write_proposal(text: str) -> Optional[Path]:
    """Schreibt den Vorschlag additiv als neue Markdown-Datei. Neue Datei mit
    Zeitstempel - kein Überschreiben, kein Code, isoliert im memory_dir. Ein
    Schreibfehler darf das Vortragen nicht verhindern (fail-safe)."""
    if _proposals_dir is None:
        return None
    try:
        _proposals_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = _proposals_dir / f"{timestamp}-plan-next-step.md"
        header = (
            f"<!-- Jarvis-Vorschlag, erstellt {datetime.now().isoformat(timespec='seconds')} "
            "- Entwurf zur Freigabe, nicht umgesetzt -->\n\n"
        )
        path.write_text(header + (text or "(kein Text)") + "\n", encoding="utf-8")
        return path
    except OSError as e:  # noqa: BLE001 - Dateisystem kann vielfaeltig scheitern
        logger.warning("Vorschlags-Entwurf konnte nicht geschrieben werden: %s", e)
        return None


class PlanNextStepCommand:
    name = "plan_next_step"
    description = (
        "Erstellt einen Vorschlag für den nächsten kleinen Entwicklungsschritt am "
        "Jarvis-Projekt (liest read-only PROJECT_STATE, Handbook, ADRs, CHANGELOG "
        "und logbook, empfiehlt EINEN Schritt mit Begründung, Risiken und "
        "ADR-Konfliktprüfung, legt einen Entwurf ab). Sicherheitsstufe 0. "
        "Trigger z. B. 'plane den nächsten Schritt', 'bereite die nächste Scheibe "
        "vor', 'was sollten wir als Nächstes umsetzen'. Setzt nichts um - Jarvis "
        "schlägt nur vor."
    )
    requires_confirmation = False  # Sicherheitsstufe 0 (nur lesen + Vorschlag ablegen)
    # Langlaufend: die Runtime führt den Schritt asynchron im Hintergrund aus und
    # pusht das Ergebnis (ADR-035). Konsole/execute laufen synchron.
    long_running = True

    def execute(self, plan: Plan) -> Result:
        return self._prepare(plan, cancel_event=None)

    def run_async(self, plan: Plan, cancel_event: Optional[threading.Event] = None) -> Result:
        return self._prepare(plan, cancel_event=cancel_event)

    def _prepare(self, plan: Plan, cancel_event: Optional[threading.Event]) -> Result:
        backend = _require_configured()

        logger.info("Nächster-Schritt-Planung gestartet (Repo %s).", _repo)
        result = backend.analyze(_repo, _PLANNING_PROMPT, _limits, cancel_event)

        if not result.ok:
            logger.info("Planung fehlgeschlagen: %s", result.detail)
            return Result(
                status=Status.FAILED,
                message=f"Ich konnte den nächsten Schritt nicht vorbereiten: {result.detail}",
            )

        artifact = _write_proposal(result.text)
        logger.info(
            "Planung fertig: dauer=%.1fs turns=%s artefakt=%s",
            result.duration_seconds,
            result.num_turns,
            artifact.name if artifact else "-",
        )

        hint = f"\n\nEntwurf abgelegt unter: {artifact}" if artifact else ""
        return Result(
            status=Status.SUCCESS,
            message=f"Vorschlag für den nächsten Schritt:\n\n{_summary(result.text)}{hint}",
            data={"artifact": str(artifact) if artifact else None, "num_turns": result.num_turns},
        )


# Registrierungspunkt - commands/__init__.py liest diese Liste beim Start ein.
COMMANDS = [PlanNextStepCommand()]
