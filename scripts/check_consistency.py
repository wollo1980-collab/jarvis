#!/usr/bin/env python3
"""
Konsistenz-Gate (Governance-Umbau, siehe CONTRIBUTING §7).

Prueft mechanisch, dass der maschinenlesbare Kopf von docs/PROJECT_STATE.md mit
der Repository-Realitaet uebereinstimmt - damit Dokumentation und tatsaechlicher
Stand nicht mehr stillschweigend auseinanderlaufen.

Nur stdlib + git. Aufruf:  python scripts/check_consistency.py
Exit 0 = PASS (ggf. mit WARN), Exit 1 = FAIL. FAIL -> STOP (nicht bauen/committen).

Checks:
  1. Testzahl          - gezaehlte 'def test_' in tests/ == Kopf 'tests'
  2. Letzte ADR        - hoechste docs/adr/ADR-NNN.md == Kopf 'latest_adr'
  3. active_increment  - 'ADR-<n>' (Datei muss existieren) ODER benannter Block
  4. Stand-Frische     - Abstand Kopf 'stand' <-> HEAD-Commit-Datum (WARN >2d, FAIL >7d)
  5. Handbook-Reinheit - Handbook enthaelt keine Status-Tokens (temporaer SKIP,
                         solange kein HANDBOOK.md existiert -> nach Markdown-Migration aktiv)
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

OK, WARN, FAIL, SKIP = "OK", "WARN", "FAIL", "SKIP"

ROOT = Path(__file__).resolve().parent.parent

# Stand-Frische-Schwellen (PO-Entscheidung 2026-07-03): frueh warnen, spaet blocken.
STAND_WARN_DAYS = 2
STAND_FAIL_DAYS = 7

# Status-Tokens, die in der Projektverfassung (Handbook) NICHT vorkommen duerfen
# (Handbook = zeitlos, kein Umsetzungs-/Phasenstatus; siehe CONTRIBUTING Grenzregeln).
HANDBOOK_FORBIDDEN = [
    re.compile(r"umgesetzt in", re.I),
    re.compile(r"noch nicht begonnen", re.I),
    re.compile(r"\d+\s*/\s*\d+\s*(tests|gr[üu]n|bestanden)", re.I),
]


def parse_frontmatter(text: str) -> dict:
    """Minimaler 'key: value'-Frontmatter-Parser (dependency-frei, kein PyYAML)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def count_tests(tests_dir: Path) -> int:
    """Bewusst einfache, dependency-freie Zaehlung (top-level 'def test_').
    Gegen pytest verifiziert fuer die aktuelle, flache Suite. Bei kuenftiger
    Parametrisierung/Test-Klassen ggf. durch 'pytest --collect-only -q' ersetzen."""
    pattern = re.compile(r"^def test_\w+", re.M)
    return sum(len(pattern.findall(p.read_text(encoding="utf-8")))
               for p in sorted(tests_dir.rglob("*.py")))


def highest_adr(adr_dir: Path):
    nums = [int(m.group(1)) for p in adr_dir.glob("ADR-*.md")
            if (m := re.match(r"ADR-0*(\d+)\.md$", p.name))]
    return max(nums) if nums else None


def check_tests(root: Path, expected: str):
    actual = count_tests(root / "tests")
    if str(actual) == str(expected):
        return OK, f"Testzahl: {actual} == Kopf (tests: {expected})"
    return FAIL, f"Testzahl: real {actual} != Kopf (tests: {expected})"


def check_latest_adr(root: Path, expected: str):
    actual = highest_adr(root / "docs" / "adr")
    if actual is not None and str(actual) == str(expected):
        return OK, f"Letzte ADR: {actual} == Kopf (latest_adr: {expected})"
    return FAIL, f"Letzte ADR: real {actual} != Kopf (latest_adr: {expected})"


def check_active_increment(value: str, adr_dir: Path):
    if not value:
        return FAIL, "active_increment: leer"
    m = re.fullmatch(r"ADR-0*(\d+)", value)
    if m:
        fname = f"ADR-{int(m.group(1)):03d}.md"
        if (adr_dir / fname).exists():
            return OK, f"active_increment: {value} (ADR existiert)"
        return FAIL, f"active_increment: {value} - ADR-Datei {fname} fehlt"
    return OK, f"active_increment: '{value}' (benannter Block)"


def check_stand_freshness(stand: str, head_date: str,
                          warn_days: int = STAND_WARN_DAYS,
                          fail_days: int = STAND_FAIL_DAYS):
    try:
        s = datetime.strptime(stand, "%Y-%m-%d").date()
        h = datetime.strptime(head_date, "%Y-%m-%d").date()
    except ValueError:
        return FAIL, f"Stand-Frische: Datum nicht parsebar (stand={stand!r}, HEAD={head_date!r})"
    delta = (h - s).days
    base = f"stand={stand}, HEAD={head_date}, Abstand {delta} Tage"
    if delta > fail_days:
        return FAIL, f"Stand-Frische: {base} (> {fail_days}d)"
    if delta > warn_days:
        return WARN, f"Stand-Frische: {base} (> {warn_days}d)"
    return OK, f"Stand-Frische: {base}"


def find_handbook_md(root: Path):
    for p in (root / "docs").rglob("HANDBOOK.md"):
        return p
    p = root / "HANDBOOK.md"
    return p if p.exists() else None


def check_handbook_purity(handbook_path):
    if handbook_path is None:
        return SKIP, ("Handbook-Reinheit: temporaer uebersprungen - kein HANDBOOK.md vorhanden "
                      "(Handbook noch als .docx). Check wird nach der Markdown-Migration aktiv.")
    text = handbook_path.read_text(encoding="utf-8")
    hits = [p.pattern for p in HANDBOOK_FORBIDDEN if p.search(text)]
    if hits:
        return FAIL, f"Handbook-Reinheit: Status-Tokens im Handbook gefunden: {hits}"
    return OK, "Handbook-Reinheit: keine Status-Tokens im Handbook"


def git_head_date(root: Path):
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%cd", "--date=short"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def main() -> int:
    fm = parse_frontmatter((ROOT / "docs" / "PROJECT_STATE.md").read_text(encoding="utf-8"))
    if not fm:
        return _report([(FAIL, "PROJECT_STATE: kein maschinenlesbarer Kopf (Frontmatter) gefunden")])

    results = [
        check_tests(ROOT, fm.get("tests", "")),
        check_latest_adr(ROOT, fm.get("latest_adr", "")),
        check_active_increment(fm.get("active_increment", ""), ROOT / "docs" / "adr"),
    ]
    head = git_head_date(ROOT)
    results.append((SKIP, "Stand-Frische: uebersprungen - kein Git-Commit-Datum ermittelbar")
                   if head is None else check_stand_freshness(fm.get("stand", ""), head))
    results.append(check_handbook_purity(find_handbook_md(ROOT)))
    return _report(results)


def _report(results) -> int:
    label = {OK: "[OK]  ", WARN: "[WARN]", FAIL: "[FAIL]", SKIP: "[SKIP]"}
    for status, msg in results:
        print(f"{label[status]} {msg}")
    n_fail = sum(1 for s, _ in results if s == FAIL)
    n_warn = sum(1 for s, _ in results if s == WARN)
    print("-" * 60)
    if n_fail:
        print(f"ERGEBNIS: FAIL ({n_fail} FAIL, {n_warn} WARN) - STOP: nicht bauen/committen.")
        return 1
    print(f"ERGEBNIS: PASS ({n_warn} WARN)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
