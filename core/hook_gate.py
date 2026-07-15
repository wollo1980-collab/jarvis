"""
Telegram-Erlaubnis-Haken fuers Folgenreiche (S4b Scheibe 2, Zuschnitt A).

Der Bau-Agent (claude -p) hat im Dev-Modus einen KURATIERTEN Werkzeugkasten
(CURATED_BASH: Tests/Gate/git-lesen). Alles DARUEBER hinaus (git push, rm,
freie Shell) faengt ein PreToolUse-Hook der CLI ab und fragt den PO ueber die
laufende Runtime per Telegram: "Der Agent moechte X - erlauben? (ja/nein)".

Dieses Modul ist die geteilte, stdlib-only Basis beider Seiten:
- HOOK-SEITE (scripts/agent_permission_hook.py, eigener Prozess): `ask()`
  schreibt eine Anfrage-Datei und wartet auf die Antwort-Datei - kommt keine,
  ist die Antwort NEIN (fail-closed, Pflock 2 des Wochenend-Bauplans).
- RUNTIME-SEITE (jarvis_runtime): `pending()` sieht offene Anfragen, `answer()`
  schreibt die PO-Entscheidung.

Die Vermittlung laeuft ueber Dateien in memory_dir/hook_requests (lokal, ein
Rechner, atomare Writes) - bewusst KEIN Netzwerk-Endpunkt: kein neuer
Angriffsweg, und ohne laufende Runtime gibt es schlicht keine Antwort = NEIN.

Sicherheits-Eigenschaften (ADR-071):
- Fail-closed an JEDER Bruchstelle: Hook stuerzt/fehlt/Timeout/Runtime weg ->
  deny. Die CLI-Allowlist bleibt eng; der Hook kann nur mit PO-Ja ERWEITERN.
- Kuratiert-sicheres (CURATED_BASH) entscheidet der Hook NICHT selbst - er
  gibt es an die normale Allowlist-Pruefung der CLI weiter (keine Doppel-Logik).
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path

logger = logging.getLogger("jarvis.hook_gate")

# Kuratierter DEV-Bash (Zuschnitt A "kuratiert weit", PO-Wahl 11.+13.07.):
# NUR sichere Dev-Befehle. SINGLE SOURCE - core/agent_backend._DEV_BASH und der
# Hook lesen BEIDE von hier (keine Drift zwischen Allowlist und Hook).
CURATED_BASH = (
    "Bash(pytest*)",
    "Bash(python -m pytest*)",
    "Bash(py -m pytest*)",
    "Bash(python scripts/check_consistency.py*)",
    "Bash(git status*)",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(git show*)",
    "Bash(git rev-parse*)",
    "Bash(git branch*)",
)

# Verkettungs-Zeichen: eine Kette ("pytest && rm -rf x") ist NIE kuratiert -
# die CLI prueft Teilbefehle einzeln, der Hook bleibt bewusst strenger.
_CHAIN_MARKERS = ("&&", "||", ";", "|", "`", "$(", "\n")


def is_curated_bash(command: str) -> bool:
    """True, wenn der Bash-Befehl von der kuratierten Allowlist abgedeckt ist -
    dann trifft der Hook KEINE Entscheidung (die CLI-Allowlist erlaubt ihn).
    Konservativ: Verkettungen/Substitutionen sind nie kuratiert."""
    cmd = (command or "").strip()
    if not cmd:
        return False
    if any(marker in cmd for marker in _CHAIN_MARKERS):
        return False
    for pattern in CURATED_BASH:
        inner = pattern[len("Bash("):-1]          # "pytest*"
        prefix = inner.rstrip("*")
        if inner.endswith("*"):
            if cmd.startswith(prefix):
                return True
        elif cmd == inner:
            return True
    return False


# Klartext-Einordnung (PO-Live-Befund 13.07.: "die Frage war Kauderwelsch") -
# deterministische Heuristik, die dem PO sagt, WAS eine Freigabe bedeutet.
# Erst-Token je Teilbefehl, der nur LIEST:
_READ_FIRST_TOKENS = frozenset({
    "ls", "dir", "cat", "type", "echo", "pwd", "whoami", "head", "tail",
    "tree", "wc", "find", "grep", "rg", "git", "python", "pytest", "where",
    "which",
})
# git-Unterbefehle, die nur lesen (git selbst ist sonst NICHT lesend):
_GIT_READ_SUBCOMMANDS = frozenset({
    "log", "status", "diff", "show", "branch", "rev-parse", "blame", "shortlog",
})
# Marker, die auf Veraendern/Loeschen/Senden deuten (Token-genau, kein
# Substring - "rm" darf nicht auf "format" anschlagen; ">" faellt extra auf):
_RISK_TOKENS = frozenset({
    "rm", "del", "rmdir", "push", "force", "--force", "-rf", "format", "mkfs",
    "shutdown", "reboot", "curl", "wget", "install", "uninstall", "reg",
    "schtasks", "taskkill", "mklink", "move", "mv", "cp", "copy", "chmod",
    "chown", "commit", "reset", "checkout", "clean", "merge", "rebase", "pip",
    "npm", "setx",
})


def classify_command(command: str) -> tuple[str, str]:
    """Deterministische Klartext-Einordnung eines Bash-Befehls fuer die
    Erlaubnis-Frage: (stufe, text) mit stufe in {"lesend","riskant","unklar"}.
    Konservativ: riskant schlaegt lesend; Unbekanntes ist unklar."""
    cmd = (command or "").strip()
    if not cmd:
        return "unklar", "Leerer Befehl — im Zweifel Nein."
    lowered = cmd.lower()
    tokens = re.findall(r"[a-z0-9_.:/\\-]+", lowered)
    if (">" in lowered) or any(t in _RISK_TOKENS for t in tokens):
        return "riskant", "⚠️ Kann etwas verändern, löschen oder nach außen senden."
    parts = re.split(r"&&|\|\||;|\|", lowered)
    all_read = True
    for part in parts:
        words = part.strip().split()
        if not words:
            continue
        first = words[0]
        if first not in _READ_FIRST_TOKENS:
            all_read = False
            break
        if first == "git" and (len(words) < 2 or words[1] not in _GIT_READ_SUBCOMMANDS):
            all_read = False
            break
    if all_read:
        return "lesend", "Nur-Lese-Befehl(e): zeigt Inhalte an, ändert nichts."
    return "unklar", "Wirkung nicht eindeutig einzuordnen — im Zweifel Nein."


class HookMailbox:
    """Datei-Briefkasten zwischen Hook-Prozess und Runtime. Atomar ueber
    os.replace (gleiches Muster wie core/fileio, hier stdlib-only dupliziert,
    damit der Hook-Prozess keine Jarvis-Importe braucht)."""

    def __init__(self, directory):
        self.dir = Path(directory)

    def _write_json(self, path: Path, data: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    # --- Hook-Seite -------------------------------------------------------

    def ask(self, tool: str, command: str, timeout: float = 110.0,
            poll: float = 0.5) -> bool:
        """Stellt die Frage und WARTET auf die PO-Antwort. False bei Timeout,
        fehlender Runtime oder jedem Fehler (fail-closed)."""
        req_id = uuid.uuid4().hex[:12]
        req = self.dir / f"q_{req_id}.json"
        res = self.dir / f"a_{req_id}.json"
        try:
            self._write_json(req, {"id": req_id, "tool": tool,
                                   "command": command, "ts": time.time()})
            deadline = time.monotonic() + max(1.0, timeout)
            while time.monotonic() < deadline:
                if res.exists():
                    data = json.loads(res.read_text(encoding="utf-8") or "{}")
                    return bool(data.get("allow"))
                time.sleep(poll)
            return False
        except Exception:  # noqa: BLE001 - jede Panne = NEIN
            return False
        finally:
            for p in (req, res):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass

    # --- Runtime-Seite ------------------------------------------------------

    def pending(self) -> list[dict]:
        """Offene (unbeantwortete) Anfragen, aelteste zuerst. Fail-safe leer."""
        try:
            if not self.dir.is_dir():
                return []
            out = []
            for req in sorted(self.dir.glob("q_*.json")):
                if (self.dir / f"a_{req.stem[2:]}.json").exists():
                    continue
                try:
                    data = json.loads(req.read_text(encoding="utf-8") or "{}")
                except (OSError, ValueError):
                    continue
                if data.get("id"):
                    out.append(data)
            return out
        except Exception:  # noqa: BLE001
            return []

    def answer(self, req_id: str, allow: bool) -> None:
        """Schreibt die PO-Entscheidung. Fail-safe (Fehler = keine Antwort =
        der Hook laeuft in seinen Timeout = NEIN)."""
        safe = "".join(c for c in str(req_id) if c.isalnum())[:32]
        if not safe:
            return
        try:
            self._write_json(self.dir / f"a_{safe}.json", {"allow": bool(allow)})
        except Exception:  # noqa: BLE001
            logger.warning("HookMailbox: Antwort konnte nicht geschrieben werden.", exc_info=True)


def write_hook_settings(settings_path, hook_script, mailbox_dir,
                        timeout_seconds: int = 110) -> Path:
    """Erzeugt die --settings-Datei fuer die claude-CLI: ein PreToolUse-Hook auf
    Bash-Aufrufe, der das Hook-Skript mit Mailbox-Pfad + Timeout als ARGUMENTE
    aufruft (kein Env-Gefummel; laeuft mit cwd=Zielrepo, darum absolute Pfade).
    Der CLI-Hook-Timeout liegt BEWUSST ueber dem Frage-Timeout, damit die
    saubere Deny-Antwort des Skripts gewinnt (nie der harte CLI-Abbruch)."""
    settings_path = Path(settings_path)
    command = (
        f'"{sys.executable}" "{Path(hook_script).resolve()}" '
        f'--mailbox "{Path(mailbox_dir).resolve()}" --timeout {int(timeout_seconds)}'
    )
    payload = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": command,
                         "timeout": int(timeout_seconds) + 15},
                    ],
                }
            ]
        }
    }
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    return settings_path
