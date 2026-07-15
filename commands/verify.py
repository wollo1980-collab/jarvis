"""
Repo-Verifikation (Endsystem-Kampagne B "Selbstkontrolle", ADR-055) - der
Command ueber core/verify.py: "pruefe das Repo jkc" laesst Jarvis das feste
Whitelist (Konsistenz-Gate + Testsuite) in EINEM freigegebenen Repo laufen
und legt einen Pruefbericht vor. Das ist der erste Baustein von Stufe 3:
Jarvis prueft die Arbeit selbst, statt dass ein Mensch die
Verifikationsluecke fuellt.

Sicherheit: die Fachlogik hier waehlt kein Kommando - core/verify.py haelt
das harte Whitelist (kein freies Shell). Der Repo-Alias wird gegen eine
Allowlist aus config.agent_repos + config.agent_write_repos aufgeloest
(fail-closed, validierte Pfade) - nur ein real vorhandenes, ausdruecklich
gelistetes Repo ist pruefbar. requires_confirmation=False: die Verifikation
aendert keinen Quellcode und committet nichts (Stufe 0/1); sie liest, laesst
laufen und berichtet. long_running wie delegate_analysis (pytest dauert) -
die Runtime fuehrt sie async aus.

configure()-Muster wie commands/delegate.py: Einmal-Aufruf beim Start baut
die Allowlist aus der Config.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

from core.models import Plan, Result, Status
from core.verify import run_verification

logger = logging.getLogger("jarvis.commands.verify")

_allowlist: dict[str, Path] = {}
_configured = False


def configure(config) -> None:
    """Baut die Pruef-Allowlist aus BEIDEN Repo-Listen (lesend + schreibend):
    ein Repo, in dem ein Agent baut ODER das analysiert werden darf, ist auch
    verifizierbar. Fail-closed, validierte Pfade - identisches Muster wie
    commands/delegate.py."""
    global _allowlist, _configured
    allowlist: dict[str, Path] = {}
    for attr in ("agent_repos", "agent_write_repos"):
        for entry in getattr(config, attr, []) or []:
            alias = str(entry.get("alias", "")).strip().lower()
            raw_path = str(entry.get("path", "")).strip()
            if not alias or not raw_path:
                continue
            path = Path(raw_path)
            if not path.is_dir():
                logger.warning("Pruef-Repo '%s' uebersprungen: Pfad fehlt (%s).", alias, raw_path)
                continue
            allowlist.setdefault(alias, path)
    _allowlist = allowlist
    _configured = True


def _format_report(report: dict) -> str:
    lines = [f"Verifikation von «{report['repo']}»: {'✓ bestanden' if report['ok'] else '✗ durchgefallen'}."]
    for check in report["checks"]:
        mark = "•" if check.get("skipped") else ("✓" if check["ok"] else "✗")
        lines.append(f"{mark} {check['name']}")
        # Bei einem Fehlschlag den Ausgaben-Anriss zeigen - sonst nur der Haken.
        if not check["ok"] and not check.get("skipped") and check.get("tail"):
            snippet = check["tail"].strip().splitlines()[-4:]
            lines.append("    " + " / ".join(s.strip() for s in snippet if s.strip()))
    return "\n".join(lines)


class VerifyRepoCommand:
    name = "verify_repo"
    description = (
        "Prueft ein freigegebenes lokales Repo selbst: laesst das Konsistenz-"
        "Gate und die Testsuite laufen und legt einen Pruefbericht vor (z. B. "
        "'pruefe das Repo jkc', 'lauf die Tests in jarvis'). target = der "
        "Repo-Alias. Sicherheitsstufe 0/1: festes Befehls-Whitelist, kein "
        "freies Shell, aendert keinen Quellcode, committet nichts."
    )
    requires_confirmation = False
    long_running = True  # pytest dauert - die Runtime fuehrt async aus (ADR-035)

    def execute(self, plan: Plan) -> Result:
        return self._verify(plan)

    def run_async(self, plan: Plan, cancel_event: Optional[threading.Event] = None) -> Result:
        # Der Harnisch nutzt einen Wall-Clock-Timeout; ein Kill-Switch ist
        # fuer diese kurze, feste Kommandokette nicht noetig.
        return self._verify(plan)

    def _verify(self, plan: Plan) -> Result:
        if not _configured:
            return Result(status=Status.FAILED, message="Verifikation ist nicht verdrahtet, Sir.")
        if not _allowlist:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=(
                    "Es ist noch kein Repo zur Verifikation freigegeben - bitte in "
                    "config.json unter 'agent_repos'/'agent_write_repos' eintragen."
                ),
            )
        alias = (plan.target or "").strip().lower()
        if not alias:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=f"Welches Repo soll ich pruefen? Bekannt: {', '.join(sorted(_allowlist))}.",
            )
        repo = _allowlist.get(alias)
        if repo is None:
            return Result(
                status=Status.FAILED,
                message=(f"«{alias}» kann ich nicht pruefen, Sir - Zugriff habe ich auf: "
                         f"{', '.join(sorted(_allowlist)) or 'derzeit nichts'}."),
            )
        report = run_verification(repo)
        return Result(
            status=Status.SUCCESS if report["ok"] else Status.FAILED,
            message=_format_report(report),
            data={"repo": report["repo"], "ok": report["ok"], "checks": report["checks"]},
        )


# Registrierungspunkt - commands/__init__.py liest diese Liste beim Start ein.
COMMANDS = [VerifyRepoCommand()]
