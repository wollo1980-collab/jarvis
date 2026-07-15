"""
PreToolUse-Hook fuer den Bau-Agenten (S4b Scheibe 2, ADR-071).

Die claude-CLI ruft dieses Skript VOR jedem Bash-Werkzeug-Aufruf des Agenten
auf (verdrahtet ueber die von core/hook_gate.write_hook_settings erzeugte
--settings-Datei). Ablauf:

1. Kuratiert-sicherer Befehl (Tests/Gate/git-lesen, CURATED_BASH)? -> KEINE
   Entscheidung; die normale CLI-Allowlist erlaubt ihn ohnehin.
2. Alles andere (git push, rm, freie Shell, Verkettungen) -> Frage an den PO
   ueber die Datei-Mailbox; die laufende Runtime pusht sie aufs Handy
   (Telegram, ja/nein).
3. Ja -> permissionDecision allow. Nein / keine Antwort / Runtime weg /
   IRGENDEIN Fehler -> deny (fail-closed, Pflock 2 des Wochenend-Bauplans).

Bewusst OHNE Jarvis-Importe ausser core/hook_gate (stdlib-only): das Skript
laeuft mit cwd = Ziel-Repo als eigener Prozess.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.hook_gate import HookMailbox, is_curated_bash  # noqa: E402


def _decision(allow: bool, reason: str) -> str:
    """Hook-Ausgabe im PreToolUse-Schema; zusaetzlich das aeltere Top-Level-
    decision-Feld (approve/block) fuer CLI-Versions-Toleranz."""
    verdict = "allow" if allow else "deny"
    return json.dumps({
        "decision": "approve" if allow else "block",
        "reason": reason,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": verdict,
            "permissionDecisionReason": reason,
        },
    }, ensure_ascii=False)


def decide(payload: dict, mailbox: HookMailbox, timeout: float) -> str:
    """Entscheidet fuer EINEN Werkzeug-Aufruf. Liefert '' (keine Entscheidung,
    normale Allowlist-Pruefung) oder das Entscheidungs-JSON."""
    tool = str(payload.get("tool_name") or "")
    if tool != "Bash":
        return ""                                  # andere Tools regelt die Allowlist
    tool_input = payload.get("tool_input") or {}
    command = str(tool_input.get("command") or "").strip()
    if not command:
        return _decision(False, "Leerer Bash-Befehl - abgelehnt (fail-closed).")
    if is_curated_bash(command):
        return ""                                  # kuratiert-sicher -> Allowlist erlaubt
    allowed = mailbox.ask("Bash", command, timeout=timeout)
    if allowed:
        return _decision(True, "Vom PO per Telegram freigegeben.")
    return _decision(False,
                     "Keine PO-Freigabe (nein/keine Antwort) - Befehl abgelehnt. "
                     "Arbeite ohne ihn weiter oder erklaere, was fehlt.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mailbox", required=True)
    parser.add_argument("--timeout", type=float, default=110.0)
    args = parser.parse_args()
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        out = decide(payload, HookMailbox(args.mailbox), args.timeout)
        if out:
            print(out)
        return 0
    except Exception:  # noqa: BLE001 - jede Panne = deny, nie fail-open
        print(_decision(False, "Hook-Fehler - abgelehnt (fail-closed)."))
        return 0


if __name__ == "__main__":
    sys.exit(main())
