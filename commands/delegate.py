"""
Repo-Analyse delegieren (ADR-033 Delegationsprozess, ADR-034 read-only
Repo-Analyse, ADR-035 asynchron + Telegram-Push).

Auf "analysiere <repo>: <Frage>" startet Jarvis das Agenten-Backend
(core/agent_backend.py, ueber configure() injiziert - die Fachlogik nennt
kein konkretes Backend, ADR-036) read-only im allowlisteten Repo, laesst die
Analyse laufen (lokal synchron, ueber den Runtime-Telegram-Kanal asynchron mit
Ergebnis-Push), legt das vollstaendige Ergebnis als reviewbares Artefakt unter
<memory_dir>/delegations/<zeitstempel>.md ab und traegt eine
Kurz-Zusammenfassung vor. Sicherheitsstufe 0 (keine System-/Repo-Aenderung),
konsistent mit search_web/check_mail.

Guardrails (ADR-034): Read-only auf Agenten-Ebene erzwungen (nur Read/Grep/
Glob), keinerlei git-Operation, Repo-Allowlist fail-closed, harter
Wall-Clock-Timeout, vollstaendiges Logging (Repo · Frage · Backend · Dauer ·
Status ✓/✗ · Kosten). Trust Boundary: das Ergebnis ist rein informativ und
loest nie selbst eine Aktion aus. Datenschutz: die Analyse kann Code-
Ausschnitte enthalten - sie bleibt lokal (Scheibe 1, kein Remote-Kanal).

configure()-Muster wie commands/mail.py: die Registry instanziiert Commands
vor Config.load(), deshalb ein Einmal-Aufruf beim Start (main.py/
jarvis_runtime.py) statt Konstruktor-Injection. Das Backend wird dabei aus der
Verdrahtungsschicht injiziert (kein eingebauter Default) - so nennt die
Fachlogik kein konkretes Backend und Tests laufen ohne echten Agenten-Aufruf.

delegate_analysis ist ueber den Standalone-Bot (telegram_main.py) NICHT
erreichbar, sondern nur ueber den Runtime-Telegram-Kanal (der den Async-Worker
hat, ADR-035) - der synchrone Standalone-Bot wuerde bei einer Minuten-Analyse
den Event-Loop blockieren.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.agent_backend import AgentBackend, AgentLimits, AgentResult
from core.fileio import write_text_create_only
from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.delegate")

_allowlist: dict[str, Path] = {}
# Kein eingebauter Default (ADR-036): die Fachlogik nennt kein konkretes Backend.
# Das Backend wird ueber configure() aus der Verdrahtungsschicht (main.py/
# jarvis_runtime.py) injiziert - wie bei commands/plan.py.
_backend: Optional[AgentBackend] = None
_artifact_dir: Optional[Path] = None
_limits: AgentLimits = AgentLimits()
_configured: bool = False

# Laenge der Kurz-Zusammenfassung im gesprochenen/gedruckten Result. Das
# vollstaendige Ergebnis steht im Artefakt - der Kanal bekommt nur einen
# Anrisz + den Verweis darauf.
_SUMMARY_CHARS = 600


def configure(config, backend: Optional[AgentBackend] = None) -> None:
    """Von main.py/jarvis_runtime.py einmal beim Start aufgerufen. Baut die
    Repo-Allowlist aus config.agent_repos (fail-closed), das Artefakt-
    Verzeichnis unter memory_dir und die Limits. Tests rufen dies mit
    tmp_path-Config und einem Fake-Backend auf."""
    global _allowlist, _backend, _artifact_dir, _limits, _configured
    _allowlist = _build_allowlist(config)
    _artifact_dir = Path(config.memory_dir) / "delegations"
    _limits = AgentLimits(timeout_seconds=float(getattr(config, "agent_timeout", 300.0)))
    _backend = backend
    _configured = True


def _build_allowlist(config) -> dict[str, Path]:
    """Alias -> Pfad aus config.agent_repos. Fail-closed: Eintraege ohne
    alias/path oder mit nicht existierendem Pfad werden uebersprungen und
    laut geloggt (nur ein real vorhandenes, ausdruecklich gelistetes Repo
    ist delegierbar)."""
    allowlist: dict[str, Path] = {}
    for entry in getattr(config, "agent_repos", []) or []:
        alias = str(entry.get("alias", "")).strip().lower()
        raw_path = str(entry.get("path", "")).strip()
        if not alias or not raw_path:
            logger.warning("Agent-Repo-Eintrag uebersprungen: alias/path fehlt (%r).", entry)
            continue
        path = Path(raw_path)
        if not path.is_dir():
            logger.warning(
                "Agent-Repo '%s' uebersprungen: Pfad existiert nicht (%s).", alias, raw_path
            )
            continue
        allowlist[alias] = path
    return allowlist


def _require_configured() -> None:
    if not _configured or _backend is None:
        raise RuntimeError(
            "Repo-Analyse nicht konfiguriert - commands.delegate.configure(config, backend) "
            "muss beim Start mit einem Backend aufgerufen werden (siehe main.py)."
        )


def _extract(plan: Plan) -> tuple[str, str]:
    """Liefert (repo_alias, frage). Primaerquelle: plan.target (Alias) +
    plan.parameters['question'] (vom Planner befuellt, siehe core/ai.py).
    Fallback fuer den Fall, dass der Planner die Frage nicht separat
    ablegt: Text nach dem ersten ':' in raw_input."""
    alias = (plan.target or "").strip().lower()
    question = str(plan.parameters.get("question", "")).strip()
    if not question:
        raw = (plan.raw_input or "").strip()
        if ":" in raw:
            question = raw.split(":", 1)[1].strip()
    return alias, question


def _write_artifact(repo_alias: str, question: str, result: AgentResult) -> Optional[Path]:
    """Schreibt das vollstaendige Ergebnis als reviewbares Markdown-Artefakt.
    Ein Schreibfehler darf das Vortragen nicht verhindern (fail-safe) - er
    wird geloggt, und der Kanal bekommt trotzdem die Analyse."""
    if _artifact_dir is None:
        return None
    try:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        status_symbol = "✓" if result.ok else "✗"
        cost = f"{result.cost_usd:.4f} USD" if result.cost_usd is not None else "unbekannt"
        turns = result.num_turns if result.num_turns is not None else "unbekannt"
        header = (
            f"# Repo-Analyse: {repo_alias}\n\n"
            f"- **Frage:** {question}\n"
            f"- **Backend:** {_backend.name} (read-only)\n"
            f"- **Status:** {status_symbol} {result.detail}\n"
            f"- **Dauer:** {result.duration_seconds:.1f}s\n"
            f"- **Turns:** {turns}\n"
            f"- **Kosten:** {cost}\n"
            f"- **Zeitpunkt:** {datetime.now().isoformat(timespec='seconds')}\n\n"
            "---\n\n"
        )
        # create-only: nie ueberschreiben (Audit-Fix P2a).
        return write_text_create_only(
            _artifact_dir, f"{timestamp}.md", header + (result.text or "(kein Text)") + "\n"
        )
    except OSError as e:  # noqa: BLE001 - Dateisystem kann vielfaeltig scheitern
        logger.warning("Delegations-Artefakt konnte nicht geschrieben werden: %s", e)
        return None


def _summary(text: str) -> str:
    """Kurz-Anrisz des Ergebnisses fuer den Kanal (Vollversion steht im
    Artefakt). Bricht an einer Wortgrenze ab, nicht mitten im Wort."""
    clean = (text or "").strip()
    if len(clean) <= _SUMMARY_CHARS:
        return clean
    cut = clean[:_SUMMARY_CHARS].rsplit(" ", 1)[0]
    return f"{cut} …"


class DelegateAnalysisCommand:
    name = "delegate_analysis"
    description = (
        "Delegiert eine read-only Analyse eines lokalen Code-Repositorys an einen "
        "Agenten (z. B. 'analysiere jarvis: wie funktioniert der Executor?', "
        "'lass das Repo X analysieren: ...'). target = der Repo-Alias, "
        "parameters.question = die eigentliche Analysefrage. Sicherheitsstufe 0, "
        "read-only (kein Schreiben/Ausfuehren, keine git-Aenderung), liefert eine "
        "Analyse mit vollstaendigem Artefakt zum Review."
    )
    requires_confirmation = False  # Sicherheitsstufe 0 (reine Analyse, read-only)
    # Langlaufend (Minuten): die Runtime fuehrt diesen Command asynchron im
    # Hintergrund aus und pusht das Ergebnis (ADR-035). Auf der Konsole und
    # ueber execute() laeuft er weiterhin synchron.
    long_running = True

    def execute(self, plan: Plan) -> Result:
        """Synchroner Einstieg (Konsole/Executor) - kein Abbruch-Kanal."""
        return self._analyze(plan, cancel_event=None)

    def run_async(self, plan: Plan, cancel_event: Optional[threading.Event] = None) -> Result:
        """Asynchroner Einstieg der Runtime (ADR-035): identische Logik wie
        execute(), reicht aber den Kill-Switch (cancel_event) bis zum Backend
        durch. Die Runtime besitzt den Hintergrund-Thread und das Event."""
        return self._analyze(plan, cancel_event=cancel_event)

    def _analyze(self, plan: Plan, cancel_event: Optional[threading.Event]) -> Result:
        _require_configured()

        if not _allowlist:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=(
                    "Es ist noch kein Repo fuer die Analyse freigegeben. Bitte in config.json "
                    "unter 'agent_repos' einen Eintrag {\"alias\": ..., \"path\": ...} hinterlegen "
                    "(siehe README)."
                ),
            )

        repo_alias, question = _extract(plan)
        if not repo_alias:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=(
                    "Welches Repo soll ich analysieren? Bekannt sind: "
                    f"{', '.join(sorted(_allowlist)) or '(keine)'}."
                ),
            )
        if not question:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=f"Was genau soll ich an '{repo_alias}' analysieren?",
            )

        repo = _allowlist.get(repo_alias)
        if repo is None:
            # Fail-closed: nicht-allowlistete Pfade werden abgelehnt (ADR-034).
            logger.warning("Repo-Analyse abgelehnt: '%s' nicht in der Allowlist.", repo_alias)
            return Result(
                status=Status.FAILED,
                message=(
                    f"'{repo_alias}' ist nicht fuer die Analyse freigegeben. Bekannt sind: "
                    f"{', '.join(sorted(_allowlist))}."
                ),
            )

        logger.info("Repo-Analyse gestartet: repo=%s frage=%r backend=%s", repo_alias, question, _backend.name)
        result = _backend.analyze(repo, question, _limits, cancel_event)
        artifact = _write_artifact(repo_alias, question, result)

        logger.info(
            "Repo-Analyse beendet: repo=%s status=%s dauer=%.1fs turns=%s kosten=%s artefakt=%s",
            repo_alias,
            "✓" if result.ok else "✗",
            result.duration_seconds,
            result.num_turns,
            f"{result.cost_usd:.4f}" if result.cost_usd is not None else "?",
            artifact.name if artifact else "-",
        )

        if not result.ok:
            return Result(
                status=Status.FAILED,
                message=f"Die Analyse von '{repo_alias}' hat nicht geklappt: {result.detail}",
                data={"repo": repo_alias, "artifact": str(artifact) if artifact else None},
            )

        artifact_hint = f"\n\nVollstaendig abgelegt unter: {artifact}" if artifact else ""
        message = (
            f"Analyse von '{repo_alias}' fertig:\n\n{_summary(result.text)}{artifact_hint}"
        )
        return Result(
            status=Status.SUCCESS,
            message=message,
            data={
                "repo": repo_alias,
                "question": question,
                "artifact": str(artifact) if artifact else None,
                "num_turns": result.num_turns,
                "cost_usd": result.cost_usd,
            },
        )


# Registrierungspunkt - commands/__init__.py liest diese Liste beim Start ein.
COMMANDS = [DelegateAnalysisCommand()]
