"""Tests fuer core/agent_narration.py (Bau-Bullauge, Spektakulaer #4):
deterministische deutsche Erzaehl-Zeile je Agenten-Ereignis, nie werfend."""
from __future__ import annotations

from core.agent_narration import narrate


def _tool(label: str, detail: str = "") -> dict:
    return {"kind": "tool", "label": label, "detail": detail}


def test_read_and_search_tools_speak_german():
    assert narrate(_tool("Read", "C:/proj/jkc/cli.py")) == "liest sich ein (cli.py)"
    assert narrate(_tool("Read")) == "liest sich in den Code ein"
    assert narrate(_tool("Grep", "def main")) == "durchsucht den Code"
    assert narrate(_tool("WebSearch", "pytest basetemp")) == "recherchiert im Netz"


def test_write_and_plan_tools_speak_german():
    assert narrate(_tool("Edit", "src\\video\\clip.py")) == "überarbeitet clip.py"
    assert narrate(_tool("Write")) == "schreibt am Code"
    assert narrate(_tool("TodoWrite")) == "plant die nächsten Schritte"


def test_bash_patterns_specific_before_generic():
    """Die Kundenreview-Zeile: «baue Tests» statt roher pytest-Befehl."""
    assert narrate(_tool("Bash", "python -m pytest -q")) == "lässt die Tests laufen"
    assert narrate(_tool("Bash", "git commit -m 'wip'")) == "sichert einen Zwischenstand"
    assert narrate(_tool("Bash", "git push origin main")) == "will den Stand veröffentlichen"
    assert narrate(_tool("Bash", "git status")) == "sieht den Projektstand nach"
    assert narrate(_tool("Bash", "pip install requests")) == "richtet Abhängigkeiten ein"
    assert narrate(_tool("Bash", "dir /b")) == "führt einen Befehl aus"


def test_text_events_become_thinking_line_not_english():
    """Englische Denk-Fragmente erscheinen nie mehr als Hauptzeile."""
    out = narrate({"kind": "text", "label": "überlegt",
                   "detail": "Let me check the existing structure first..."})
    assert out == "denkt kurz nach"


def test_unknown_tool_and_other_kinds_fail_readable():
    assert narrate(_tool("MysteryTool")) == "arbeitet (MysteryTool)"
    assert narrate({"kind": "start", "label": "Agent gestartet"}) == ""   # UI bleibt zustaendig
    assert narrate({"kind": "done", "label": "fertig"}) == ""
    assert narrate({"kind": "redirect", "detail": "mach anders"}) == ""
    assert narrate({}) == ""
    assert narrate({"kind": "tool", "label": None, "detail": None}) in ("arbeitet", "arbeitet (None)")


def test_runtime_sink_enriches_event_with_summary():
    """Verdrahtung (EINE Stelle): _agent_event_sink haengt die Erzaehl-Zeile
    als event['summary'] an - das Original-Event bleibt unveraendert."""
    from types import SimpleNamespace

    from jarvis_runtime import JarvisRuntime

    published = []
    fake = SimpleNamespace(agent_event_publisher=published.append)
    original = {"kind": "tool", "label": "Bash", "detail": "python -m pytest"}

    JarvisRuntime._agent_event_sink(fake, original)

    assert published[0]["summary"] == "lässt die Tests laufen"
    assert published[0]["label"] == "Bash"          # Roh-Detail bleibt am Event
    assert "summary" not in original                 # Original unangetastet
