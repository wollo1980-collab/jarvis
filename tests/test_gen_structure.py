"""Schlanker Test für `scripts/gen_structure.py` (Governance-Umbau Chunk 5).

Prüft die reine `build_tree`-Funktion gegen Fixture-Verzeichnisse. Das Skript
wird per importlib geladen, da `scripts/` kein Package ist."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "gen_structure", _ROOT / "scripts" / "gen_structure.py"
)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def test_build_tree_lists_dirs_and_files(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("", encoding="utf-8")
    (tmp_path / "readme.md").write_text("", encoding="utf-8")
    lines = gen.build_tree(tmp_path)
    text = "\n".join(lines)
    assert lines[0].endswith("/")           # Root
    assert "pkg/" in text                    # Verzeichnis mit '/'
    assert "mod.py" in text
    assert "readme.md" in text


def test_build_tree_skips_ignored(tmp_path):
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "keep.py").write_text("", encoding="utf-8")
    text = "\n".join(gen.build_tree(tmp_path))
    assert "keep.py" in text
    assert "__pycache__" not in text


def test_build_tree_custom_ignore(tmp_path):
    (tmp_path / "keep.py").write_text("", encoding="utf-8")
    (tmp_path / "skip.py").write_text("", encoding="utf-8")
    text = "\n".join(gen.build_tree(tmp_path, ignore={"skip.py"}))
    assert "keep.py" in text
    assert "skip.py" not in text


def test_build_tree_max_depth(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "deep.py").write_text("", encoding="utf-8")
    text = "\n".join(gen.build_tree(tmp_path, max_depth=1))
    assert "a/" in text
    assert "deep.py" not in text            # jenseits der Tiefe
