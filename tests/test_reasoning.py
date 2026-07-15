"""Tests fuer core/reasoning.py (ADR-060) - die Entscheidungs-Logik des
denkenden Kerns. Die Werkzeug-Wahl (LLM) ist injiziert (Liste von Aufrufen);
kein Netz. Seit Phase 2 liefert decide eine LISTE von Plaenen (Multi-Step)."""
from __future__ import annotations

from core.models import Status
from core.reasoning import decide


def test_tool_choice_becomes_plan_like_the_planner():
    """Eine Werkzeug-Wahl -> ein Plan (intent=Werkzeug, target, parameters) -
    genau die Form, die auch der alte Planner liefert (1:1 vergleichbar)."""
    def caller(user_input, history, tools):
        return [("get_weather", {"target": "Berlin", "parameters": {"day": "morgen"}})]

    plans = decide("wie wird das Wetter morgen in Berlin?", [], caller)

    assert len(plans) == 1
    assert plans[0].intent == "get_weather"
    assert plans[0].target == "Berlin"
    assert plans[0].parameters == {"day": "morgen"}
    assert plans[0].confidence == 1.0


def test_multi_step_becomes_multiple_plans():
    """Mehrere Werkzeug-Wahlen ('X und Y') -> mehrere Plaene in Reihenfolge."""
    def caller(user_input, history, tools):
        return [("get_weather", {"target": "Berlin"}), ("get_news", {})]

    plans = decide("wetter in berlin und die news", [], caller)

    assert [p.intent for p in plans] == ["get_weather", "get_news"]
    assert plans[0].target == "Berlin"


def test_no_tool_means_chat():
    plans = decide("erzaehl mir einen Witz", [], lambda u, h, t: [])
    assert len(plans) == 1
    assert plans[0].intent == "chat" and plans[0].confidence == 1.0


def test_unknown_tool_falls_back_to_chat():
    """Fail-safe: waehlt der Kern NUR ein Werkzeug, das es nicht gibt -> chat,
    nie eine geratene Aktion."""
    plans = decide("tu irgendwas", [], lambda u, h, t: [("gibt_es_nicht", {})])
    assert len(plans) == 1
    assert plans[0].intent == "chat" and plans[0].confidence == 0.0


def test_unknown_tool_is_skipped_but_known_ones_survive():
    """Ein unbekanntes Werkzeug in der Liste wird uebersprungen, bekannte
    bleiben (nie die ganze Eingabe verwerfen wegen eines Streuners)."""
    plans = decide("x", [], lambda u, h, t: [("gibt_es_nicht", {}), ("get_news", {})])
    assert [p.intent for p in plans] == ["get_news"]


def test_exception_in_caller_falls_back_to_chat():
    def boom(user_input, history, tools):
        raise RuntimeError("LLM kaputt")

    plans = decide("hallo", [], boom)
    assert len(plans) == 1
    assert plans[0].intent == "chat" and plans[0].confidence == 0.0


def test_typed_flat_args_become_plan_parameters():
    """ADR-064: typisierte (flache) Argumente OHNE 'parameters'-Objekt landen
    direkt in Plan.parameters; 'target' bleibt das Ziel. So kommen die parallel
    zuverlaessig gefuellten Multi-Step-Args korrekt an."""
    def caller(user_input, history, tools):
        return [("add_to_list", {"target": "einkaufsliste", "items": ["Milch", "Brot"]})]

    plans = decide("setz milch und brot drauf", [], caller)

    assert plans[0].intent == "add_to_list"
    assert plans[0].target == "einkaufsliste"
    assert plans[0].parameters == {"items": ["Milch", "Brot"]}


def test_tool_without_target_or_params():
    plans = decide("pause", [], lambda u, h, t: [("spotify_pause", {})])
    assert plans[0].intent == "spotify_pause"
    assert plans[0].target is None
    assert plans[0].parameters == {}


def test_caller_receives_the_tool_schemas():
    """Der Kern reicht dem tool_caller die echten Werkzeug-Schemas (aus der
    Registry) durch - die Grundplatte aus Scheibe 1."""
    seen = {}

    def caller(user_input, history, tools):
        seen["tools"] = tools
        return []

    decide("test", [], caller)
    names = {t["function"]["name"] for t in seen["tools"]}
    assert "get_weather" in names and "build_project" in names


def test_select_tools_filters_schemas_before_caller():
    """Plan B: ein Selector filtert die Schemas VOR der Wahl (nur die relevanten)."""
    seen = {}

    def caller(user_input, history, tools):
        seen["tools"] = tools
        return []

    def only_weather(user_input, tools):
        return [t for t in tools if t["function"]["name"] == "get_weather"]

    decide("wetter?", [], caller, select_tools=only_weather)
    names = {t["function"]["name"] for t in seen["tools"]}
    assert names == {"get_weather"}


def test_select_tools_failopen_on_error():
    """Wirft der Selector, werden ALLE Tools genutzt (keine Regression)."""
    seen = {}

    def caller(user_input, history, tools):
        seen["tools"] = tools
        return []

    def boom(user_input, tools):
        raise RuntimeError("kaputt")

    decide("test", [], caller, select_tools=boom)
    names = {t["function"]["name"] for t in seen["tools"]}
    assert "get_weather" in names and "build_project" in names   # voll, nicht leer


def test_returned_plan_dispatches_through_normal_registry():
    """Der Plan des Kerns laeuft ueber denselben dispatch wie ein Planner-Plan -
    also durch dieselben Sicherheits-Gates (hier: unkonfiguriertes Spotify
    meldet sauber, statt zu handeln)."""
    import commands.spotify as spotify_commands
    from commands import dispatch

    spotify_commands.configure(config=None, client=None)   # nicht eingerichtet
    plans = decide("was laeuft gerade?", [], lambda u, h, t: [("spotify_now_playing", {})])
    result = dispatch(plans[0])
    # Kein Absturz, sauberes Ergebnis ueber den ganz normalen Pfad.
    assert result.status in (Status.SUCCESS, Status.NEEDS_CLARIFICATION, Status.FAILED)
