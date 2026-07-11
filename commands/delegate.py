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

import json
import logging
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.agent_backend import AgentBackend, AgentLimits, AgentResult
from core.fileio import read_text_capped, write_text_create_only
from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.delegate")

_allowlist: dict[str, Path] = {}
# Schreib-Kaefig (ADR-050): EIGENE Allowlist, getrennt von der Lese-Liste -
# dass ein Repo analysiert werden darf, heisst nie, dass darin geschrieben
# werden darf. Fail-closed: leer = keine schreibende Delegation moeglich.
_write_allowlist: dict[str, Path] = {}
# Kein eingebauter Default (ADR-036): die Fachlogik nennt kein konkretes Backend.
# Das Backend wird ueber configure() aus der Verdrahtungsschicht (main.py/
# jarvis_runtime.py) injiziert - wie bei commands/plan.py.
_backend: Optional[AgentBackend] = None
# AI-Engine fuer project_continue (Stufe 2 der Projektentwickler-Kampagne):
# baut aus dem Projektstand den Delegations-Auftrag. Optional injiziert -
# ohne sie bleibt project_continue ehrlich funktionsunfaehig (fail-closed),
# delegate_analysis/delegate_work laufen unveraendert.
_ai = None
_artifact_dir: Optional[Path] = None
_limits: AgentLimits = AgentLimits()
# Warnschwelle je Agentenlauf (ADR-050). WICHTIG zur Einordnung (PO-Hinweis
# 2026-07-10): der Agent laeuft ueber das Claude-MAX-Abo - der von der CLI
# gemeldete Betrag ist ein GEGENWERT (API-Preis), die Grenzkosten sind 0.
# Die Schwelle ist ein AUSREISSER-WECKER: ein ungewoehnlich grosser Lauf
# frisst vor allem Session-Kontingent und war vermutlich ausser Kontrolle.
_cost_warn_usd: float = 2.0
_configured: bool = False
# Durchsicht (ADR-056): Rueckruf fuer die Schritt-Ereignisse des Agenten.
# None -> Stapel-Modus (kein Streaming). Von der Runtime gesetzt.
_event_sink = None
# Umlenken (ADR-056 Scheibe 3): bidirektionaler Draht der Runtime. Zusammen mit
# _event_sink laeuft die SCHREIBENDE Delegation interaktiv - der Nutzer kann den
# Agenten mitten im Lauf umlenken. None -> nicht interaktiv (Konsole/Tests).
_redirect_channel = None

# Laenge der Kurz-Zusammenfassung im gesprochenen/gedruckten Result. Das
# vollstaendige Ergebnis steht im Artefakt - der Kanal bekommt nur einen
# Anrisz + den Verweis darauf.
_SUMMARY_CHARS = 600


def configure(config, backend: Optional[AgentBackend] = None, ai=None, event_sink=None,
              redirect=None) -> None:
    """Von main.py/jarvis_runtime.py einmal beim Start aufgerufen. Baut die
    Repo-Allowlist aus config.agent_repos (fail-closed), das Artefakt-
    Verzeichnis unter memory_dir und die Limits. `ai` (AIEngine, optional)
    braucht nur project_continue - fehlt sie, faellt der Auftrag-Bau ehrlich
    aus. event_sink (optional, ADR-056 Durchsicht): Rueckruf, an den die
    Schritt-Ereignisse des Agenten gehen (Runtime leitet sie ins UI). Ohne
    event_sink laeuft der Agent im Stapel-Modus. Tests rufen dies mit
    tmp_path-Config und Fakes auf."""
    global _allowlist, _write_allowlist, _backend, _ai, _artifact_dir, _limits
    global _cost_warn_usd, _configured, _event_sink, _redirect_channel
    _allowlist = _build_allowlist(config)
    _write_allowlist = _build_allowlist(config, attr="agent_write_repos")
    _artifact_dir = Path(config.memory_dir) / "delegations"
    _limits = AgentLimits(timeout_seconds=float(getattr(config, "agent_timeout", 300.0)))
    _cost_warn_usd = float(getattr(config, "agent_cost_warn_usd", 2.0))
    _backend = backend
    _ai = ai
    _event_sink = event_sink
    _redirect_channel = redirect
    _configured = True


