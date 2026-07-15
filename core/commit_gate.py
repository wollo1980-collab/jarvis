"""
Ampel-Klassifikator + Auto-Commit (ADR-056 Scheibe 4, Sicherheitskern).

Nach einem erfolgreichen, selbstgeprueften Kaefig-Bau (delegate_work, ADR-050
+ ADR-055) entscheidet dieser Baustein die Ampel fuer den COMMIT: GRUEN =
Jarvis committet das verifizierte Ergebnis selbst; sonst = Vorlage + Freigabe
(bestehendes Verhalten, der Mensch sichtet).

Klassifikation = die Delegations-Matrix (CONTRIBUTING §3), umgesetzt als
OBJEKTIVER, pruefbarer Filter - mit den drei Praezisierungen aus ADR-056 §4:

  a. Gruen ist an den SCOPE gebunden, nicht bloss an Reversibilitaet. Der
     Auftrag liefert genau EINEN Lauf; die Vorbedingung "sauberer Arbeitsbaum"
     (delegate_work) garantiert, dass der Diff NUR die Aenderungen dieses
     freigegebenen Auftrags enthaelt. Auto-Commit committet genau diesen Diff
     mit einer Message, die den Auftrag/die Freigabe referenziert - kein
     Freibrief fuer Vorgefundenes oder Kuenftiges.
  b. Selbst-erstellt vs. fremd: eine LOESCHUNG/Umbenennung trifft im
     Clean-Tree-Lauf immer eine vorgefundene Datei -> 🟡, nie Auto-Commit.
  c. Der Auftrag IST die PO-Freigabe des Arbeitspakets: die Message haelt das
     fest (Freigabe-Protokollierung, CONTRIBUTING §3).

Was die Ampel auf ROT/GELB zieht (Vorlage statt Auto-Commit):
  - Selbstpruefung nicht gruen (Gate/Tests, ADR-055) - notwendige Bedingung.
  - Eine Loeschung/Umbenennung (Schaerfung b).
  - Beruehrung folgenreicher Flaechen: Verfassung (Handbook), Charter
    (CONTRIBUTING), Architektur (neue/geaenderte ADR) - alle 🟡/🔴 in §3.
  - Beruehrung von Jarvis' eigenem Kern/Neustart (nur wenn im eigenen Repo
    gearbeitet wird): EXTRA gesperrt (nie den Ast absaegen, auf dem er sitzt).

Bewusst KEINE semantische Scope-Drift-Erkennung (kann ein Filter nicht
leisten): das Netz ist Selbstpruefung + Mensch-im-Loop-fuer-Unsicheres +
die Umkehrbarkeit des lokalen Commits (privates Remote, kein Push hier).

Der Auto-Commit committet lokal und pusht NICHT (nach aussen = eigener,
folgenreicher Akt). Fail-safe: die Git-Aktion wirft nie; ein Fehlschlag wird
ehrlich gemeldet und der Diff bleibt zur Sichtung liegen.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("jarvis.commit_gate")

# Folgenreiche Flaechen (repo-relativ, forward slashes). Beruehrt der Diff eine
# davon, geht die Ampel auf Vorlage - das sind genau die 🟡/🔴-Kategorien der
# Delegations-Matrix, die eine PO-Entscheidung/Sichtung brauchen.
_HANDBOOK_PREFIX = "docs/handbook/"   # Verfassung - 🔴
_ADR_PREFIX = "docs/adr/"            # Architektur-Entscheidung - 🟡
_CHARTER_FILE = "contributing.md"     # Charter/Governance - 🔴 (Basename, klein)

# Kern-/Neustart-Dateien von Jarvis selbst (Basename). Nur relevant, wenn der
# Agent im EIGENEN Repo arbeitet (guard_kernel) - dann bleibt Selbst-
# Modifikation extra gesperrt (ADR-056 Sicherheitsmodell).
_KERNEL_FILES = frozenset({
    "jarvis_runtime.py", "main.py", "dashboard.py",
    "browser_channel.py", "telegram_main.py",
})

_MAX_BLOCKERS_SHOWN = 5
_SUBJECT_MAX = 72


@dataclass
class CommitVerdict:
    """Ergebnis der Ampel-Klassifikation. green=True -> Auto-Commit; sonst
    Vorlage + Freigabe. reason ist menschenlesbar (fuer die Antwort, wenn NICHT
    committet wird); blockers listet die einzelnen Gruende."""

    green: bool
    reason: str
    blockers: list = field(default_factory=list)


def _parse_status(status_porcelain: str) -> list:
    """`git status --porcelain -uall` -> Liste (kind, path). kind ist
    'delete' | 'rename' | 'change' (Anlegen/Aendern zusammengefasst - fuer die
    Ampel zaehlt nur, ob etwas VERSCHWINDET). Fail-safe: unlesbare Zeilen
    werden uebersprungen, nie geworfen."""
    changes = []
    for line in (status_porcelain or "").splitlines():
        if not line.strip():
            continue
        code = line[:2]
        rest = line[3:] if len(line) > 3 else ""
        # Umbenennung (nur bei gestagtem R): "R  alt -> neu". Ohne git seitens
        # des Agenten unwahrscheinlich, aber defensiv behandelt.
        if "R" in code or " -> " in rest:
            path = rest.split(" -> ", 1)[-1].strip()
            changes.append(("rename", _norm(path)))
            continue
        if "D" in code:
            changes.append(("delete", _norm(rest.strip())))
            continue
        changes.append(("change", _norm(rest.strip())))
    return changes


def _norm(path: str) -> str:
    """Repo-relativen Pfad vereinheitlichen: forward slashes, evtl. Quotes weg
    (git zitiert Pfade mit Sonderzeichen)."""
    p = path.strip().strip('"')
    return p.replace("\\", "/")


def _sensitive_reason(path: str, guard_kernel: bool):
    """Liefert einen Grund-String, wenn der Pfad eine folgenreiche Flaeche
    trifft, sonst None. Case-insensitive auf dem Prefix/Basename."""
    low = path.lower()
    if low.startswith(_HANDBOOK_PREFIX):
        return "Verfassung (Handbook) - PO-Entscheidung noetig (🔴)"
    if low == _CHARTER_FILE or low.endswith("/" + _CHARTER_FILE):
        return "Charter/Governance (CONTRIBUTING) - PO-Entscheidung noetig (🔴)"
    if low.startswith(_ADR_PREFIX):
        return "Architektur-Entscheidung (ADR) - Vorlage statt Auto-Commit (🟡)"
    if guard_kernel and path.rsplit("/", 1)[-1].lower() in _KERNEL_FILES:
        return "Jarvis-Kern/Neustart - extra gesperrt (nie den Ast absaegen)"
    return None


def classify_commit(status_porcelain: str, self_check_report, *, guard_kernel: bool = False) -> CommitVerdict:
    """Die Ampel fuer den Commit. GRUEN nur, wenn ALLE gelten:
      1. es gibt ueberhaupt Aenderungen,
      2. die Selbstpruefung ist gruen (ADR-055) - notwendige Bedingung,
      3. nichts wird geloescht/umbenannt (Schaerfung b),
      4. keine folgenreiche Flaeche beruehrt (Handbook/Charter/ADR/[Kern]).
    Sonst: Vorlage + Freigabe (reason erklaert warum)."""
    changes = _parse_status(status_porcelain)
    if not changes:
        return CommitVerdict(False, "keine Aenderungen zum Committen.")
    if not (isinstance(self_check_report, dict) and self_check_report.get("ok") is True):
        return CommitVerdict(
            False,
            "Selbstpruefung nicht gruen - erst der Diff und die Pruefung, dann committen.",
        )

    blockers = []
    for kind, path in changes:
        if kind in ("delete", "rename"):
            blockers.append(
                f"{path or '(Pfad?)'}: Loeschung/Umbenennung einer vorgefundenen Datei (🟡)"
            )
            continue
        reason = _sensitive_reason(path, guard_kernel)
        if reason:
            blockers.append(f"{path}: {reason}")

    if blockers:
        shown = "; ".join(blockers[:_MAX_BLOCKERS_SHOWN])
        more = "" if len(blockers) <= _MAX_BLOCKERS_SHOWN else f" (+{len(blockers) - _MAX_BLOCKERS_SHOWN} weitere)"
        return CommitVerdict(False, shown + more, blockers)

    return CommitVerdict(
        True,
        "GRUEN: Aenderungen im Auftrags-Scope, Selbstpruefung gruen, nichts Folgenreiches.",
        [],
    )


def _subject_from_task(task: str) -> str:
    """Commit-Betreff aus dem Auftrag: erste nicht-leere Zeile, an Wortgrenze
    gekappt. Leerer Auftrag -> neutraler Fallback."""
    for line in (task or "").splitlines():
        line = line.strip()
        if line:
            if len(line) <= _SUBJECT_MAX:
                return line
            return line[:_SUBJECT_MAX].rsplit(" ", 1)[0] + " …"
    return "Agenten-Umsetzung (Auto-Commit)"


def build_commit_message(task: str) -> tuple[str, str]:
    """(Betreff, Rumpf) fuer den Auto-Commit. Der Rumpf haelt die Herkunft und
    die Freigabe-Kette fest (Freigabe-Protokollierung, CONTRIBUTING §3): wer
    gebaut hat, dass selbstgeprueft wurde, und dass der Auftrag die PO-Freigabe
    des Arbeitspakets ist."""
    subject = _subject_from_task(task)
    body = (
        "Umgesetzt vom Jarvis-Agenten (delegate_work) und selbstgeprueft: "
        "Gate + Tests gruen (ADR-055).\n"
        "Ampel-Klassifikation GRUEN -> Auto-Commit (ADR-056 Scheibe 4).\n"
        "Auftrag = PO-freigegebenes Arbeitspaket; committet genau dessen "
        "verifiziertes, im-Scope-liegendes Ergebnis.\n\n"
        f"Auftrag: {(task or '').strip()}"
    )
    return subject, body


def _run_git(repo: Path, args: list, timeout: float) -> tuple[bool, str]:
    """Ein git-Aufruf im Ziel-Repo (kein Shell, festes Timeout). Fail-safe:
    jeder Fehler wird zum (False, meldung), nie zur Exception."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, shell=False,
            # Fensterlose Runtime (pythonw): ohne das Flag blitzt je git-Aufruf
            # ein Konsolenfenster auf (PO-Befund 13.07.).
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return proc.returncode == 0, out.strip()
    except Exception as e:  # noqa: BLE001 - git kann vielfaeltig scheitern
        return False, f"git nicht ausfuehrbar: {e}"


def perform_auto_commit(repo: Path, task: str, timeout: float = 60.0) -> tuple[bool, str]:
    """Committet den aktuellen Arbeitsbaum-Stand im Ziel-Repo (git add -A +
    commit). KEIN Push (nach aussen = eigener folgenreicher Akt). Liefert
    (True, kurz-SHA) oder (False, Fehlermeldung). Fail-safe: wirft nie - ein
    Fehlschlag (z. B. roter Pre-Commit-Hook des Ziel-Repos, fehlende git-
    Identitaet) laesst den Diff unangetastet zur Sichtung liegen."""
    repo = Path(repo)
    subject, body = build_commit_message(task)

    ok, out = _run_git(repo, ["add", "-A"], timeout)
    if not ok:
        return False, f"git add fehlgeschlagen: {out}"

    ok, out = _run_git(repo, ["commit", "-m", subject, "-m", body], timeout)
    if not ok:
        return False, f"git commit fehlgeschlagen: {out}"

    ok, sha = _run_git(repo, ["rev-parse", "--short", "HEAD"], timeout)
    short = sha.strip() if ok else "?"
    logger.info("Auto-Commit im Repo %s: %s (%s)", repo.name, short, subject)
    return True, short
