"""
Skill-Befehl (Plan A1): „was hast du schon gebaut?" listet die Skill-Bibliothek.

configure() bekommt das memory_dir und baut die (geteilte, file-backed)
SkillLibrary. Nur lesend, Stufe 0. Das AUSFUEHREN eines Skills (A2) kommt spaeter
(S4b-gated) - hier wird nur gezeigt, was existiert.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from core.models import Plan, Result, Status
from memory.skills import SkillLibrary

logger = logging.getLogger("jarvis.commands.skills")

_library: Optional[SkillLibrary] = None


def configure(memory_dir) -> SkillLibrary:
    """Baut die SkillLibrary unter memory_dir/skills.json und gibt sie zurueck
    (die Runtime nutzt dieselbe Instanz fuer die Dedup im Bau-Vorschlag)."""
    global _library
    _library = SkillLibrary(Path(memory_dir) / "skills.json")
    return _library


class ListSkillsCommand:
    name = "list_skills"
    description = (
        "Zeigt die Faehigkeiten/Werkzeuge, die Jarvis fuer dich SELBST GEBAUT hat "
        "- AUCH fuer Rueckfragen zum letzten Bau (z. B. 'was hast du schon/eben/"
        "zuletzt/gerade gebaut?', 'zeig deine Faehigkeiten', 'welche Tools hast du "
        "mir gebaut?', 'was war das Projekt eben?'). Nur lesend. Nicht zu "
        "verwechseln mit list_facts (gemerkte Fakten), show_list (Einkaufslisten) "
        "oder delegate_analysis (analysiert CODE eines Repos auf eine Frage hin - "
        "eine blosse Rueckfrage, was gebaut wurde, ist KEINE Repo-Analyse)."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if _library is None:
            return Result(status=Status.FAILED,
                          message="Die Skill-Bibliothek ist nicht verdrahtet, Sir.")
        skills = _library.all()
        if not skills:
            return Result(
                status=Status.SUCCESS,
                message=("Fertig gebaut habe ich bisher noch nichts, Sir — sag «Bau mir …», "
                         "dann lege ich los und merke es mir als Faehigkeit. (Ein "
                         "abgebrochener Versuch zaehlt erst, wenn er fertig wird.)"),
            )
        lines = [f"- {s.get('name', '?')}: {s.get('description', '').strip() or '(ohne Beschreibung)'}"
                 for s in skills]
        return Result(
            status=Status.SUCCESS,
            message="Das habe ich bisher für dich gebaut, Sir:\n" + "\n".join(lines),
            data={"skills": [s.get("name", "") for s in skills]},
        )


COMMANDS = [ListSkillsCommand()]
