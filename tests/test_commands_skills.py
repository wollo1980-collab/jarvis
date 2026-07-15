"""Tests fuer commands/skills.py (Plan A1) - list_skills."""
from __future__ import annotations

import commands.skills as skills_commands
from core.models import Plan, Status


def test_list_skills_empty_invites_building(tmp_path):
    skills_commands.configure(tmp_path)
    result = skills_commands.ListSkillsCommand().execute(Plan(intent="list_skills"))
    assert result.status == Status.SUCCESS
    assert "noch nichts" in result.message.lower()   # "Fertig gebaut habe ich bisher noch nichts"


def test_list_skills_lists_registered(tmp_path):
    lib = skills_commands.configure(tmp_path)
    lib.add("wetter-cli", "zeigt das Wetter", tmp_path / "wetter-cli")
    lib.add("backup-tool", "sichert Ordner", tmp_path / "backup-tool")

    result = skills_commands.ListSkillsCommand().execute(Plan(intent="list_skills"))

    assert result.status == Status.SUCCESS
    assert "wetter-cli" in result.message and "backup-tool" in result.message
    assert set(result.data["skills"]) == {"wetter-cli", "backup-tool"}
