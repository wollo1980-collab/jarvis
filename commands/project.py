"""
Projektstart auf Zuruf (ADR-049, Projektentwickler-Kampagne Stufe 1):
"starte Projekt jkc" -> Jarvis legt das Geruest eines neuen Zielprojekts
nach den Regeln des AI Project Frameworks an (core/project_scaffold.py).

Sicherheitsstufe 2 (requires_confirmation): erster Command, der ausserhalb
von memory_data ins Dateisystem schreibt - aber nur UNTERHALB der
konfigurierten projects_root, nie in existierende Verzeichnisse, nie mit
Remote/Push. Beide Pfade kommen aus der Config (Default leer = Faehigkeit
aus, fail-closed); das Framework-Repo wird ausschliesslich gelesen.

configure()-Muster wie commands/news.py: Registry instanziiert Commands
vor Config.load(), deshalb Einmal-Injection beim Start.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from core.models import Plan, Result, Status
from core.project_scaffold import scaffold_project

logger = logging.getLogger("jarvis.commands.project")

_projects_root: Optional[Path] = None
_framework_repo: Optional[Path] = None


def configure(projects_root: str, framework_repo: str) -> None:
    """Von main.py/jarvis_runtime.py beim Start aufgerufen (Pfade aus Config).
    Leere Werte lassen die Faehigkeit aus (fail-closed)."""
    global _projects_root, _framework_repo
    _projects_root = Path(projects_root) if projects_root else None
    _framework_repo = Path(framework_repo) if framework_repo else None


class StartProjectCommand:
    name = "start_project"
    description = (
        "Legt das Geruest eines neuen Software-Projekts nach dem AI Project "
        "Framework an (z. B. 'starte Projekt jkc', 'lege ein neues Projekt "
        "namens foo an'): eigenes Git-Repo, Governance-Dokumente, erster "
        "Commit. Sicherheitsstufe 2 - Bestaetigung erforderlich."
    )
    requires_confirmation = True

    def execute(self, plan: Plan) -> Result:
        name = str(plan.parameters.get("name") or plan.target or "").strip()
        if not name:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Wie soll das neue Projekt heissen, Sir?",
            )
        if _projects_root is None or _framework_repo is None:
            return Result(
                status=Status.FAILED,
                message=(
                    "Der Projektstart ist nicht konfiguriert, Sir - "
                    "projects_root und framework_repo fehlen in der config.json."
                ),
            )
        try:
            target = scaffold_project(_projects_root, name, _framework_repo)
        except ValueError as e:
            return Result(status=Status.FAILED, message=f"Kein Projektstart, Sir: {e}")
        except Exception:  # noqa: BLE001 - z. B. git nicht verfuegbar
            logger.exception("Projektstart fehlgeschlagen.")
            return Result(
                status=Status.FAILED,
                message="Der Projektstart ist fehlgeschlagen, Sir - Details im Log.",
            )
        return Result(
            status=Status.SUCCESS,
            message=(
                f"Das Geruest steht, Sir: {target} - eigenes Git-Repo, "
                "Governance-Dokumente, erster Commit. Bevor dort Code entsteht, "
                "gehoert das Onboarding-Interview dazu (Zweck, MVP, Stack) - "
                "ganz nach den Regeln des Frameworks."
            ),
            data={"path": str(target)},
        )


COMMANDS = [StartProjectCommand()]
