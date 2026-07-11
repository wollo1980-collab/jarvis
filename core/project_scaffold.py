"""
Projektgeruest nach AI-Project-Framework (ADR-049, Projektentwickler-
Kampagne Stufe 1) - die MECHANISCHE Haelfte des Projektstarts:

PROJECT_INIT.md des Frameworks verlangt fuer Greenfield-Zielprojekte ein
eigenes Git-Repository AUSSERHALB des Framework-Repos, einen fruehen ersten
Commit und die logbook-Pflichtzeile "Abgeleitet aus AI Project Framework
Commit <hash> am <Datum>" (inkl. charter_version, falls vorhanden). Genau
das erzeugt scaffold_project() - deterministisch, ohne LLM.

Die INHALTLICHE Haelfte (Zweck, Vision, MVP, Stack) kommt laut Framework
aus dem Onboarding-Interview mit dem PO und wird hier bewusst NICHT
erfunden: die erzeugten Dokumente sagen ehrlich "Onboarding ausstehend".

Sicherheit: Das Framework-Repo wird ausschliesslich GELESEN (rev-parse,
zwei Dateien). Geschrieben wird nur UNTERHALB von projects_root, nie in
ein existierendes Verzeichnis, nie mit Remote/Push.
"""
from __future__ import annotations

import logging
import re
import subprocess
from datetime import date
from pathlib import Path

logger = logging.getLogger("jarvis.project_scaffold")

# Projektname = Verzeichnis- und Repo-Name: klein, mit Bindestrich,
# keine Pfad-Tricks ("..", Laufwerke, Umlaute).
_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,39}$")

_GITIGNORE = """__pycache__/
*.pyc
.venv/
.pytest_cache/
"""

_PYTEST_INI = """[pytest]
testpaths = tests
"""


def _run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def framework_commit(framework_dir: Path) -> str:
    """Kurzer Commit-Hash des Framework-Repos (READ-ONLY-Zugriff)."""
    return _run_git(["rev-parse", "--short", "HEAD"], framework_dir)


def framework_charter_version(framework_dir: Path) -> str:
    """charter_version aus der Framework-CONTRIBUTING.md ("" wenn keine)."""
    path = framework_dir / "CONTRIBUTING.md"
    if not path.exists():
        return ""
    match = re.search(
        r"^charter_version:\s*(\S+)", path.read_text(encoding="utf-8"), re.MULTILINE
    )
    return match.group(1) if match else ""


def validate_name(name: str) -> str:
    """Normalisiert und prueft den Projektnamen; ValueError bei Murks."""
    slug = name.strip().lower()
    if not _NAME_RE.match(slug):
        raise ValueError(
            f"Ungueltiger Projektname {name!r} - erlaubt: klein, a-z/0-9/Bindestrich, "
            "2-40 Zeichen, beginnend mit Buchstabe."
        )
    return slug


def scaffold_project(projects_root: Path, name: str, framework_dir: Path) -> Path:
    """Erzeugt <projects_root>/<name> als eigenstaendiges Git-Repo nach
    PROJECT_INIT (Geruest + Pflichtzeile + frueher erster Commit). Wirft
    ValueError bei Verstoessen (existiert schon, Name ungueltig, Framework
    nicht auffindbar) - der Command uebersetzt in Persona-Antworten."""
    slug = validate_name(name)
    if not projects_root.is_dir():
        raise ValueError(f"projects_root existiert nicht: {projects_root}")
    if not (framework_dir / "docs" / "PROJECT_INIT.md").exists():
        raise ValueError(
            f"Framework-Repo nicht gefunden (docs/PROJECT_INIT.md fehlt): {framework_dir}"
        )

    target = (projects_root / slug).resolve()
    if projects_root.resolve() not in target.parents:
        raise ValueError(f"Zielverzeichnis liegt ausserhalb von projects_root: {target}")
    if target.exists():
        raise ValueError(f"Verzeichnis existiert bereits: {target} - ich ueberschreibe nichts.")

    commit = framework_commit(framework_dir)
    charter = framework_charter_version(framework_dir)
    today = date.today().isoformat()
    charter_note = f", charter_version {charter}" if charter else ""

    (target / "docs" / "adr").mkdir(parents=True)
    (target / "tests").mkdir()

    _write(target / "README.md", (
        f"# {slug}\n\n"
        "Zielprojekt nach dem AI Project Framework. Zweck, Produktvision und\n"
        "MVP werden im Onboarding-Interview mit dem PO festgelegt\n"
        "(PROJECT_INIT Schritt 2) und danach hier eingetragen.\n"
    ))
    _write(target / "docs" / "PROJECT_STATE.md", (
        "---\n"
        'version: "0.0 - Onboarding ausstehend"\n'
        "active_increment: projektstart\n"
        "tests: 1\n"
        f"stand: {today}\n"
        "---\n\n"
        "# PROJECT STATE\n\n"
        "## Status\n\n"
        "Geruest erzeugt (PROJECT_INIT Schritt 3, mechanischer Teil). Vor dem\n"
        "ersten Code: Onboarding-Interview (Schritt 2) und Projektanalyse\n"
        "(Schritt 4) mit PO-Freigabe.\n"
    ))
    _write(target / "docs" / "CHANGELOG.md",
           "# Changelog\n\n(leer - erster Eintrag mit dem ersten nutzerseitigen Ergebnis)\n")
    _write(target / "docs" / "logbook.md", (
        "# Logbook\n\n"
        f"## {today} - Projektstart\n\n"
        f"Abgeleitet aus AI Project Framework Commit `{commit}` am {today}{charter_note}.\n\n"
        "Geruest erzeugt von Jarvis (`start_project`, ADR-049 des Jarvis-Repos) -\n"
        "deterministische Schablone, kein LLM. Onboarding-Interview und\n"
        "Projektanalyse stehen aus; bis dahin kein Produktcode.\n"
    ))
    _write(target / "docs" / "framework_feedback.md", (
        "# Framework-Feedback\n\n"
        "Rueckfluss-Vorschlaege ans AI Project Framework (CONTRIBUTING.md\n"
        "Abschnitt 15): Herkunft, konkreter Beleg, Aenderungsvorschlag.\n"
    ))
    adr_template = framework_dir / "docs" / "adr" / "ADR-TEMPLATE.md"
    if adr_template.exists():  # "woertlich uebernehmen" (PROJECT_INIT)
        _write(target / "docs" / "adr" / "ADR-TEMPLATE.md",
               adr_template.read_text(encoding="utf-8"))
    _write(target / ".gitignore", _GITIGNORE)
    _write(target / "pytest.ini", _PYTEST_INI)
    _write(target / "tests" / "test_smoke.py", (
        '"""Rauchtest des Geruests: die Governance-Dokumente existieren."""\n'
        "from pathlib import Path\n\n"
        "ROOT = Path(__file__).resolve().parents[1]\n\n\n"
        "def test_governance_documents_exist():\n"
        '    for rel in ("README.md", "docs/PROJECT_STATE.md", "docs/logbook.md"):\n'
        "        assert (ROOT / rel).exists(), rel\n"
    ))

    _run_git(["init", "-b", "main"], target)
    _run_git(["add", "-A"], target)
    _run_git([
        "-c", "user.name=Jarvis",
        "-c", "user.email=jarvis@local",
        "commit", "-m",
        f"chore: Projektstart - Geruest nach PROJECT_INIT (Framework {commit})",
    ], target)
    logger.info("Projektgeruest erzeugt: %s (Framework-Commit %s).", target, commit)
    return target


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
