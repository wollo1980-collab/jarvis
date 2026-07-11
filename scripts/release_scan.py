"""
CLI des Release-Hygiene-Scanners (Welle 4.1) - Muster wie
scripts/check_consistency.py: [OK]/[WARN]/[FAIL]-Zeilen, Exit-Code 1 bei
FAIL (WARNs blockieren nicht, sollen aber gelesen werden).

Aufruf:  .venv\\Scripts\\python.exe scripts\\release_scan.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.release_scan import LOCAL_TERMS_FILENAME, load_local_terms, scan_repo  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    terms = load_local_terms(REPO_ROOT)
    if terms:
        print(f"[OK]   Lokale Begriffsliste: {len(terms)} Begriffe ({LOCAL_TERMS_FILENAME})")
    else:
        print(
            f"[WARN] Keine lokale Begriffsliste ({LOCAL_TERMS_FILENAME}) - "
            "persoenliche Begriffe (z. B. Wohnort) werden nicht geprueft."
        )

    findings = scan_repo(REPO_ROOT, local_terms=terms)
    fails = [f for f in findings if f.severity == "FAIL"]
    warns = [f for f in findings if f.severity == "WARN"]

    for f in fails + warns:
        where = f"{f.path}:{f.line}" if f.line else f.path
        print(f"[{f.severity}] {where} - {f.kind}: {f.detail}")

    print("-" * 60)
    if fails:
        print(f"ERGEBNIS: FAIL ({len(fails)} kritisch, {len(warns)} Hinweise) - NICHT veroeffentlichen.")
        return 1
    print(f"ERGEBNIS: PASS ({len(warns)} Hinweise) - keine kritischen Funde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
