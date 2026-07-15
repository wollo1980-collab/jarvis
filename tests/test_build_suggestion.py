"""Tests fuer core/build_suggestion.py (ADR-067) - LLM injiziert, kein Netz."""
from __future__ import annotations

from core.build_suggestion import frictions_text, suggest_build, usage_text

_VALID = ("Mir ist aufgefallen: du prüfst oft das Wetter. Ich koennte dir "
          "«wetter-cli» bauen, das dir das Wetter im Terminal zeigt. Sag "
          "«Bau mir wetter-cli», dann lege ich los.")


def test_suggest_returns_grounded_idea_with_trigger():
    out = suggest_build("- get_weather: 10x", "(keine)", lambda s, u: _VALID)
    assert "wetter-cli" in out
    assert "Bau mir" in out


def test_keine_returns_empty():
    assert suggest_build("u", "f", lambda s, u: "KEINE") == ""
    assert suggest_build("u", "f", lambda s, u: "KEINE.") == ""


def test_missing_trigger_phrase_is_rejected():
    # ohne den Ausloese-Satz "Bau mir" -> Muell-Schutz greift
    assert suggest_build("u", "f", lambda s, u: "Ich koennte dir ein Tool bauen.") == ""


def test_llm_error_returns_empty():
    def boom(system, user):
        raise RuntimeError("down")

    assert suggest_build("u", "f", boom) == ""


def test_gate_bypass_proposals_are_rejected():
    """Sicherheits-Riegel (Live-Befund 15.07.): der Vorschlag «kalender-
    termin-loescher ... ohne Bestätigung» wollte ein Bestaetigungs-Gate
    umgehen - solche Ideen werden deterministisch verworfen, egal was der
    Prompt liefert (fail-closed gegen Prompt-Drift)."""
    live_case = ("Mir ist aufgefallen: Du hast Schwierigkeiten, Termine im "
                 "Kalender zu löschen, da du keine Bestätigung erhältst. Ich "
                 "koennte dir «kalender-termin-loescher» bauen, das es dir "
                 "ermöglicht, Termine im Kalender direkt zu löschen, ohne eine "
                 "Bestätigung anfordern zu müssen. Sag «Bau mir "
                 "kalender-termin-loescher», dann lege ich los.")
    assert suggest_build("u", "f", lambda s, u: live_case) == ""
    for phrase in ("ohne Rückfrage", "die Bestätigung umgehen", "ohne Freigabe"):
        text = f"Mir ist aufgefallen: X. Ich koennte dir «t» bauen, das Y {phrase}. Sag «Bau mir t», dann lege ich los."
        assert suggest_build("u", "f", lambda s, u, t=text: t) == ""
    # Der Prompt traegt die Regel ausserdem ausdruecklich:
    from core.build_suggestion import _PROMPT
    assert "NIEMALS" in _PROMPT and "Bestaetigungen" in _PROMPT
    # Gutartige Vorschlaege passieren weiterhin:
    assert "wetter-cli" in suggest_build("u", "f", lambda s, u: _VALID)


def test_usage_text_sorts_by_count_desc():
    text = usage_text({"selten": {"1": 3}, "oft": {"1": 10, "2": 5}})
    assert text.index("oft:") < text.index("selten:")


def test_frictions_text_picks_only_failures():
    eps = [{"user_input": "gut", "response": "✓ ok"},
           {"user_input": "schlecht", "response": "✗ Fehler"}]
    text = frictions_text(eps)
    assert "schlecht" in text and "gut" not in text
