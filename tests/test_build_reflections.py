"""Tests fuer memory/build_reflections.py (Plan G)."""
from __future__ import annotations

from memory.build_reflections import BuildReflections


def test_record_and_recent_roundtrip(tmp_path):
    r = BuildReflections(tmp_path)
    r.record("jkc", "Selbstpruefung ROT (tests) beim Auftrag: X")
    r.record("jkc", "Selbstpruefung ROT (gate) beim Auftrag: Y")
    assert r.recent("jkc") == ["Selbstpruefung ROT (tests) beim Auftrag: X",
                               "Selbstpruefung ROT (gate) beim Auftrag: Y"]
    assert r.recent("anderes") == []


def test_recent_limits_to_n(tmp_path):
    r = BuildReflections(tmp_path)
    for i in range(6):
        r.record("p", f"note {i}")
    assert r.recent("p", n=2) == ["note 4", "note 5"]


def test_record_caps_per_project(tmp_path):
    r = BuildReflections(tmp_path)
    for i in range(15):
        r.record("p", f"note {i}")
    all_notes = r.recent("p", n=100)
    assert len(all_notes) == 10                 # _MAX_PER_PROJECT
    assert all_notes[0] == "note 5"             # aelteste abgeschnitten


def test_record_ignores_empty(tmp_path):
    r = BuildReflections(tmp_path)
    r.record("", "x")
    r.record("p", "")
    assert r.recent("p") == []
