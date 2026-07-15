"""Tests fuer memory/skills.py (Plan A1, Skill-Bibliothek)."""
from __future__ import annotations

from memory.skills import SkillLibrary

_VOCAB = ["screenshot", "umbenennen", "wetter", "backup", "steuer"]


def _embed(texts):
    return [[1.0 if w in (t or "").lower() else 0.0 for w in _VOCAB] for t in texts]


def test_add_and_list_roundtrip(tmp_path):
    lib = SkillLibrary(tmp_path / "skills.json")
    lib.add("wetter-cli", "zeigt das Wetter im Terminal", tmp_path / "wetter-cli")
    lib.add("backup-tool", "sichert Ordner", tmp_path / "backup-tool")
    assert lib.names() == ["wetter-cli", "backup-tool"]
    assert lib.get("WETTER-CLI")["description"] == "zeigt das Wetter im Terminal"


def test_add_dedups_by_name(tmp_path):
    lib = SkillLibrary(tmp_path / "skills.json")
    lib.add("wetter-cli", "alt", tmp_path / "a")
    lib.add("wetter-cli", "neu", tmp_path / "b")           # gleicher Name -> Update
    assert len(lib.all()) == 1
    assert lib.get("wetter-cli")["description"] == "neu"


def test_add_ignores_empty_name(tmp_path):
    lib = SkillLibrary(tmp_path / "skills.json")
    assert lib.add("", "x", tmp_path) == {}
    assert lib.all() == []


def test_find_similar_matches_and_thresholds(tmp_path):
    lib = SkillLibrary(tmp_path / "skills.json")
    lib.add("screenshot-renamer", "screenshot umbenennen", tmp_path / "s")
    hit = lib.find_similar("ein tool das screenshot umbenennen kann", _embed, threshold=0.5)
    assert hit and hit["name"] == "screenshot-renamer"
    miss = lib.find_similar("etwas ganz anderes zum steuer", _embed, threshold=0.5)
    assert miss is None


def test_find_similar_failsafe_on_embed_error(tmp_path):
    lib = SkillLibrary(tmp_path / "skills.json")
    lib.add("x", "y", tmp_path)

    def boom(texts):
        raise RuntimeError("kein Netz")

    assert lib.find_similar("egal", boom) is None