def _build_allowlist(config, attr: str = "agent_repos") -> dict[str, Path]:
    """Alias -> Pfad aus config.<attr> (agent_repos = lesend, ADR-034;
    agent_write_repos = schreibend, ADR-050). Fail-closed: Eintraege ohne
    alias/path oder mit nicht existierendem Pfad werden uebersprungen und
    laut geloggt (nur ein real vorhandenes, ausdruecklich gelistetes Repo
    ist delegierbar)."""
    allowlist: dict[str, Path] = {}
    for entry in getattr(config, attr, []) or []:
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


def _extract(plan: Plan, param: str = "question") -> tuple[str, str]:
    """Liefert (repo_alias, auftrag/frage). WORTLAUT schlaegt Paraphrase
    (Live-Befund 2026-07-10): der Planner KUERZT lange Auftraege beim
    Umschreiben in parameters - dem Agenten fehlte die halbe AP1-
    Spezifikation. Deshalb gewinnt der Text nach dem ersten ':' der
    Roheingabe, wenn er laenger ist als der Planner-Parameter; der
    Parameter bleibt Rueckfall fuer Formulierungen ohne Doppelpunkt."""
    alias = (plan.target or "").strip().lower()
    text = str(plan.parameters.get(param, "")).strip()
    raw = (plan.raw_input or "").strip()
    if ":" in raw:
        raw_text = raw.split(":", 1)[1].strip()
        if len(raw_text) > len(text):
            text = raw_text
    return alias, text


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
        result = _backend.analyze(repo, question, _limits, cancel_event, on_event=_event_sink)
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


# --- Schreibende Delegation im Kaefig (ADR-050, Kampagnen-Stufe 0) ---------

