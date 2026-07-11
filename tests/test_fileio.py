"""Tests fuer core/fileio.py - atomares JSON-Schreiben, sicheres Lesen
(kaputte Datei wird bewahrt) und create-only Textschreiben (Audit-Fixes P2a/P2b)."""
from __future__ import annotations

import json
from pathlib import Path

from core.fileio import read_json, write_json_atomic, write_text_create_only


def test_write_json_atomic_roundtrip_and_no_tmp_left(tmp_path: Path):
    target = tmp_path / "state.json"
    write_json_atomic(target, {"a": 1, "b": [2, 3]})

    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1, "b": [2, 3]}
    # Keine verwaiste .tmp-Datei.
    assert list(tmp_path.glob("*.tmp*")) == []


def test_write_json_atomic_creates_parent_dirs(tmp_path: Path):
    target = tmp_path / "sub" / "dir" / "state.json"
    write_json_atomic(target, [1, 2, 3])
    assert target.exists()


def test_read_json_missing_returns_default_without_side_effects(tmp_path: Path):
    result = read_json(tmp_path / "nope.json", {"default": True})
    assert result == {"default": True}
    # Fehlende Datei erzeugt KEINE .corrupt-Sicherung.
    assert list(tmp_path.glob("*.corrupt*")) == []


def test_read_json_corrupt_is_preserved_not_silently_discarded(tmp_path: Path):
    target = tmp_path / "history.json"
    target.write_text("{ das ist kaputtes json ", encoding="utf-8")

    result = read_json(target, [])

    assert result == []                       # Default geliefert
    assert not target.exists()                # Original zur Seite gelegt
    corrupt = list(tmp_path.glob("history.json.corrupt-*"))
    assert len(corrupt) == 1                  # ... aber bewahrt, nicht geloescht
    assert "kaputtes json" in corrupt[0].read_text(encoding="utf-8")


def test_write_text_create_only_never_overwrites(tmp_path: Path):
    p1 = write_text_create_only(tmp_path, "vorschlag.md", "erster")
    p2 = write_text_create_only(tmp_path, "vorschlag.md", "zweiter")
    p3 = write_text_create_only(tmp_path, "vorschlag.md", "dritter")

    # Drei verschiedene Dateien, nichts ueberschrieben.
    assert p1 != p2 != p3
    assert p1.read_text(encoding="utf-8") == "erster"
    assert p2.read_text(encoding="utf-8") == "zweiter"
    assert p2.name == "vorschlag-2.md"
    assert p3.name == "vorschlag-3.md"
    assert len(list(tmp_path.glob("vorschlag*.md"))) == 3


def test_write_text_create_only_without_extension(tmp_path: Path):
    p1 = write_text_create_only(tmp_path, "NOTES", "a")
    p2 = write_text_create_only(tmp_path, "NOTES", "b")
    assert p1.name == "NOTES"
    assert p2.name == "NOTES-2"
