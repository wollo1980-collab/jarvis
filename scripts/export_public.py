"""
Schaufenster-Export (Welle 4.2 Phase 3, PO-Entscheidungen 10.07.2026).

Kopiert das PO-freigegebene Ship-Set in ein frisches Export-Verzeichnis,
aus dem das oeffentliche Repo entsteht:

  Ship-Set  = alle git-getrackten Dateien AUSSER
              - docs/** (nur docs/adr/** bleibt - "nur ADRs, bereinigt")
              - CONTRIBUTING.md, CHANGELOG.md (Governance/Verweis = privat)
              - .githooks/** (Hook braucht das private Konsistenz-Gate)
  Bereinigt = Ersetzungstabelle aus export_replacements_local.txt (lokal,
              gitignoriert - Original-Begriffe stehen nie im Repo) wird auf
              docs/adr/*.md angewendet; Code/Tests/README sind seit Phase 1
              sauber (Nachweis: Release-Scanner).
  Tuersteher = core.release_scan.scan_repo laeuft ueber den fertigen Export
              mit der lokalen Begriffsliste des Privat-Repos. FAIL => Exit 1,
              es wird nichts publiziert.

Bewusst NICHT Teil dieses Skripts: git init/push - die Publikation bleibt
ein eigener, manueller Schritt nach PO-Sichtung des Exports.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))  # release-scan: ok (Import des eigenen core-Pakets)

from core.release_scan import (  # noqa: E402
    REPLACEMENTS_FILENAME,
    load_local_terms,
    scan_repo,
    tracked_files,
)

# Was NICHT ins Schaufenster gehoert (PO-Entscheidung 10.07.2026:
# Ship-Set = Code + Tests + README + nur ADRs; Handbook/Prozess privat).
# docs/assets/ = README-Bilder (neutraler UI-Screenshot), gehoert dazu.
EXCLUDED_PREFIXES = ("docs/", ".githooks/")
KEPT_PREFIXES = ("docs/adr/", "docs/assets/")
EXCLUDED_FILES = ("contributing.md", "changelog.md")

# Die Ersetzungstabelle wird nur auf die ADRs angewendet - Code/Tests/README
# sind seit Phase 1 entpersonalisiert; dort ersetzt niemand blind Woerter.
REPLACE_PREFIX = "docs/adr/"

_MARKER = ".jarvis-public-export"  # kennzeichnet ein Verzeichnis als Export-Ziel


def ship_list(tracked: list[str]) -> list[str]:
    """Filtert die getrackte Dateiliste auf das Ship-Set."""
    shipped = []
    for rel in tracked:
        lowered = rel.lower().replace("\\", "/")
        if lowered in EXCLUDED_FILES:
            continue
        if any(lowered.startswith(k) for k in KEPT_PREFIXES):
            shipped.append(rel)
            continue
        if any(lowered.startswith(p) for p in EXCLUDED_PREFIXES):
            continue
        shipped.append(rel)
    return shipped


def load_replacements(repo_root: Path) -> list[tuple[str, str]]:
    """Ersetzungstabelle aus der lokalen (gitignorierten) Datei.
    Format: alt=>neu, eine je Zeile. Laengere Muster zuerst anwenden,
    damit z. B. der Genitiv nicht vom kuerzeren Grundwort zerschnitten wird."""
    path = repo_root / REPLACEMENTS_FILENAME
    if not path.exists():
        return []
    pairs: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=>" not in line:
            continue
        old, new = line.split("=>", 1)
        if old:
            pairs.append((old, new))
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


def apply_replacements(text: str, replacements: list[tuple[str, str]]) -> str:
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def export(repo_root: Path, target: Path, tracked: list[str] | None = None) -> list[str]:
    """Kopiert das Ship-Set nach `target` (frisch), wendet die
    Ersetzungstabelle auf die ADRs an. Gibt die Liste der exportierten
    relativen Pfade zurueck."""
    tracked = tracked if tracked is not None else tracked_files(repo_root)
    shipped = ship_list(tracked)
    replacements = load_replacements(repo_root)

    if target.exists():
        if not (target / _MARKER).exists() and any(target.iterdir()):
            raise SystemExit(
                f"Zielverzeichnis {target} existiert, ist nicht leer und kein "
                f"frueherer Export (Marker {_MARKER} fehlt) - breche ab, um "
                "nichts Fremdes zu ueberschreiben."
            )
        # .git-Schutz (Jarvis-Eigenvorschlag 2026-07-10, proposals/20260710-
        # 145018): der publizierte Klon lebt im Export-Verzeichnis - ein
        # rmtree wuerde seine lokale Git-Historie ersatzlos vernichten. Der
        # Marker-Check greift hier nicht (das Verzeichnis IST der erkannte
        # Export). Harter Abbruch, bewusst ohne --force: destruktive
        # Publikations-Schritte bleiben Handarbeit des PO.
        if (target / ".git").is_dir():
            raise SystemExit(
                f"Zielverzeichnis {target} enthaelt ein Git-Repo (.git) - "
                "vermutlich der publizierte Klon. Bitte bewusst von Hand "
                "verschieben/loeschen, bevor neu exportiert wird; dieses "
                "Skript vernichtet keine Git-Historie."
            )
        shutil.rmtree(target)
    target.mkdir(parents=True)
    (target / _MARKER).write_text("Erzeugt von scripts/export_public.py\n", encoding="utf-8")

    for rel in shipped:
        src = repo_root / rel
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel.lower().replace("\\", "/").startswith(REPLACE_PREFIX) and replacements:
            content = src.read_text(encoding="utf-8", errors="replace")
            dst.write_text(apply_replacements(content, replacements), encoding="utf-8", newline="\n")
        else:
            shutil.copy2(src, dst)
    return shipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Schaufenster-Export (Welle 4.2 Phase 3)")
    parser.add_argument(
        "--target",
        type=Path,
        default=_REPO_ROOT.parent / "jarvis-public-export",
        help="Export-Zielverzeichnis (Default: ../jarvis-public-export)",
    )
    args = parser.parse_args()

    shipped = export(_REPO_ROOT, args.target)
    print(f"Exportiert: {len(shipped)} Dateien -> {args.target}")
    for must in ("README.md", "LICENSE"):
        if must not in shipped:
            print(f"[FAIL] Pflichtdatei fehlt im Ship-Set: {must}")
            return 1

    # Tuersteher: derselbe Scanner wie Welle 4.1, aber ueber den EXPORT -
    # mit der lokalen Begriffsliste des Privat-Repos.
    terms = load_local_terms(_REPO_ROOT)
    findings = scan_repo(args.target, tracked=shipped, local_terms=terms)
    fails = [f for f in findings if f.severity == "FAIL"]
    warns = [f for f in findings if f.severity == "WARN"]
    for f in fails + warns:
        print(f"[{f.severity}] {f.path}:{f.line} {f.kind}: {f.detail}")
    print("-" * 60)
    if fails:
        print(f"ERGEBNIS: FAIL ({len(fails)} FAIL, {len(warns)} WARN) - NICHT publizieren.")
        return 1
    print(f"ERGEBNIS: PASS ({len(warns)} WARN) - Export bereit zur PO-Sichtung.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
