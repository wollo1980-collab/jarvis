"""Tests fuer scripts/export_public.py (Welle 4.2 Phase 3, Schaufenster).

Alle Personen-/Orts-Beispiele hier sind erfunden (Melchior/Musterhausen) -
die echte Ersetzungstabelle ist lokal und gitignoriert.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "export_public", _ROOT / "scripts" / "export_public.py"
)
xp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(xp)


def test_ship_list_keeps_code_tests_readme_license_and_adrs():
    tracked = [
        "README.md", "LICENSE", "setup.ps1", "config.example.json",
        "core/ai.py", "commands/news.py", "tests/test_ai.py",
        "docs/adr/ADR-001.md", "docs/assets/jarvis-ui.png",
    ]
    assert xp.ship_list(tracked) == tracked  # alles davon gehoert ins Schaufenster


def test_ship_list_excludes_private_docs_governance_and_hooks():
    tracked = [
        "docs/PROJECT_STATE.md", "docs/handbook/HANDBOOK.md", "docs/logbook.md",
        "docs/CHANGELOG.md", "CONTRIBUTING.md", "CHANGELOG.md",
        ".githooks/pre-commit",
        "core/ai.py",  # Kontrollprobe: Code bleibt
    ]
    assert xp.ship_list(tracked) == ["core/ai.py"]


def test_load_replacements_longest_first(tmp_path):
    (tmp_path / xp.REPLACEMENTS_FILENAME).write_text(
        "# Kommentar\nMelchior=>PO\nMelchiors=>POs\n\nkaputte zeile ohne pfeil\n",
        encoding="utf-8",
    )
    pairs = xp.load_replacements(tmp_path)
    assert pairs == [("Melchiors", "POs"), ("Melchior", "PO")]


def test_apply_replacements_handles_genitive_before_base():
    pairs = [("Melchiors", "POs"), ("Melchior", "PO")]
    text = "Melchiors Rechner gehoert Melchior."
    assert xp.apply_replacements(text, pairs) == "POs Rechner gehoert PO."


def _fake_repo(tmp_path: Path) -> tuple[Path, list[str]]:
    repo = tmp_path / "repo"
    (repo / "core").mkdir(parents=True)
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "core" / "x.py").write_text("# code\n", encoding="utf-8")
    (repo / "README.md").write_text("# Jarvis\n", encoding="utf-8")
    (repo / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (repo / "docs" / "adr" / "ADR-001.md").write_text(
        "Melchior wohnt in Musterhausen. Melchiors Entscheidung.\n", encoding="utf-8"
    )
    (repo / xp.REPLACEMENTS_FILENAME).write_text(
        "Melchiors=>POs\nMelchior=>PO\nMusterhausen=>Musterstadt\n", encoding="utf-8"
    )
    tracked = ["core/x.py", "README.md", "LICENSE", "docs/adr/ADR-001.md"]
    return repo, tracked


def test_export_copies_ship_set_and_cleans_adrs(tmp_path):
    repo, tracked = _fake_repo(tmp_path)
    target = tmp_path / "export"

    shipped = xp.export(repo, target, tracked=tracked)

    assert sorted(shipped) == sorted(tracked)
    assert (target / "core" / "x.py").read_text(encoding="utf-8") == "# code\n"
    adr = (target / "docs" / "adr" / "ADR-001.md").read_text(encoding="utf-8")
    assert adr == "PO wohnt in Musterstadt. POs Entscheidung.\n"
    # Die Ersetzungstabelle selbst wird NIE mitkopiert (nicht getrackt).
    assert not (target / xp.REPLACEMENTS_FILENAME).exists()


def test_export_refuses_foreign_nonempty_target(tmp_path):
    repo, tracked = _fake_repo(tmp_path)
    target = tmp_path / "fremd"
    target.mkdir()
    (target / "wichtig.txt").write_text("nicht anfassen", encoding="utf-8")

    with pytest.raises(SystemExit, match="kein[\\s\\S]*Export"):
        xp.export(repo, target, tracked=tracked)
    assert (target / "wichtig.txt").exists()  # nichts zerstoert


def test_export_replaces_previous_export_cleanly(tmp_path):
    repo, tracked = _fake_repo(tmp_path)
    target = tmp_path / "export"

    xp.export(repo, target, tracked=tracked)
    (target / "altlast.txt").write_text("aus altem Lauf", encoding="utf-8")
    xp.export(repo, target, tracked=tracked)  # Marker da -> frisch ersetzen

    assert not (target / "altlast.txt").exists()
    assert (target / "README.md").exists()


def test_export_never_destroys_git_history_in_target(tmp_path):
    """Jarvis-Eigenvorschlag 2026-07-10 (proposals/20260710-145018, erster
    selbst vorgeschlagener Plan): Der publizierte Klon lebt im Export-
    Verzeichnis - rmtree wuerde seine Git-Historie vernichten, und der
    Marker-Check greift genau dann nicht. Harter Abbruch, .git unangetastet."""
    repo, tracked = _fake_repo(tmp_path)
    target = tmp_path / "export"

    xp.export(repo, target, tracked=tracked)          # Erst-Export ok
    (target / ".git").mkdir()
    (target / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="Git-Historie"):
        xp.export(repo, target, tracked=tracked)

    assert (target / ".git" / "HEAD").exists()        # Historie unangetastet
