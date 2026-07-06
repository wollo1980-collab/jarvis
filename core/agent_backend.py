"""
Agenten-Backend-Kontrakt + erste Implementierung (Claude Code CLI).
Erster Baustein des Agenten-Arms (ADR-033 Delegationsprozess, ADR-034
read-only Repo-Analyse, Umsetzungs-Scheibe 1: lokal & synchron).

Aufbau bewusst analog core/providers.py (LLMProvider): das Protokoll
`AgentBackend` und seine erste Implementierung `ClaudeCodeBackend` liegen
in einer Datei. Ein Agent ist eine neue Tool-Klasse, kein Parallelsystem
(ADR-033) - deshalb ist der Kontrakt klein und austauschbar: Codex/GPT
folgen spaeter hinter demselben `analyze()`-Vertrag, ohne dass der
Command-Layer (commands/delegate.py) sich aendert.

Sicherheit (ADR-034 Guardrails):
- Read-only ist im Print-Modus (`claude -p`) nicht verhandelbar: nur
  `Read`/`Grep`/`Glob` werden erlaubt (`--allowedTools`). Ohne Bash/Edit/
  Write ist keinerlei git-Operation moeglich (kein Branch/Commit/Push).
- Der harte Guardrail ist der Wall-Clock-Timeout: laeuft der Subprozess
  laenger als `AgentLimits.timeout_seconds`, wird er hart gekillt
  (Kill-Switch). Ein CLI-`--max-turns`-Flag existiert in der genutzten
  `claude`-Version (2.1.201) NICHT - Turn-/Kostendeckel werden deshalb
  nicht vorab erzwungen, sondern aus dem JSON-Ergebnis (`num_turns`,
  `total_cost_usd`) nur protokolliert (Observability).
- Keine stillen Fehler: Timeout, Exit != 0, is_error und nicht parsebares
  JSON fuehren alle zu ok=False mit klarem `detail`.

Auth (ADR-034 §6): Der Subprozess erbt den vorhandenen Account-Login
(~/.claude). Dieses Backend liest selbst KEIN Secret und setzt keinen
API-Key - der spaetere dedizierte ANTHROPIC_API_KEY (Env, ADR-018) ist die
dokumentierte Robustheits-Aufwertung fuer den unbeaufsichtigten Betrieb.
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

logger = logging.getLogger("jarvis.agent_backend")

# Name des CLI-Binaries (kein Magic Value im Aufrufcode). Auf dem PATH
# erwartet; Auth traegt ueber den Account-Login (~/.claude).
CLAUDE_BINARY = "claude"

# Read-only erzwungen: ausschliesslich lesende Tools. Ohne Bash/Edit/Write
# ist keine System-/Repo-Aenderung und keine git-Operation moeglich.
READ_ONLY_TOOLS = ("Read", "Grep", "Glob")


@dataclass
class AgentLimits:
    """Harte Grenzen fuer einen Agentenlauf. In Scheibe 1 nur der
    Wall-Clock-Timeout (Subprozess-Kill) - er ist der einzige vorab
    erzwingbare Guardrail (kein CLI-Turn-/Kostendeckel verfuegbar)."""

    timeout_seconds: float = 300.0


@dataclass
class AgentResult:
    """Ergebnis eines Agentenlaufs - rein informativ (Trust Boundary:
    loest nie selbst eine Aktion aus). num_turns/cost_usd sind, soweit vom
    Backend geliefert, fuer Logging und Artefakt gedacht (Observability),
    nicht fuer eine Steuerungsentscheidung."""

    text: str
    ok: bool
    duration_seconds: float
    detail: str = ""
    num_turns: Optional[int] = None
    cost_usd: Optional[float] = None


class AgentBackend(Protocol):
    """Rohschnittstelle der Delegation: Repo + Frage rein, Ergebnis raus.
    Read-only ist Teil des Vertrags - eine Implementierung MUSS das
    Schreiben/Ausfuehren im Ziel-Repo ausschliessen."""

    def analyze(self, repo: Path, question: str, limits: AgentLimits) -> AgentResult:
        ...


class ClaudeCodeBackend:
    """Erste AgentBackend-Implementierung: startet `claude -p` als
    Subprozess im Ziel-Repo, read-only erzwungen. Der Runner ist
    injizierbar (Default: subprocess.run), damit Tests ohne echten
    `claude`-Aufruf/Netzwerk laufen (gleiches Muster wie ein injizierter
    reader/searcher in den bestehenden Commands)."""

    def __init__(self, runner=subprocess.run, binary: str = CLAUDE_BINARY):
        self._run = runner
        self._binary = binary

    def _build_argv(self, repo: Path, question: str) -> list[str]:
        """Baut die Kommandozeile. Read-only ueber --allowedTools; das Ziel-
        Repo wird ueber --add-dir freigegeben und ist zusaetzlich das cwd."""
        return [
            self._binary,
            "-p",
            question,
            "--allowedTools",
            *READ_ONLY_TOOLS,
            "--output-format",
            "json",
            "--add-dir",
            str(repo),
        ]

    def analyze(self, repo: Path, question: str, limits: AgentLimits) -> AgentResult:
        argv = self._build_argv(repo, question)
        started = time.monotonic()
        try:
            completed = self._run(
                argv,
                cwd=str(repo),
                capture_output=True,
                text=True,
                # claude -p gibt UTF-8 aus. Ohne explizites encoding dekodiert
                # subprocess unter Windows mit der locale-Codepage (cp1252) und
                # zerschiesst Umlaute/Pfeile (Live-Fund Rauchtest 2026-07-06:
                # "ausfuehrt" -> "ausfÃ¼hrt"). errors="replace" haelt den Lauf am
                # Leben, falls doch ein nicht dekodierbares Byte auftaucht.
                encoding="utf-8",
                errors="replace",
                timeout=limits.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - started
            logger.warning(
                "Agentenlauf abgebrochen: Zeitlimit %.0fs ueberschritten (Repo %s).",
                limits.timeout_seconds,
                repo,
            )
            return AgentResult(
                text="",
                ok=False,
                duration_seconds=duration,
                detail=f"Zeitlimit ({limits.timeout_seconds:.0f}s) ueberschritten - Lauf abgebrochen.",
            )
        except FileNotFoundError:
            duration = time.monotonic() - started
            return AgentResult(
                text="",
                ok=False,
                duration_seconds=duration,
                detail=(
                    f"Agenten-Backend '{self._binary}' nicht gefunden (nicht im PATH). "
                    "Claude Code muss installiert und angemeldet sein (ADR-034)."
                ),
            )

        duration = time.monotonic() - started
        return self._parse(completed, duration)

    def _parse(self, completed, duration: float) -> AgentResult:
        """Uebersetzt das Subprozess-Ergebnis in ein AgentResult. Keine
        stillen Fehler: Exit != 0, is_error und nicht parsebares JSON werden
        klar als ok=False mit `detail` gemeldet."""
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()

        if completed.returncode != 0:
            detail = stderr or stdout or f"Exit-Code {completed.returncode}"
            return AgentResult(
                text=stdout,
                ok=False,
                duration_seconds=duration,
                detail=f"Agentenlauf fehlgeschlagen: {detail}",
            )

        try:
            data = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            # Kein/kaputtes JSON trotz Exit 0 -> Rohtext behalten, aber ehrlich
            # als unsicher markieren (kein stiller Erfolg).
            return AgentResult(
                text=stdout,
                ok=False,
                duration_seconds=duration,
                detail="Antwort des Agenten war kein gueltiges JSON.",
            )

        is_error = bool(data.get("is_error", False))
        text = (data.get("result") or "").strip()
        num_turns = data.get("num_turns")
        cost = data.get("total_cost_usd")

        if is_error or not text:
            return AgentResult(
                text=text,
                ok=False,
                duration_seconds=duration,
                detail=data.get("subtype") or "Agent meldete einen Fehler oder lieferte keinen Text.",
                num_turns=num_turns if isinstance(num_turns, int) else None,
                cost_usd=float(cost) if isinstance(cost, (int, float)) else None,
            )

        return AgentResult(
            text=text,
            ok=True,
            duration_seconds=duration,
            detail=data.get("subtype", "success"),
            num_turns=num_turns if isinstance(num_turns, int) else None,
            cost_usd=float(cost) if isinstance(cost, (int, float)) else None,
        )
