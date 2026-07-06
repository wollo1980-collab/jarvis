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
import threading
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

# Poll-Intervall der Warteschleife (Sekunden): so oft werden cancel_event und
# das Gesamt-Timeout geprueft, waehrend der claude-Prozess laeuft. Klein genug
# fuer einen zuegigen Abbruch, gross genug fuer vernachlaessigbare CPU-Last.
_POLL_INTERVAL_SECONDS = 0.2


@dataclass
class AgentLimits:
    """Harte Grenzen fuer einen Agentenlauf: der Wall-Clock-Timeout
    (Subprozess-Kill) ist der einzige vorab erzwingbare Guardrail (kein
    CLI-Turn-/Kostendeckel verfuegbar). Ergaenzt wird er zur Laufzeit durch
    den optionalen cancel_event (Kill-Switch der Runtime, ADR-035)."""

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
    Schreiben/Ausfuehren im Ziel-Repo ausschliessen. cancel_event (optional,
    ADR-035) erlaubt der Runtime, einen laufenden Agentenlauf hart
    abzubrechen (Kill-Switch)."""

    def analyze(
        self,
        repo: Path,
        question: str,
        limits: AgentLimits,
        cancel_event: "Optional[threading.Event]" = None,
    ) -> AgentResult:
        ...


class ClaudeCodeBackend:
    """Erste AgentBackend-Implementierung: startet `claude -p` als
    Subprozess im Ziel-Repo, read-only erzwungen. Statt `subprocess.run`
    wird `subprocess.Popen` genutzt, damit ein laufender Prozess auf
    cancel_event/Timeout hin hart beendet werden kann (Kill-Switch der
    Runtime, ADR-035) - ohne Popen wuerde `runtime.stop()` bis zum Timeout
    (bis 300 s) haengen. Die Popen-Factory ist injizierbar, damit Tests ohne
    echten `claude`-Aufruf/Netzwerk laufen (gleiches Muster wie ein
    injizierter reader/searcher in den bestehenden Commands)."""

    def __init__(self, popen=subprocess.Popen, binary: str = CLAUDE_BINARY):
        self._popen = popen
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

    def analyze(
        self,
        repo: Path,
        question: str,
        limits: AgentLimits,
        cancel_event: Optional[threading.Event] = None,
    ) -> AgentResult:
        argv = self._build_argv(repo, question)
        started = time.monotonic()
        try:
            proc = self._popen(
                argv,
                cwd=str(repo),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                # claude -p gibt UTF-8 aus. Ohne explizites encoding dekodiert
                # subprocess unter Windows mit der locale-Codepage (cp1252) und
                # zerschiesst Umlaute/Pfeile (Live-Fund Rauchtest 2026-07-06:
                # "ausfuehrt" -> "ausfÃ¼hrt"). errors="replace" haelt den Lauf am
                # Leben, falls doch ein nicht dekodierbares Byte auftaucht.
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            return AgentResult(
                text="",
                ok=False,
                duration_seconds=time.monotonic() - started,
                detail=(
                    f"Agenten-Backend '{self._binary}' nicht gefunden (nicht im PATH). "
                    "Claude Code muss installiert und angemeldet sein (ADR-034)."
                ),
            )

        return self._wait(proc, repo, limits, cancel_event, started)

    def _wait(
        self,
        proc,
        repo: Path,
        limits: AgentLimits,
        cancel_event: Optional[threading.Event],
        started: float,
    ) -> AgentResult:
        """Wartet auf den Prozess und setzt die Abbruch-Praezedenz durch:
        **natuerlicher Abschluss > Cancel > Timeout**. Ist der Prozess in
        einer Iteration bereits fertig, gewinnt sein Ergebnis (die Arbeit ist
        getan). Laeuft er noch, wird zuerst cancel_event, dann das
        Gesamt-Timeout geprueft - jeweils genau ein gemeldeter Grund, kein
        Zombie-Prozess."""
        while True:
            try:
                stdout, stderr = proc.communicate(timeout=_POLL_INTERVAL_SECONDS)
            except subprocess.TimeoutExpired:
                # Prozess laeuft noch: Cancel hat Vorrang vor Timeout.
                if cancel_event is not None and cancel_event.is_set():
                    return self._terminate(
                        proc, started, "Analyse abgebrochen - Lauf gestoppt."
                    )
                if (time.monotonic() - started) >= limits.timeout_seconds:
                    logger.warning(
                        "Agentenlauf abgebrochen: Zeitlimit %.0fs ueberschritten (Repo %s).",
                        limits.timeout_seconds,
                        repo,
                    )
                    return self._terminate(
                        proc,
                        started,
                        f"Zeitlimit ({limits.timeout_seconds:.0f}s) ueberschritten - Lauf abgebrochen.",
                    )
                continue
            # Natuerlicher Abschluss - gewinnt auch, falls gleichzeitig ein
            # Cancel eintraf (das Ergebnis liegt bereits vor).
            return self._parse_output(
                proc.returncode, stdout, stderr, time.monotonic() - started
            )

    def _terminate(self, proc, started: float, detail: str) -> AgentResult:
        """Killt den laufenden Prozess und leert die Pipes (kein Zombie)."""
        try:
            proc.kill()
            proc.communicate(timeout=_POLL_INTERVAL_SECONDS)
        except Exception:  # noqa: BLE001 - Aufraeumen darf nie selbst scheitern
            logger.debug("Aufraeumen nach kill() unvollstaendig.", exc_info=True)
        return AgentResult(
            text="", ok=False, duration_seconds=time.monotonic() - started, detail=detail
        )

    def _parse_output(
        self, returncode: int, stdout: str, stderr: str, duration: float
    ) -> AgentResult:
        """Uebersetzt das Subprozess-Ergebnis in ein AgentResult. Keine
        stillen Fehler: Exit != 0, is_error und nicht parsebares JSON werden
        klar als ok=False mit `detail` gemeldet."""
        stdout = (stdout or "").strip()
        stderr = (stderr or "").strip()

        if returncode != 0:
            detail = stderr or stdout or f"Exit-Code {returncode}"
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
