#!/usr/bin/env python3
"""
Generischer Projektstruktur-Generator (Governance-Umbau Chunk 5).

Leitet den Verzeichnis-/Dateibaum eines Projekts direkt aus dem Repository ab,
damit die Struktur nie wieder manuell gepflegt werden muss (und damit nie
wieder veraltet). Ersetzt handgepflegte Baumgrafiken.

Bewusst generisch und projektunabhaengig — wiederverwendbar als Baustein fuer
ein Projekt-Template:
- Root ist ein Parameter (Default: aktuelles Verzeichnis).
- Ignore-Liste konfigurierbar (sinnvolle Defaults fuer Build-/VCS-Artefakte).
- Nur Standardbibliothek.

Aufruf:
    python scripts/gen_structure.py [ROOT] [--max-depth N] [--ignore NAME ...]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_IGNORE = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "node_modules",
    ".idea", ".vscode", ".DS_Store", ".git_broken_5",
}


def build_tree(root, ignore=DEFAULT_IGNORE, max_depth=None) -> list[str]:
    """Baut den Struktur-Baum als Liste von Zeilen (rein, gut testbar).

    Verzeichnisse zuerst, dann Dateien, jeweils alphabetisch. Verzeichnisse
    enden auf '/'. Eintraege aus `ignore` werden ausgelassen."""
    root = Path(root)
    lines: list[str] = [root.name + "/"]

    def walk(directory: Path, prefix: str, depth: int) -> None:
        if max_depth is not None and depth > max_depth:
            return
        try:
            entries = [e for e in directory.iterdir() if e.name not in ignore]
        except (PermissionError, OSError):
            return
        entries.sort(key=lambda p: (p.is_file(), p.name.lower()))
        for i, entry in enumerate(entries):
            last = i == len(entries) - 1
            connector = "└── " if last else "├── "
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{prefix}{connector}{entry.name}{suffix}")
            if entry.is_dir():
                walk(entry, prefix + ("    " if last else "│   "), depth + 1)

    walk(root, "", 1)
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Projektstruktur aus dem Repository ableiten.")
    parser.add_argument("root", nargs="?", default=".", help="Wurzelverzeichnis (Default: .)")
    parser.add_argument("--max-depth", type=int, default=None, help="maximale Tiefe")
    parser.add_argument("--ignore", nargs="*", default=[], help="zusaetzliche Namen zum Ignorieren")
    args = parser.parse_args(argv)
    ignore = DEFAULT_IGNORE | set(args.ignore)
    # Die Baum-Zeichen (└── │) sind nicht in cp1252 - Ausgabe unabhaengig von
    # der Konsolen-Codierung als UTF-8 erzwingen.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover - z. B. umgeleiteter Stream
        pass
    for line in build_tree(args.root, ignore=ignore, max_depth=args.max_depth):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
