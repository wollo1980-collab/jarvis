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
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.agent_backend import AgentBackend, AgentLimits
from core.config import BASE_DIR
from core.fileio import write_text_create_only
from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.plan")

_backend: Optional[AgentBackend] = None
_repo: Path = BASE_DIR
_proposals_dir: Optional[Path] = None
_limits: AgentLimits = AgentLimits()
_configured: bool = False

_SUMMARY_CHARS = 600

# Kuratierter Kontext (Kontext-Optimierung Stufe 1): Caps PRO Quelle UND ein
# Gesamt-Cap (PO-Auflage) - Token-Schutz gegen einen aufgeblaehten Prompt.
_RECENT_ADR_COUNT = 3
_CAP_PROJECT_STATE = 6000
_CAP_ADR = 3500
_CAP_CHANGELOG = 2500
_CAP_LOGBOOK = 2500
_CAP_TOTAL = 20000

# Der eigentliche Wert dieser Fähigkeit steckt im Prompt: Er zwingt zu einem
# konkreten, klein geschnittenen Schritt in fester Struktur, erlaubt aber
# ausdrücklich das ehrliche „kein sinnvoller Schritt" statt eines erzwungenen
# Vorschlags (Governance / Produktphilosophie).
_PLANNING_PROMPT = (
    "Du bist die Planungs-Fähigkeit von Jarvis. Ziel: den sinnvollsten NÄCHSTEN "
    "kleinen Entwicklungsschritt für das Jarvis-Projekt vorschlagen — nicht mehr.\n\n"
    "Der aktuelle Projektstand ist dir UNTEN bereits kuratiert mitgegeben "
    "(PROJECT_STATE.md, die 3 jüngsten ADRs aus docs/adr/, jüngste "
    "docs/CHANGELOG.md- und docs/logbook.md-Einträge). Stütze dich PRIMÄR auf "
    "diesen mitgegebenen Kontext und nur auf das, was dort wirklich steht. Lies "
    "nur dann zusätzlich selbst (Read/Grep/Glob), wenn es wirklich nötig ist - "
    "insbesondere docs/handbook/HANDBOOK.md für die Governance-Invariante, oder "
    "eine ältere ADR bei konkretem Verdacht.\n\n"
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


# --- Kuratierter Projektkontext (Kontext-Optimierung Stufe 1) -----------------
# Statt den Agenten das ganze Projekt explorieren zu lassen (~17 Turns), reicht
# Jarvis den relevanten Stand fertig kuratiert im Prompt mit - der Agent denkt
# dann darueber, statt zu suchen. Read-only; der Agent darf bei Bedarf nachlesen.
_ADR_RE = re.compile(r"ADR-(\d+)\.md$", re.IGNORECASE)


def _read_text_capped(path: Path, cap: int) -> str:
    """Liest eine Datei fail-safe und deckelt sie auf `cap` Zeichen (Kopf, da
    CHANGELOG/logbook neueste Eintraege zuerst fuehren). Nie ein harter Fehler:
    fehlt/klemmt die Datei, kommt eine Notiz statt eines Absturzes."""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return "(nicht lesbar)"
    if len(text) <= cap:
        return text
    return text[:cap] + " …[gekürzt]"


def _recent_adrs(adr_dir: Path, count: int) -> list:
    """Die `count` juengsten ADRs (nach Nummer im Dateinamen absteigend)."""
    numbered = []
    for p in adr_dir.glob("ADR-*.md"):
        m = _ADR_RE.search(p.name)
        if m:
            numbered.append((int(m.group(1)), p))
    numbered.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in numbered[:count]]


def _assemble_context(repo: Path) -> str:
    """Buendelt den relevanten Projektstand read-only als kuratierten Textblock:
    PROJECT_STATE (voll), die 3 juengsten ADRs, juengste CHANGELOG-/logbook-
    Eintraege. Jeder Block ist eindeutig mit seinem Repo-Pfad ueberschrieben
    (PO-Auflage); es gilt ein Cap PRO Quelle UND ein Gesamt-Cap (Token-Schutz)."""
    docs = repo / "docs"

    def _block(rel_path: str, content: str) -> str:
        return f"===== {rel_path} =====\n{content}"

    parts = [
        _block(
            "docs/PROJECT_STATE.md",
            _read_text_capped(docs / "PROJECT_STATE.md", _CAP_PROJECT_STATE),
        )
    ]
    for adr in _recent_adrs(docs / "adr", _RECENT_ADR_COUNT):
        parts.append(_block(f"docs/adr/{adr.name}", _read_text_capped(adr, _CAP_ADR)))
    parts.append(
        _block("docs/CHANGELOG.md", _read_text_capped(docs / "CHANGELOG.md", _CAP_CHANGELOG))
    )
    parts.append(
        _block("docs/logbook.md", _read_text_capped(docs / "logbook.md", _CAP_LOGBOOK))
    )

    assembled = "\n\n".join(parts).strip()
    if len(assembled) > _CAP_TOTAL:
        assembled = assembled[:_CAP_TOTAL] + "\n…[Gesamtkontext gekürzt]"
    return assembled


def _write_proposal(text: str) -> Optional[Path]:
    """Schreibt den Vorschlag additiv als neue Markdown-Datei. Neue Datei mit
    Zeitstempel - kein Überschreiben, kein Code, isoliert im memory_dir. Ein
    Schreibfehler darf das Vortragen nicht verhindern (fail-safe)."""
    if _proposals_dir is None:
        return None
    try:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        header = (
            f"<!-- Jarvis-Vorschlag, erstellt {datetime.now().isoformat(timespec='seconds')} "
            "- Entwurf zur Freigabe, nicht umgesetzt -->\n\n"
        )
        # create-only: nie eine bestehende Datei ueberschreiben (Audit-Fix P2a) -
        # sichert das explizite Versprechen "additiv, kein Ueberschreiben".
        return write_text_create_only(
            _proposals_dir, f"{timestamp}-plan-next-step.md", header + (text or "(kein Text)") + "\n"
        )
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
        question = (
            f"{_PLANNING_PROMPT}\n"
            "================ AKTUELLER PROJEKTKONTEXT "
            "(kuratiert, read-only) ================\n\n"
            f"{_assemble_context(_repo)}\n"
        )
        result = backend.analyze(_repo, question, _limits, cancel_event)

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
