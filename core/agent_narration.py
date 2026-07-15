"""
Bau-Bullauge (Spektakulaer #4, Design 2026-07-13): deutsche Erzaehl-Zeile je
Agenten-Ereignis.

Der LIVE-ABLAUF zeigte Agenten-Schritte roh ('-> Read jkc/cli.py', 'ueberlegt:
Let me check...') - englisch, technisch, repetitiv (Kundenreview: 'Waschmaschine
ohne Bullauge'). narrate() uebersetzt jedes generische Ereignis {kind,label,
detail} DETERMINISTISCH in einen deutschen Halbsatz; das Roh-Detail bleibt am
Event erhalten (Transparenz - die UI zeigt es im Hover).

Bewusst KEIN LLM je Event: der Sink laeuft im Delegations-Thread, ein Call je
Schritt waere Latenz/Kosten/Blockade-Risiko im laufenden Bau. Die Tabelle
deckt die Werkzeug-Events; englische Denk-Fragmente werden ehrlich zu 'denkt
kurz nach'. Fail-safe: nie werfend, Unbekanntes faellt lesbar zurueck.
"""
from __future__ import annotations

import re

# Werkzeugname -> Halbsatz-Bauer. Reihenfolge der Bash-Muster wichtig
# (spezifisch vor generisch). Alle Texte sprechtauglich klein gehalten.
_READ_TOOLS = {"Read", "Glob", "Grep", "NotebookRead", "LS", "WebFetch", "WebSearch"}
_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
_PLAN_TOOLS = {"TodoWrite", "Task", "TaskCreate", "TaskUpdate", "EnterPlanMode", "ExitPlanMode"}

_BASH_PATTERNS: "list[tuple[re.Pattern, str]]" = [
    (re.compile(r"\bpytest\b|\bunittest\b|\btest", re.I), "lässt die Tests laufen"),
    (re.compile(r"\bgit\s+commit\b", re.I), "sichert einen Zwischenstand"),
    (re.compile(r"\bgit\s+push\b", re.I), "will den Stand veröffentlichen"),
    (re.compile(r"\bgit\s+(status|log|diff|show|branch)\b", re.I), "sieht den Projektstand nach"),
    (re.compile(r"\b(pip|npm|uv|poetry)\b.*\binstall\b", re.I), "richtet Abhängigkeiten ein"),
    (re.compile(r"\bmkdir\b|\bNew-Item\b", re.I), "legt Ordner/Dateien an"),
    (re.compile(r"\bpython\b|\bnode\b", re.I), "probiert das Programm aus"),
]

_FILE_TAIL_RE = re.compile(r"[^\\/]+$")


def _file_name(detail: str) -> str:
    """Nur der Dateiname aus einem Pfad-Detail - kurz genug fuer eine Zeile."""
    match = _FILE_TAIL_RE.search((detail or "").strip())
    return match.group(0)[:60] if match else ""


def narrate(event: dict) -> str:
    """Deutscher Halbsatz zu einem Agenten-Ereignis. Nie werfend; leerer
    String heisst 'die UI soll ihre bisherige Darstellung nutzen'
    (start/done/redirect sind dort schon deutsch)."""
    try:
        kind = str(event.get("kind", ""))
        label = str(event.get("label", "")).strip()
        detail = str(event.get("detail", "")).strip()

        if kind == "text":
            return "denkt kurz nach"
        if kind != "tool":
            return ""

        if label in _READ_TOOLS:
            name = _file_name(detail)
            if label in ("Grep", "Glob"):
                return "durchsucht den Code"
            if label in ("WebFetch", "WebSearch"):
                return "recherchiert im Netz"
            return f"liest sich ein ({name})" if name else "liest sich in den Code ein"
        if label in _WRITE_TOOLS:
            name = _file_name(detail)
            return f"überarbeitet {name}" if name else "schreibt am Code"
        if label in _PLAN_TOOLS:
            return "plant die nächsten Schritte"
        if label == "Bash" or label.lower() in ("bash", "powershell", "shell"):
            for pattern, text in _BASH_PATTERNS:
                if pattern.search(detail):
                    return text
            return "führt einen Befehl aus"
        # Unbekanntes Werkzeug: ehrlich, aber lesbar.
        return f"arbeitet ({label})" if label else "arbeitet"
    except Exception:  # noqa: BLE001 - Erzaehlung ist Beiwerk, nie werfend
        return ""