def _git(repo: Path, *args: str) -> str:
    """Nur-lesende git-Aufrufe fuer die Sichtung (status/diff). Fehler
    liefern einen Marker-Text statt zu werfen - die Sichtung darf nie am
    Diff-Werkzeug scheitern."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30,
        )
        if result.returncode != 0:
            return f"(git {' '.join(args)} fehlgeschlagen: {result.stderr.strip()})"
        return result.stdout
    except Exception as e:  # noqa: BLE001 - Sichtung bleibt fail-safe
        return f"(git nicht verfuegbar: {e})"


_MAX_NEW_FILE_PREVIEW_BYTES = 200_000


def _capture_changes(repo: Path) -> tuple[str, str]:
    """Liefert (status --porcelain, vollstaendiger Diff inkl. Inhalt neuer
    Dateien) - das reviewbare Herzstueck der PO-Sichtung (ADR-050).
    -uall: neue Dateien EINZELN statt als '?? verzeichnis/' (sonst fehlt
    ihr Inhalt im Diff-Artefakt)."""
    status = _git(repo, "status", "--porcelain", "-uall").strip()
    parts = []
    diff = _git(repo, "diff").strip()
    if diff:
        parts.append(diff)
    for line in status.splitlines():
        if not line.startswith("??"):
            continue
        rel = line[3:].strip()
        path = repo / rel
        try:
            if path.is_file() and path.stat().st_size <= _MAX_NEW_FILE_PREVIEW_BYTES:
                content = path.read_text(encoding="utf-8", errors="replace")
                parts.append(f"--- NEUE DATEI: {rel} ---\n{content}")
            else:
                parts.append(f"--- NEUE DATEI: {rel} (Inhalt nicht angezeigt: Verzeichnis/zu gross) ---")
        except OSError:
            parts.append(f"--- NEUE DATEI: {rel} (nicht lesbar) ---")
    return status, "\n\n".join(parts).strip()


def _write_work_artifact(
    repo_alias: str, task: str, result: AgentResult, status: str, diff: str
) -> Optional[Path]:
    """Diff-Artefakt der schreibenden Delegation - Grundlage der PO-Sichtung.
    Wird AUCH bei fehlgeschlagenem Lauf geschrieben (Ehrlichkeit: was wurde
    trotzdem angefasst?)."""
    if _artifact_dir is None:
        return None
    try:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        status_symbol = "✓" if result.ok else "✗"
        cost = f"{result.cost_usd:.4f} USD" if result.cost_usd is not None else "unbekannt"
        turns = result.num_turns if result.num_turns is not None else "unbekannt"
        header = (
            f"# Schreib-Delegation: {repo_alias}\n\n"
            f"- **Auftrag:** {task}\n"
            f"- **Backend:** {_backend.name} (Schreib-Kaefig, kein Bash/git)\n"
            f"- **Status:** {status_symbol} {result.detail}\n"
            f"- **Dauer:** {result.duration_seconds:.1f}s\n"
            f"- **Turns:** {turns}\n"
            f"- **Kosten-Gegenwert:** {cost} (MAX-Abo: Grenzkosten 0)\n"
            f"- **Zeitpunkt:** {datetime.now().isoformat(timespec='seconds')}\n\n"
            "## Geaenderte Dateien (git status --porcelain)\n\n"
            f"```\n{status or '(keine Aenderungen)'}\n```\n\n"
            "## Diff zur Sichtung\n\n"
            f"```diff\n{diff or '(leer)'}\n```\n\n"
            "## Zusammenfassung des Agenten\n\n"
        )
        return write_text_create_only(
            _artifact_dir, f"{timestamp}-arbeit.md",
            header + (result.text or "(kein Text)") + "\n",
        )
    except OSError as e:  # noqa: BLE001
        logger.warning("Arbeits-Artefakt konnte nicht geschrieben werden: %s", e)
        return None


def _self_check(repo: Path) -> tuple[str, Optional[dict]]:
    """Selbstkontrolle nach erfolgreichem Kaefig-Bau (Stufe 3, ADR-055): Gate +
    Tests des Repos laufen lassen und das Ergebnis als Anhang zur Antwort
    zurueckgeben. Fail-safe: scheitert die Pruefung SELBST (nicht der Code),
    wird das nur vermerkt - die Delegation bleibt erfolgreich, der Diff liegt
    ja vor. Eine ROTE Pruefung fuehrt zu einer deutlichen Warnung, aendert aber
    den Delegations-Status nicht (der Bau lief; die Sichtung bleibt beim PO)."""
    try:
        from core.verify import run_verification

        report = run_verification(repo)
    except Exception:  # noqa: BLE001 - Pruefung ist additiv, darf nie werfen
        logger.exception("Selbstpruefung nach Schreib-Delegation fehlgeschlagen.")
        return "\n\nSelbstpruefung: nicht durchfuehrbar (siehe Log).", None
    if report.get("ok"):
        return "\n\n✓ Selbstpruefung bestanden: Gate + Tests gruen.", report
    failed = [c["name"] for c in report["checks"] if not c["ok"] and not c.get("skipped")]
    return (
        f"\n\n⚠ Selbstpruefung ROT ({', '.join(failed)}) - die Aenderung besteht die "
        "Pruefung NICHT. Bitte nicht committen, erst den Diff pruefen.",
        report,
    )


class DelegateWorkCommand:
    name = "delegate_work"
    description = (
        "Delegiert eine SCHREIBENDE Umsetzungsarbeit in einem dafuer "
        "freigegebenen Projekt-Repo an einen Agenten (z. B. 'erledige in "
        "jkc: lege die CONTRIBUTING.md nach Framework-Vorbild an', 'arbeite "
        "in jkc: ...'). target = Repo-Alias, parameters.task = der "
        "Arbeitsauftrag. Sicherheitsstufe 2 - Bestaetigung erforderlich. "
        "Der Agent schreibt nur im freigegebenen Verzeichnis, fuehrt nichts "
        "aus und committet nichts; Ergebnis = Aenderungen im Arbeitsbaum + "
        "Diff-Artefakt zur Sichtung."
    )
    requires_confirmation = True  # Sicherheitsstufe 2 (Systemaenderung)
    long_running = True           # Minuten - async wie delegate_analysis (ADR-035)

    def execute(self, plan: Plan) -> Result:
        return self._work(plan, cancel_event=None)

    def run_async(self, plan: Plan, cancel_event: Optional[threading.Event] = None) -> Result:
        return self._work(plan, cancel_event=cancel_event)

    def _work(self, plan: Plan, cancel_event: Optional[threading.Event]) -> Result:
        _require_configured()

        if not _write_allowlist:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=(
                    "Es ist kein Repo fuer schreibende Delegation freigegeben. In config.json "
                    "unter 'agent_write_repos' eintragen - bewusst getrennt von 'agent_repos' "
                    "(lesen heisst nicht schreiben, ADR-050)."
                ),
            )

        repo_alias, task = _extract(plan, param="task")
        if not repo_alias:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=(
                    "In welchem Projekt soll gearbeitet werden? Freigegeben: "
                    f"{', '.join(sorted(_write_allowlist)) or '(keine)'}."
                ),
            )
        if not task:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=f"Was genau soll in '{repo_alias}' erledigt werden?",
            )

        repo = _write_allowlist.get(repo_alias)
        if repo is None:
            logger.warning("Schreib-Delegation abgelehnt: '%s' nicht in der Schreib-Allowlist.", repo_alias)
            return Result(
                status=Status.FAILED,
                message=(
                    f"In '{repo_alias}' darf nicht geschrieben werden. Freigegeben: "
                    f"{', '.join(sorted(_write_allowlist))}."
                ),
            )
        if not (repo / ".git").is_dir():
            return Result(
                status=Status.FAILED,
                message=f"'{repo_alias}' ist kein Git-Repo - ohne git keine Diff-Sichtung, kein Lauf.",
            )
        # Sauberer Arbeitsbaum als Vorbedingung: nach dem Lauf stammt damit
        # JEDE Aenderung nachweislich vom Agenten (eindeutige Sichtung).
        pre_status = _git(repo, "status", "--porcelain").strip()
        if pre_status:
            return Result(
                status=Status.FAILED,
                message=(
                    f"Der Arbeitsbaum von '{repo_alias}' ist nicht sauber - erst committen/"
                    "aufraeumen, dann delegieren (sonst ist die Sichtung nicht eindeutig)."
                ),
            )

        logger.info(
            "Schreib-Delegation gestartet: repo=%s auftrag=%r backend=%s",
            repo_alias, task, _backend.name,
        )
        # redirect (Scheibe 3): zusammen mit on_event laeuft der Bau interaktiv -
        # der PO kann den Agenten mitten im Lauf umlenken (Runtime-Draht).
        result = _backend.work(repo, task, _limits, cancel_event,
                               on_event=_event_sink, redirect=_redirect_channel)
        status, diff = _capture_changes(repo)
        artifact = _write_work_artifact(repo_alias, task, result, status, diff)

        cost_note = ""
        if result.cost_usd is not None and result.cost_usd > _cost_warn_usd:
            cost_note = (
                f"\n⚠ Ungewoehnlich grosser Lauf: Kosten-Gegenwert {result.cost_usd:.2f} USD "
                f"ueber der Warnschwelle ({_cost_warn_usd:.2f} USD) - ueber dein Abo gedeckt, "
                "aber das Session-Kontingent leidet."
            )
            logger.warning(
                "Agentenlauf ueber Warnschwelle: Gegenwert %.4f USD (Schwelle %.2f, Abo-Grenzkosten 0).",
                result.cost_usd, _cost_warn_usd,
            )

        changed = len([line for line in status.splitlines() if line.strip()])
        logger.info(
            "Schreib-Delegation beendet: repo=%s status=%s dauer=%.1fs dateien=%d kosten=%s artefakt=%s",
            repo_alias, "✓" if result.ok else "✗", result.duration_seconds,
            changed,
            f"{result.cost_usd:.4f}" if result.cost_usd is not None else "?",
            artifact.name if artifact else "-",
        )

        artifact_hint = f"\n\nDiff zur Sichtung: {artifact}" if artifact else ""
        if not result.ok:
            touched = f" {changed} Datei(en) wurden trotzdem angefasst -" if changed else ""
            return Result(
                status=Status.FAILED,
                message=(
                    f"Die Arbeit in '{repo_alias}' hat nicht geklappt: {result.detail}."
                    f"{touched} nichts wurde committet.{artifact_hint}{cost_note}"
                ),
                data={"repo": repo_alias, "artifact": str(artifact) if artifact else None},
            )

        # Selbstkontrolle (Stufe 3, ADR-055): direkt nach dem Bau Gate + Tests
        # laufen lassen - so liefert Jarvis GEPRUEFTE Arbeit (Kette Bauen ->
        # Pruefen -> Vorlegen). Der Diff bleibt uncommittet; die Pruefung testet
        # also genau die neue Aenderung. Fail-safe, additiv.
        verify_note, verify_report = _self_check(repo)

        return Result(
            status=Status.SUCCESS,
            message=(
                f"Arbeit in '{repo_alias}' erledigt - {changed} Datei(en) geaendert, "
                f"nichts committet. Die Sichtung liegt bei dir, Sir."
                f"\n\n{_summary(result.text)}{verify_note}{artifact_hint}{cost_note}"
            ),
            data={
                "repo": repo_alias,
                "task": task,
                "changed_files": changed,
                "artifact": str(artifact) if artifact else None,
                "num_turns": result.num_turns,
                "cost_usd": result.cost_usd,
                "self_check": verify_report,
            },
        )


# --- "mach weiter an <projekt>" (Projektentwickler-Kampagne, Stufe 2) ------
#
# project_continue ist der Scheiben-Zyklus als EIN Befehl: Jarvis liest den
# Projektstand des Zielrepos (PROJECT_STATE + logbook, read-only, gedeckelt),
# laesst das Antwort-Modell daraus den konkreten delegate_work-Auftrag
# formulieren, zeigt die Kurzfassung in der Stufe-2-Rueckfrage (preview()-Hook,
# ADR-023) - und delegiert nach dem Ja ueber exakt den delegate_work-Pfad
# (Schreib-Kaefig ADR-050, sauberer Baum, Diff-Artefakt, Kosten-Warnschwelle:
# alles erbt sich, nichts dupliziert). PO-Leitplanke 2026-07-10: "ich will
# Jarvis intuitiver steuern - mit so einem ewig langen Text kann ich das nie
# selbstaendig."

# Deckel fuer den kuratierten Projektstand (Muster commands/plan.py): das
# Modell soll DENKEN, nicht das ganze Repo geschickt bekommen. PROJECT_STATE
# traegt die AP-Spezifikationen, darum der groessere Deckel.
_CAP_CONTINUE_STATE = 9000
_CAP_CONTINUE_LOGBOOK = 4000

_CONTINUE_PROMPT = (
    "Du bist die Projektfortsetzungs-Faehigkeit von Jarvis. Unten steht der "
    "aktuelle Stand eines Zielprojekts (docs/PROJECT_STATE.md und juengste "
    "docs/logbook.md-Eintraege). Bestimme daraus das NAECHSTE offene "
    "Arbeitspaket und formuliere den Arbeitsauftrag fuer einen "
    "Umsetzungs-Agenten, der im Repo schreiben darf, aber nichts ausfuehrt "
    "und nichts committet.\n\n"
    "Regeln:\n"
    "- Uebernimm Spezifikations-Details WOERTLICH aus dem Projektstand - "
    "niemals paraphrasieren oder kuerzen (verlorene Details = kaputte "
    "Umsetzung).\n"
    "- Der Auftrag nennt: das Arbeitspaket, die konkreten Anforderungen laut "
    "Stand, und dass Tests zum Paket gehoeren.\n"
    "- Genau EIN Arbeitspaket - niemals mehrere buendeln.\n"
    "- Ist KEIN klares naechstes Arbeitspaket dokumentiert, setze auftrag "
    "auf null und begruende das in kurzfassung - erfinde NIEMALS eines.\n\n"
    "Antworte AUSSCHLIESSLICH als JSON-Objekt in genau dieser Form:\n"
    '{"kurzfassung": "<1-2 Saetze: welches Paket, was es tut>", '
    '"auftrag": "<vollstaendiger Arbeitsauftrag oder null>"}'
)


def _build_continuation(repo: Path) -> tuple[str, str]:
    """Liest den Projektstand (read-only, gedeckelt) und laesst das LLM das
    naechste Arbeitspaket als (kurzfassung, auftrag) formulieren. auftrag=""
    heisst ehrlich: kein delegierbarer Schritt dokumentiert. Wirft bei
    fehlender AI-Engine, fehlendem PROJECT_STATE oder kaputter LLM-Antwort -
    der Aufrufer entscheidet fail-closed."""
    if _ai is None:
        raise RuntimeError(
            "project_continue braucht die AI-Engine - configure(config, backend, ai=...) "
            "muss sie beim Start injizieren (siehe jarvis_runtime.py)."
        )
    docs = repo / "docs"
    state_path = docs / "PROJECT_STATE.md"
    if not state_path.is_file():
        # Ohne Projektstand gibt es nichts Ehrliches fortzusetzen - lieber
        # laut scheitern als aus dem logbook allein einen Auftrag raten.
        raise RuntimeError(f"{state_path} fehlt - ohne Projektstand kein Fortsetzungs-Auftrag.")
    context = (
        f"===== docs/PROJECT_STATE.md =====\n"
        f"{read_text_capped(state_path, _CAP_CONTINUE_STATE)}\n\n"
        f"===== docs/logbook.md =====\n"
        f"{read_text_capped(docs / 'logbook.md', _CAP_CONTINUE_LOGBOOK)}"
    )
    raw = _ai.generate(_CONTINUE_PROMPT, context, json_mode=True, max_tokens=1500)
    data = json.loads(raw)
    kurzfassung = str(data.get("kurzfassung") or "").strip()
    auftrag = data.get("auftrag")
    auftrag = "" if auftrag is None else str(auftrag).strip()
    if not kurzfassung:
        raise ValueError("LLM-Antwort ohne kurzfassung.")
    return kurzfassung, auftrag


def _continue_alias(plan: Plan) -> str:
    """Projekt-Alias aus target (Planner) oder parameters.project (Rueckfall)."""
    alias = (plan.target or "").strip().lower()
    if not alias:
        alias = str(plan.parameters.get("project", "")).strip().lower()
    return alias


class ProjectContinueCommand:
    name = "project_continue"
    description = (
        "Setzt die Arbeit an einem fuer schreibende Delegation freigegebenen "
        "Projekt fort ('mach weiter an jkc', 'arbeite weiter am Projekt jkc'): "
        "liest PROJECT_STATE und logbook des Projekts, formuliert daraus den "
        "naechsten Arbeitsauftrag und delegiert ihn nach Bestaetigung an den "
        "Schreib-Agenten (Kaefig, nichts wird committet). target = NUR der "
        "Projekt-Alias. Sicherheitsstufe 2 - Bestaetigung erforderlich."
    )
    requires_confirmation = True  # Sicherheitsstufe 2 (loest Schreib-Delegation aus)
    long_running = True           # Delegation dauert Minuten - async (ADR-035)

    def preview(self, plan: Plan) -> Optional[str]:
        """preview()-Hook (ADR-023): baut den Auftrag VOR der Rueckfrage und
        legt ihn im Plan ab - die Bestaetigungsfrage zeigt die Kurzfassung,
        der PO bestaetigt einen KONKRETEN Schritt, nie eine Blackbox. Jeder
        Fehler wird zur ehrlichen Empfehlung, mit Nein zu antworten (die
        Ausfuehrung selbst bleibt fail-closed, siehe _continue)."""
        try:
            _require_configured()
            alias = _continue_alias(plan)
            repo = _write_allowlist.get(alias)
            if repo is None:
                return (
                    f"'{alias or '?'}' ist nicht fuer schreibende Delegation freigegeben "
                    f"(freigegeben: {', '.join(sorted(_write_allowlist)) or 'keine'}) - "
                    "antworte am besten mit Nein."
                )
            kurzfassung, auftrag = _build_continuation(repo)
            if not auftrag:
                return (
                    f"Ich habe KEINEN delegierbaren naechsten Schritt gefunden: "
                    f"{kurzfassung} Antworte am besten mit Nein."
                )
            plan.parameters["task"] = auftrag
            plan.parameters["kurzfassung"] = kurzfassung
            return f"Naechster Schritt in '{alias}': {kurzfassung}"
        except Exception as e:  # noqa: BLE001 - Vorschau darf die Rueckfrage nie crashen
            logger.warning("project_continue-Vorschau fehlgeschlagen: %s", e)
            return (
                "Ich konnte den naechsten Schritt nicht ermitteln (Details im Log) - "
                "antworte am besten mit Nein."
            )

    def execute(self, plan: Plan) -> Result:
        return self._continue(plan, cancel_event=None)

    def run_async(self, plan: Plan, cancel_event: Optional[threading.Event] = None) -> Result:
        return self._continue(plan, cancel_event=cancel_event)

    def _continue(self, plan: Plan, cancel_event: Optional[threading.Event]) -> Result:
        _require_configured()

        alias = _continue_alias(plan)
        if not alias:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=(
                    "An welchem Projekt soll ich weiterarbeiten? Freigegeben: "
                    f"{', '.join(sorted(_write_allowlist)) or '(keine)'}."
                ),
            )
        repo = _write_allowlist.get(alias)
        if repo is None:
            # Fail-closed wie delegate_work: fortsetzen heisst schreiben.
            logger.warning("project_continue abgelehnt: '%s' nicht in der Schreib-Allowlist.", alias)
            return Result(
                status=Status.FAILED,
                message=(
                    f"An '{alias}' darf ich nicht weiterarbeiten (keine Schreib-Freigabe). "
                    f"Freigegeben: {', '.join(sorted(_write_allowlist)) or '(keine)'}."
                ),
            )

        task = str(plan.parameters.get("task") or "").strip()
        kurzfassung = str(plan.parameters.get("kurzfassung") or "").strip()
        if not task:
            # preview() lief nicht (z. B. direkter Dispatch) - Auftrag jetzt
            # bauen, fail-closed bei jedem Fehler: nie ein geratener Auftrag.
            try:
                kurzfassung, task = _build_continuation(repo)
            except Exception as e:  # noqa: BLE001 - LLM/IO koennen vielfaeltig scheitern
                logger.warning("project_continue: Auftrag-Bau fehlgeschlagen: %s", e)
                return Result(
                    status=Status.FAILED,
                    message=(
                        f"Ich konnte den naechsten Schritt fuer '{alias}' nicht "
                        "ermitteln - Details im Log. Es wurde nichts delegiert."
                    ),
                )
            if not task:
                return Result(
                    status=Status.NEEDS_CLARIFICATION,
                    message=(
                        f"Ich sehe keinen delegierbaren naechsten Schritt fuer "
                        f"'{alias}': {kurzfassung}"
                    ),
                )

        logger.info(
            "project_continue: repo=%s kurzfassung=%r auftrag_laenge=%d",
            alias, kurzfassung, len(task),
        )
        # Delegation ueber den delegate_work-Pfad (alle ADR-050-Waechter
        # inklusive). raw_input bewusst leer: _extract darf den gebauten
        # Auftrag nie durch eine Roheingabe ersetzen.
        work_plan = Plan(
            intent="delegate_work",
            target=alias,
            parameters={"task": task},
            raw_input="",
            confidence=plan.confidence,
        )
        result = _work_command._work(work_plan, cancel_event)

        if kurzfassung:
            # Kontext fuer die Minuten spaeter eintreffende Async-Antwort:
            # WAS wurde fortgesetzt, nicht nur "Arbeit erledigt".
            result = Result(
                status=result.status,
                message=f"Weiterarbeit an '{alias}' - {kurzfassung}\n\n{result.message}",
                data=result.data,
            )
        if result.data is not None:
            result.data["kurzfassung"] = kurzfassung
        return result


# Registrierungspunkt - commands/__init__.py liest diese Liste beim Start ein.
# project_continue delegiert intern an dieselbe DelegateWorkCommand-Instanz.
_work_command = DelegateWorkCommand()
COMMANDS = [DelegateAnalysisCommand(), _work_command, ProjectContinueCommand()]
