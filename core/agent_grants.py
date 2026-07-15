"""
Schreib-Freigabe-Brücke für frisch angelegte Projekte (ADR-059).

„Bau mir X" legt ein neues Projekt unter `projects_root` an und muss es DANN
für den Bau-Agenten schreibbar machen — `agent_write_repos` ist aber fail-closed
(ein frisches Projekt steht dort nicht). Diese Datei trägt die WÄCHTER-PRÜFUNG:
darf genau dieser Pfad freigegeben werden?

Die vier Wächter (fail-closed):
1. nur UNTER `projects_root` (Config),
2. nicht `projects_root` selbst (nur echte Unterprojekte),
3. NIE Jarvis' eigenes Repo (`BASE_DIR`) — auch nicht darunter,
4. (Sitzungs-Begrenzung + „nur frisch angelegt" erzwingt der Aufrufer: die
   Freigabe wird nur IN-MEMORY in die Allowlist eingetragen, nie persistiert →
   nach einem Neustart ist alles wieder zu; eingetragen wird nur direkt nach
   `start_project`).

Bewusst nur die PRÜFUNG hier (an EINER testbaren Stelle); die eigentliche
Eintragung in die (In-Memory-)Schreib-Allowlist macht der Aufrufer
(commands/delegate.py), damit die bestehende Delegations-Maschinerie
unverändert greift.
"""
from __future__ import annotations

import logging
from pathlib import Path

from core.config import BASE_DIR

logger = logging.getLogger("jarvis.agent_grants")


def _is_under(child: Path, parent: Path) -> bool:
    """True, wenn child == parent ODER darunter liegt."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def may_grant(path, projects_root) -> bool:
    """Darf dieses frisch angelegte Projekt schreibbar gemacht werden?
    Nur unter projects_root, nicht projects_root selbst, und NIE Jarvis' eigenes
    Repo (oder darunter). Sonst False (fail-closed). Wirft nie."""
    if not projects_root:
        return False
    try:
        target = Path(path).resolve()
        root = Path(projects_root).resolve()
        base = Path(BASE_DIR).resolve()
    except OSError:
        return False

    if target == base or _is_under(target, base):
        logger.warning("Schreib-Freigabe verweigert: %s ist Jarvis' eigenes Repo (oder darunter).", target)
        return False
    if target == root:
        logger.warning("Schreib-Freigabe verweigert: %s ist die Projektwurzel selbst, kein Unterprojekt.", target)
        return False
    if not _is_under(target, root):
        logger.warning("Schreib-Freigabe verweigert: %s liegt nicht unter projects_root %s.", target, root)
        return False
    return True


def is_framework_scaffold(path) -> bool:
    """True, wenn `path` ein von JARVIS nach dem AI Project Framework angelegtes
    Projektgeruest ist (ADR-069): docs/PROJECT_STATE.md existiert UND docs/logbook.md
    traegt die PROJECT_INIT-Pflichtzeile 'Abgeleitet aus AI Project Framework'.

    Zweck: den Wiedereinstieg von `build_project` NUR auf echte, von Jarvis selbst
    erzeugte Projekte begrenzen - ein beliebiger Nachbarordner unter projects_root
    (z. B. der oeffentliche Export) traegt diese Zeile NICHT und wird so NIE ueber
    den Wiedereinstieg schreibbar. Ergaenzt may_grant (das Selbst-Repo/Wurzel
    sperrt), ersetzt es nicht. Wirft nie."""
    try:
        base = Path(path)
        state = base / "docs" / "PROJECT_STATE.md"
        logbook = base / "docs" / "logbook.md"
        if not state.is_file() or not logbook.is_file():
            return False
        return "Abgeleitet aus AI Project Framework" in logbook.read_text(encoding="utf-8")
    except OSError:
        return False
