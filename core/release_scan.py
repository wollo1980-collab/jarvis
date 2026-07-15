"""
Release-Hygiene-Scanner (Welle 4.1) - der Tuersteher vor jeder
Veroeffentlichung: prueft die GIT-GETRACKTEN Dateien (nur die wuerden
publiziert) auf Secrets, private Daten und Struktur-Suenden.

Vier Pruefklassen:
1. Secret-Muster (API-Keys, Bot-Tokens, private Schluessel, Passwort-
   Literale) - Wiederverwendung der Redaction-Idee (ADR-040), aber auf
   Dateien statt auf Gedaechtnis-Texte.
2. Verbotene getrackte Pfade (config.json, memory_data/, logs/, voices/,
   .env, die lokale Begriffsliste selbst) - was gitignoriert sein MUSS.
3. E-Mail-Adressen in getrackten Dateien (WARN - koennen legitim sein).
4. Persoenliche Begriffe aus einer LOKALEN, selbst gitignorierten Liste
   (release_scan_local_terms.txt, ein Begriff je Zeile, z. B. Wohnort) -
   die Begriffe stehen dadurch nie im Repo.

Ausnahmen sind explizit und begruendbar:
- Zeile:  ... # release-scan: ok (Begruendung)
- Datei:  "release-scan: datei-ok" in den ersten 5 Zeilen
  (z. B. tests mit bewusst erfundenen Beispiel-Secrets).

Gefundene Treffer werden MASKIERT ausgegeben - der Scanner plaudert nie
selbst aus, was er gefunden hat.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

LINE_PRAGMA = "release-scan: ok"
FILE_PRAGMA = "release-scan: datei-ok"
LOCAL_TERMS_FILENAME = "release_scan_local_terms.txt"

SECRET_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("API-Key (sk-...)", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("Telegram-Bot-Token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b")),
    ("AWS-Access-Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Privater Schluessel", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "Passwort-Literal",
        re.compile(r"(?i)\b(password|passwort|app_password|secret)\b\s*[=:]\s*['\"][^'\"]{6,}['\"]"),
    ),
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Pfade, die NIE getrackt sein duerfen (Vergleich case-insensitiv - Git
# unter Windows ist es auch).
FORBIDDEN_PREFIXES = ("memory_data/", "logs/", "voices/")
REPLACEMENTS_FILENAME = "export_replacements_local.txt"  # Welle 4.2 Phase 3
FORBIDDEN_FILES = ("config.json", ".env", LOCAL_TERMS_FILENAME, REPLACEMENTS_FILENAME)

# Nicht sinnvoll textuell scannbar.
_BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".ico", ".onnx", ".bin", ".wav", ".mp3", ".docx", ".pdf", ".zip"}
_MAX_FILE_BYTES = 2_000_000


@dataclass
class Finding:
    path: str
    line: int  # 0 = betrifft die Datei als Ganzes
    kind: str
    detail: str  # maskiert!
    severity: str  # "FAIL" | "WARN"


def mask(text: str) -> str:
    """Nie den Fund selbst ausplaudern: Anfang zeigen, Rest sternen."""
    text = text.strip()
    if len(text) <= 6:
        return "*" * len(text)
    return text[:4] + "*" * min(len(text) - 4, 12)


def tracked_files(repo_root: Path) -> list[str]:
    """Nur was Git kennt, wuerde veroeffentlicht."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        # Kein Konsolen-Aufblitzen unter pythonw (PO-Befund 13.07.).
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def load_local_terms(repo_root: Path) -> list[str]:
    """Persoenliche Begriffe aus der LOKALEN (gitignorierten) Liste."""
    path = repo_root / LOCAL_TERMS_FILENAME
    if not path.exists():
        return []
    terms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        term = line.strip()
        if term and not term.startswith("#"):
            terms.append(term)
    return terms


def scan_text(rel_path: str, content: str, local_terms: Optional[list[str]] = None) -> list[Finding]:
    """Kern-Scan einer Datei (pur, testbar ohne Git). E-Mail-Hinweise werden
    fuer tests/ unterdrueckt (erfundene Fixture-Adressen, sonst 18x
    Warn-Rauschen bei jedem Lauf) - Secret- und Begriffs-Pruefung gelten
    dort unveraendert."""
    findings: list[Finding] = []
    lines = content.splitlines()
    head = "\n".join(lines[:5])
    if FILE_PRAGMA in head:
        return []
    check_emails = not rel_path.lower().startswith("tests/")

    for number, line in enumerate(lines, start=1):
        if LINE_PRAGMA in line:
            continue
        for kind, pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if match:
                findings.append(Finding(rel_path, number, kind, mask(match.group(0)), "FAIL"))
        if check_emails:
            email = _EMAIL_RE.search(line)
            if email:
                findings.append(Finding(rel_path, number, "E-Mail-Adresse", mask(email.group(0)), "WARN"))
        for term in local_terms or []:
            # Ganzes Wort statt Teilstring (2026-07-11): so lassen sich auch
            # kurze Kuerzel sperren, ohne dass sie faelschlich in laengeren
            # Code-Woertern zuschlagen. Weiter case-insensitiv - die Kuerzel
            # tauchen mal gross, mal klein auf.
            if re.search(r"\b" + re.escape(term) + r"\b", line, re.IGNORECASE):
                findings.append(
                    Finding(rel_path, number, "Persoenlicher Begriff (lokale Liste)", mask(term), "FAIL")
                )
    return findings


def scan_repo(
    repo_root: Path,
    tracked: Optional[list[str]] = None,
    local_terms: Optional[list[str]] = None,
) -> list[Finding]:
    """Kompletter Scan: verbotene Pfade + Inhalt aller getrackten Dateien."""
    tracked = tracked if tracked is not None else tracked_files(repo_root)
    local_terms = local_terms if local_terms is not None else load_local_terms(repo_root)
    findings: list[Finding] = []

    for rel in tracked:
        lowered = rel.lower()
        if lowered in FORBIDDEN_FILES or any(lowered.startswith(p) for p in FORBIDDEN_PREFIXES):
            findings.append(
                Finding(rel, 0, "Verbotener getrackter Pfad", "gehoert in .gitignore, nicht ins Repo", "FAIL")
            )
            continue
        path = repo_root / rel
        if path.suffix.lower() in _BINARY_SUFFIXES:
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "\x00" in content[:1000]:
            continue  # binaer
        findings.extend(scan_text(rel, content, local_terms))

    return findings
