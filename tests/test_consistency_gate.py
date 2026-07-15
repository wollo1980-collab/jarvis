"""Schlanker Test für das Konsistenz-Gate (`scripts/check_consistency.py`).

Prüft die reinen Funktionen (Frontmatter-Parser, Stand-Frische-Schwellen,
active_increment, Zählungen, Handbook-Reinheit) gegen Fixtures - ohne echtes
Repo/Git. Das Skript wird per importlib geladen, da `scripts/` kein Package ist."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_consistency", _ROOT / "scripts" / "check_consistency.py"
)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def test_parse_frontmatter():
    text = '---\nversion: "v0.8 x"\ntests: 327\nlatest_adr: 31\n---\n# Body\n'
    fm = gate.parse_frontmatter(text)
    assert fm["version"] == "v0.8 x"
    assert fm["tests"] == "327"
    assert fm["latest_adr"] == "31"


def test_parse_frontmatter_without_header():
    assert gate.parse_frontmatter("# kein Frontmatter\n") == {}


def test_stand_freshness_ok_boundary():
    assert gate.check_stand_freshness("2026-07-03", "2026-07-03")[0] == gate.OK   # 0 Tage
    assert gate.check_stand_freshness("2026-07-01", "2026-07-03")[0] == gate.OK   # 2 Tage (nicht > 2)


def test_stand_freshness_warn():
    assert gate.check_stand_freshness("2026-06-30", "2026-07-03")[0] == gate.WARN  # 3 Tage


def test_stand_freshness_fail():
    assert gate.check_stand_freshness("2026-06-25", "2026-07-03")[0] == gate.FAIL  # 8 Tage


def test_stand_freshness_unparsable():
    assert gate.check_stand_freshness("kaputt", "2026-07-03")[0] == gate.FAIL


def test_active_increment_named_block():
    assert gate.check_active_increment("governance-rebuild", _ROOT / "docs" / "adr")[0] == gate.OK


def test_active_increment_existing_adr(tmp_path):
    (tmp_path / "ADR-031.md").write_text("x", encoding="utf-8")
    assert gate.check_active_increment("ADR-031", tmp_path)[0] == gate.OK


def test_active_increment_missing_adr(tmp_path):
    assert gate.check_active_increment("ADR-999", tmp_path)[0] == gate.FAIL


def test_active_increment_empty():
    assert gate.check_active_increment("", _ROOT / "docs" / "adr")[0] == gate.FAIL


def test_count_tests(tmp_path):
    (tmp_path / "test_a.py").write_text(
        "def test_one():\n    pass\ndef test_two():\n    pass\n", encoding="utf-8")
    (tmp_path / "test_b.py").write_text("def test_three():\n    pass\n", encoding="utf-8")
    assert gate.count_tests(tmp_path) == 3


def test_highest_adr(tmp_path):
    (tmp_path / "ADR-000.md").write_text("x", encoding="utf-8")
    (tmp_path / "ADR-031.md").write_text("x", encoding="utf-8")
    assert gate.highest_adr(tmp_path) == 31


def test_handbook_purity_skip_when_missing():
    assert gate.check_handbook_purity(None)[0] == gate.SKIP


def test_handbook_purity_detects_status_token(tmp_path):
    hb = tmp_path / "HANDBOOK.md"
    hb.write_text("Der Router wurde umgesetzt in Phase 2.", encoding="utf-8")
    assert gate.check_handbook_purity(hb)[0] == gate.FAIL


def test_handbook_purity_clean(tmp_path):
    hb = tmp_path / "HANDBOOK.md"
    hb.write_text("Jarvis steht auf der Seite seines Nutzers.", encoding="utf-8")
    assert gate.check_handbook_purity(hb)[0] == gate.OK


# --- Produktions-Ruff (Truth Repair II, 14.07.2026) --------------------------

def test_production_ruff_clean_and_fail(tmp_path):
    """Clean-Repo -> OK; ein Lint-Befund im Produktionscode -> FAIL mit
    Beispielzeile. tests/ ist ausgenommen (dort bleibt Kompaktheit erlaubt)."""
    import pytest

    (tmp_path / "gut.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("a = 1; b = 2\n", encoding="utf-8")
    status, msg = gate.check_production_ruff(tmp_path)
    if status == gate.SKIP:
        pytest.skip("ruff nicht installiert - Check greift nur in der Dev-Umgebung")
    assert status == gate.OK, msg          # tests/-Befund zaehlt NICHT

    (tmp_path / "schlecht.py").write_text("import os; import sys\n", encoding="utf-8")
    status, msg = gate.check_production_ruff(tmp_path)
    assert status == gate.FAIL
    assert "schlecht.py" in msg            # Beispielzeile nennt die Fundstelle
