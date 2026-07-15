"""
Verifikations-Harnisch (Endsystem-Kampagne B "Selbstkontrolle", ADR-055) -
das Fundament dafuer, dass Jarvis die Arbeit eines Agenten SELBST prueft,
statt dass ein Mensch die Verifikationsluecke fuellt. Ausgefuehrt wird ein
HART VERDRAHTETES Befehls-Whitelist in genau einem freigegebenen Repo:

  1. Konsistenz-Gate:  <python> scripts/check_consistency.py   (falls vorhanden)
  2. Testsuite:        <python> -m pytest -q --basetemp <frisch>

Sicherheitsmodell (der springende Punkt):
- Die argv-Liste jedes Befehls wird IM CODE gebaut, nie aus Nutzer- oder
  Modell-Eingabe. Die einzige Variable ist der Repo-PFAD - und der kommt
  ausschliesslich aus einer vom Aufrufer uebergebenen, gegen die
  Config-Allowlist validierten Pfad-Angabe (fail-closed).
- Kein Shell (shell=False), festes Timeout, Ausgabe gekappt. Es gibt KEIN
  freies Kommando - ein Agent im Kaefig bekommt hierdurch keine neue Macht,
  nur die Pruefung bekommt zwei feste Werkzeuge.
- Fail-safe: wirft nie; ein fehlender/fehlgeschlagener Befehl wird als
  solcher berichtet, nicht als Absturz.

Ausgefuehrt wird mit demselben Python, das Jarvis startet (sys.executable) -
fuer die eigenen Repos (jarvis/jkc) ist das der richtige Interpreter. Der
Harnisch AENDERT keinen Quellcode und committet nichts; er liest, laesst
laufen und berichtet.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.verify")

_DEFAULT_TIMEOUT = 420.0
_OUTPUT_TAIL_CHARS = 1500
_GATE_SCRIPT = "scripts/check_consistency.py"


def _run_command(argv: list, cwd: Path, timeout: float) -> dict:
    """Fuehrt EINEN festen Befehl aus (kein Shell) und liefert ein
    strukturiertes Ergebnis. Fail-safe: jeder Fehler wird zum Ergebnis, nie
    zur Exception."""
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, shell=False,
            # Kein Konsolen-Aufblitzen unter pythonw (PO-Befund 13.07.).
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        tail = output[-_OUTPUT_TAIL_CHARS:].strip()
        return {"ok": proc.returncode == 0, "returncode": proc.returncode, "tail": tail}
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": None, "tail": f"Zeitlimit ({timeout:.0f}s) ueberschritten."}
    except OSError as e:
        return {"ok": False, "returncode": None, "tail": f"Konnte Befehl nicht starten: {e}"}


def run_verification(
    repo_path: Path, python_exe: Optional[str] = None, timeout: float = _DEFAULT_TIMEOUT
) -> dict:
    """Fuehrt das Whitelist im Repo aus und liefert einen strukturierten
    Bericht. Kein Repo-Pfad aus Nutzer-/Modell-Eingabe - der Aufrufer hat
    ihn gegen die Allowlist validiert.

    Rueckgabe: {"repo": <name>, "checks": [{"name","ok","returncode","tail"}],
    "ok": <alle vorhandenen Checks gruen>}."""
    repo = Path(repo_path)
    python_exe = python_exe or sys.executable
    checks = []

    # 1) Konsistenz-Gate - nur wenn das Skript existiert (nicht jedes Repo hat es).
    gate_script = repo / _GATE_SCRIPT
    if gate_script.is_file():
        result = _run_command([python_exe, str(gate_script)], repo, timeout)
        checks.append({"name": "Konsistenz-Gate", **result})
    else:
        checks.append({
            "name": "Konsistenz-Gate", "ok": True, "returncode": None,
            "tail": "kein Gate-Skript im Repo - uebersprungen.", "skipped": True,
        })

    # 2) Testsuite - frisches basetemp, damit parallele/Sandbox-Laeufe sich
    #    nicht ins Gehege kommen.
    basetemp = Path(tempfile.mkdtemp(prefix="jarvis-verify-"))
    result = _run_command(
        [python_exe, "-m", "pytest", "-q", "--basetemp", str(basetemp)], repo, timeout
    )
    checks.append({"name": "Testsuite (pytest)", **result})

    # "ok" zaehlt nur echte (nicht uebersprungene) Checks.
    ok = all(c["ok"] for c in checks if not c.get("skipped"))
    logger.info("Verifikation %s: %s", repo.name, "bestanden" if ok else "durchgefallen")
    return {"repo": repo.name, "checks": checks, "ok": ok}
